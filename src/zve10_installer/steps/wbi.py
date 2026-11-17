"""Advanced WBI invalidation: prepare, explicit confirmation, drop.

This wraps the upstream ``wbi-prepare`` / ``wbi-drop`` actions. It refuses
already-invalid WBI, requires a user-supplied official Sony utility and a typed
recovery-route confirmation, and validates the full readback result.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .. import doctor
from ..errors import GateError, InstallerError, PreflightError
from ..evidence import RunDir
from ..prompts import confirm_exact
from ..server import SessionServer
from ..state import RunState, Stage
from ..upstream import Upstream
from . import guards

TOOL_SIZE = 6200
TOOL_HASH = "f2a5b27a0c11d55a612d61e61e82c55278efb744052ecb8ec2cbbd8851d0ea6e"
EXPECTED_SONY_OUTPUT = "[UD_WBI_DROP] /dev/nflasha5 wbi_drop"


def validate_tool(path: str | Path) -> Path:
    tool = Path(path).expanduser().resolve()
    if not tool.is_file():
        raise GateError("wbi_tool", f"tool not found: {tool}")
    data = tool.read_bytes()
    if len(data) != TOOL_SIZE or hashlib.sha256(data).hexdigest() != TOOL_HASH:
        raise GateError(
            "wbi_tool",
            "unexpected ud_wbi_drop.elf size/hash; use the file from your own ZV-E10 2.03 update package",
        )
    return tool


class WbiSession:
    def __init__(self, upstream: Upstream, runs_dir: Path, *, firmware: str = "2.03") -> None:
        self.upstream = upstream
        self.firmware = firmware
        self.run_dir = RunDir.create(Path(runs_dir), "wbi")
        self.state = RunState.load_or_create(self.run_dir.state_path)
        self.server = SessionServer(
            upstream,
            self.run_dir.session_dir,
            write=True,
            firmware=firmware,
            log_dir=self.run_dir.path,
        )
        self.prepared = False
        self.write_attempted = False
        self.prepare_result: dict = {}
        self.tool: Path | None = None
        self.state.advance(Stage.ENV_READY, {"firmware": firmware, "upstream": str(upstream.root)})

    def prepare(self, sony_tool: str | Path) -> dict:
        tool = validate_tool(sony_tool)
        self.tool = tool
        try:
            self.server.start()
            self.state.advance(Stage.CONNECTED, {"session_dir": str(self.run_dir.session_dir)})
            guards.check(self.server)
            result = self.server.submit(
                {
                    "action": "wbi-prepare",
                    "model": "ZV-E10",
                    "displayed_firmware": self.firmware,
                    "sony_tool": str(tool),
                },
                timeout=600,
            )
            status = result.get("status")
            if status == "already-invalid":
                raise GateError(
                    "wbi_prepare",
                    "WBI is already invalid; refuse to write it again",
                )
            if status != "valid":
                raise GateError("wbi_prepare", f"unexpected WBI preparation status: {status!r}")
            if not result.get("token") or not result.get("confirmation"):
                raise GateError("wbi_prepare", f"preparation returned no token/confirmation: {result!r}")
            self.prepared = True
            self.prepare_result = result
            self.state.advance(
                Stage.WBI_PREPARED,
                {
                    "token": result.get("token"),
                    "confirmation": result.get("confirmation"),
                    "backup_sha256": result.get("backup_sha256"),
                },
            )
            return result
        except Exception:
            self.close()
            raise

    def execute(self, confirmation: str, recovery_ready: bool) -> dict:
        if not self.prepared:
            raise InstallerError("WBI session is not prepared")
        if not recovery_ready:
            raise GateError("wbi_recovery", "recovery route was not confirmed")
        if confirmation != self.prepare_result.get("confirmation"):
            raise GateError("wbi_confirm", "confirmation string does not match")

        self.write_attempted = True
        try:
            self.state.advance(Stage.WBI_CONFIRMED, {"recovery_ready": True})
            result = self.server.submit(
                {
                    "action": "wbi-drop",
                    "prepared": self.prepare_result["token"],
                    "sony_tool": str(self.tool),
                    "confirm_emmc_write": confirmation,
                    "recovery_ready": True,
                },
                timeout=600,
            )
            if result.get("write_attempted") is not True:
                raise GateError("wbi_drop", f"write was not attempted: {result!r}")
            status = str(result.get("status", ""))
            if "invalidated" not in status:
                raise GateError("wbi_drop", f"unexpected WBI drop status: {result!r}")
            output = str(result.get("sony_output", ""))
            if output.strip() != EXPECTED_SONY_OUTPUT:
                raise GateError("wbi_drop", f"unexpected Sony output: {output!r}")
            if not result.get("after_sha256"):
                raise GateError("wbi_drop", f"missing after_sha256: {result!r}")

            self.state.advance(Stage.WBI_DROPPED, {"after_sha256": result.get("after_sha256")})
            self.server.close()
            self.state.advance(Stage.DONE, {})

            summary = {
                "kind": "wbi",
                "run_dir": str(self.run_dir.path),
                "session_dir": str(self.run_dir.session_dir),
                "status": "wbi_completed",
                "sony_output": output.strip(),
                "after_sha256": result.get("after_sha256"),
                "token": self.prepare_result.get("token"),
                "confirmation": confirmation,
                "next": "Cold boot the camera, then run verify and expect TypeNB/5.",
            }
            self.run_dir.write_json("summary.json", summary)
            self.run_dir.append_event("wbi", {"status": "invalidated"})
            self.prepared = False
            return summary
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        try:
            if self.server.proc is not None and self.server.state().get("state") != "closed":
                self.server.close()
        except Exception as exc:
            self.run_dir.append_event("close_error", {"error": repr(exc)})
        finally:
            self.server.terminate()

        if self.state.stage == Stage.DONE:
            self.prepared = False
            return

        uncertain = self.write_attempted and self.state.stage in {
            Stage.WBI_PREPARED,
            Stage.WBI_CONFIRMED,
        }
        target = Stage.UNKNOWN if uncertain else Stage.STOPPED
        if self.state.stage not in {Stage.DONE, Stage.STOPPED, Stage.UNKNOWN, Stage.RECOVERY_REQUIRED}:
            try:
                self.state.advance(target, {"cancelled": True})
            except Exception:
                pass
        self.prepared = False


def run(
    upstream: Upstream,
    runs_dir: Path,
    *,
    sony_tool: str,
    firmware: str = "2.03",
) -> dict:
    checks = doctor.run(upstream)
    if doctor.has_failures(checks):
        raise PreflightError("doctor reported required failures:\n" + doctor.format_checks(checks))
    camera = next((check for check in checks if check.name == "camera_usb"), None)
    if camera is None or not camera.ok:
        raise PreflightError("camera 054c not enumerated; connect it in Mass Storage mode")

    session = WbiSession(upstream, runs_dir, firmware=firmware)
    try:
        result = session.prepare(sony_tool)
        print("WBI prepared (no write yet):")
        print(f"  token: {result.get('token')}")
        print(f"  backup_sha256: {result.get('backup_sha256')}")
        print(f"  warning: {result.get('warning')}")
        print(f"  confirmation: {result.get('confirmation')}")
        confirm_exact(
            str(result.get("confirmation")),
            "Type the exact WBI confirmation string to authorize the eMMC write.",
        )
        confirm_exact(
            "RECOVERY-READY",
            "Confirm you have a Pico/BootROM + fastboot recovery route for this camera.",
        )
        return session.execute(str(result.get("confirmation")), recovery_ready=True)
    except InstallerError:
        session.close()
        raise
