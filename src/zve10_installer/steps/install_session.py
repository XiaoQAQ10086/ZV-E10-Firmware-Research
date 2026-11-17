"""Stateful install session: prepare (read-only checks + backup), then execute.

The session is kept open between prepare and execute so the GUI can show the
precondition checklist and ask for explicit confirmation without opening a
second Jiritsu session. No camera write happens during prepare.
"""

from __future__ import annotations

from pathlib import Path

from .. import gates
from ..errors import GateError, InstallerError
from ..evidence import RunDir
from ..server import SessionServer
from ..state import RunState, Stage
from ..upstream import Upstream
from . import backup as backup_step
from . import guards
from . import identity
from . import patch as patch_step
from . import preservation
from . import props as props_step
from . import stability as stability_step


class InstallSession:
    def __init__(
        self,
        upstream: Upstream,
        runs_dir: Path,
        *,
        firmware: str = "2.03",
        backup_passes: int = 1,
        backup_copy: Path | None = None,
        stability_seconds: int = 120,
        stability_minimum_passes: int = 2,
        battery_percent: int | None = None,
    ) -> None:
        self.upstream = upstream
        self.firmware = firmware
        self.backup_passes = backup_passes
        self.backup_copy = Path(backup_copy).expanduser().resolve() if backup_copy else None
        self.stability_seconds = stability_seconds
        self.stability_minimum_passes = stability_minimum_passes
        self.battery_percent = battery_percent
        self.run_dir = RunDir.create(Path(runs_dir), "install")
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
        self.body_id: str | None = None
        self.first: dict = {}
        self.second: dict = {}
        self.backup: dict = {}
        self.natural_changes: set[int] = set()
        self.facts: dict = {}
        self.state.advance(
            Stage.ENV_READY,
            {"upstream": str(upstream.root), "firmware": firmware},
        )

    # -- precondition check + backup --------------------------------------
    def prepare(self, region: str) -> dict:
        gates.require(gates.check_region(region))
        if self.battery_percent is None or not 50 <= self.battery_percent <= 100:
            raise GateError("battery", "enter the camera battery percentage (50-100) first")
        try:
            self.server.start()
            self.state.advance(Stage.CONNECTED, {"session_dir": str(self.run_dir.session_dir)})
            guards.check(self.server)

            first = self.server.submit({"action": "inspect"}, timeout=420)
            gates.require(gates.check_prewrite(first))
            gates.require(gates.check_baseline_properties(first.get("backup") or {}))
            first_snapshot = str(first.get("snapshot") or "")
            if not first_snapshot:
                raise GateError("identity", "inspect did not return a Backup snapshot")
            self.body_id = identity.body_id(
                self.upstream,
                self._snapshot_paths(first_snapshot)[0],
            )
            self.first = first
            self.state.advance(
                Stage.INSPECTED,
                {
                    "sha256": first.get("sha256"),
                    "backup": first.get("backup"),
                    "snapshot": first.get("snapshot"),
                    "body_id": self.body_id,
                },
            )
            self.state.advance(Stage.SCOPE_CONFIRMED, {"region": region})

            stability = stability_step.run(
                self.server,
                initial=first,
                seconds=self.stability_seconds,
                minimum_passes=self.stability_minimum_passes,
            )
            self.run_dir.append_event("stability", stability)

            backup = backup_step.run(
                self.server,
                self.upstream,
                self.run_dir,
                passes=self.backup_passes,
            )
            self.backup = backup
            if self.backup_copy is None:
                raise GateError(
                    "backup_copy",
                    "a second backup directory is required; choose an empty folder, preferably on another disk",
                )
            second_copy = backup_step.copy_to_second(
                Path(backup["backup_dir"]),
                self.backup_copy,
            )
            self.state.advance(
                Stage.BACKUP_DONE,
                {
                    "backup_dir": backup.get("backup_dir"),
                    "backup_copy": second_copy.get("backup_copy"),
                    "passes": self.backup_passes,
                    "stability": stability,
                },
            )

            second = self.server.submit({"action": "inspect"}, timeout=420)
            gates.require(gates.check_prewrite(second))
            if second.get("sha256") != first.get("sha256") or second.get("backup") != first.get("backup"):
                raise GateError(
                    "prewrite_recheck",
                    "library or properties changed since the first inspect",
                )
            self.second = second
            first_snapshot = str(first.get("snapshot") or "")
            second_snapshot = str(second.get("snapshot") or "")
            if not first_snapshot or not second_snapshot:
                raise GateError("preservation", "inspect did not return a Backup snapshot")
            second_body = identity.body_id(
                self.upstream,
                self._snapshot_paths(second_snapshot)[0],
            )
            if second_body != self.body_id:
                raise GateError("identity", "camera identity changed between inspections")
            self.natural_changes = preservation.changed_keys(
                self.upstream,
                self._snapshot_paths(first_snapshot),
                self._snapshot_paths(second_snapshot),
            )
            self.state.advance(
                Stage.PREWRITE_INSPECTED,
                {
                    "snapshot": second.get("snapshot"),
                    "natural_changes": len(self.natural_changes),
                    "battery_percent": self.battery_percent,
                },
            )

            self.prepared = True
            self.facts = {
                "region": region,
                "firmware": self.firmware,
                "sha256": first.get("sha256"),
                "library": gates.classify_library(str(first.get("sha256", ""))),
                "backup": first.get("backup"),
                "backup_dir": backup.get("backup_dir"),
                "backup_copy": second_copy.get("backup_copy"),
                "backup_passes": self.backup_passes,
                "stability": stability,
                "battery_percent": self.battery_percent,
                "body_id": self.body_id,
                "mounts": first.get("mounts"),
                "run_dir": str(self.run_dir.path),
                "session_dir": str(self.run_dir.session_dir),
            }
            return self.facts
        except Exception:
            self.close()
            raise

    # -- write -------------------------------------------------------------
    def execute(self) -> dict:
        if not self.prepared:
            raise InstallerError("install session is not prepared")
        self.write_attempted = True
        try:
            patch = patch_step.run(self.server, self.run_dir)
            self.state.advance(Stage.PATCHED, {"patch_sha256": patch.get("sha256")})

            props_step.run(self.server, self.run_dir, self.first.get("backup") or {})
            self.state.advance(Stage.PROPS_DONE, {"properties": "01/02/16"})

            final = self.server.submit({"action": "inspect"}, timeout=420)
            gates.require(gates.check_installed_state(final))
            final_snapshot = str(final.get("snapshot") or "")
            second_snapshot = str(self.second.get("snapshot") or "")
            if not final_snapshot or not second_snapshot:
                raise GateError("preservation", "inspect did not return a Backup snapshot")
            preservation_result = preservation.compare(
                self.upstream,
                self._snapshot_paths(second_snapshot),
                self._snapshot_paths(final_snapshot),
                allowed_keys=self.natural_changes,
            )

            self.server.close()
            self.state.advance(Stage.WRITE_CLOSED, {"closed": True})
            self.prepared = False

            summary = {
                "kind": "install",
                "run_dir": str(self.run_dir.path),
                "session_dir": str(self.run_dir.session_dir),
                "status": "awaiting_verify",
                "sha256": final.get("sha256"),
                "backup": final.get("backup"),
                "backup_dir": self.backup.get("backup_dir"),
                "preservation": preservation_result,
                "battery_percent": self.battery_percent,
                "body_id": self.body_id,
                "next": (
                    "Cold boot the camera (off, wait for the lamp, unplug, remove the "
                    "battery for ~30s, refit, boot, Mass Storage, reconnect), then run verify."
                ),
            }
            self.run_dir.write_json("summary.json", summary)
            self.run_dir.append_event("install", {"status": "awaiting_verify"})
            return summary
        except Exception:
            self.close()
            raise

    # -- teardown ----------------------------------------------------------
    def _snapshot_paths(self, token: str) -> list[Path]:
        session = self.run_dir.session_dir
        return [session / f"{token}-Backup.bin", session / f"{token}-Backup.bak"]

    def close(self) -> None:
        try:
            if self.server.proc is not None and self.server.state().get("state") != "closed":
                self.server.close()
        except Exception as exc:
            self.run_dir.append_event("close_error", {"error": repr(exc)})
        finally:
            self.server.terminate()

        if self.state.stage == Stage.WRITE_CLOSED:
            self.prepared = False
            return

        uncertain = self.state.stage in {Stage.PATCHED, Stage.PROPS_DONE} or (
            self.write_attempted and self.state.stage == Stage.PREWRITE_INSPECTED
        )
        target = Stage.UNKNOWN if uncertain else Stage.STOPPED
        if self.state.stage not in {Stage.DONE, Stage.STOPPED, Stage.UNKNOWN, Stage.RECOVERY_REQUIRED}:
            try:
                self.state.advance(target, {"cancelled": True})
            except Exception:
                pass
        self.prepared = False
