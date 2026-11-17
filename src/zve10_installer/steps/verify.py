"""Read-only post-install verification.

Run this in a new session after the owner has cold-booted the camera. It checks
that the patched library and properties persisted and that the running Page1 is
TypeNB with five items. It never writes to the camera.
"""

from __future__ import annotations

from pathlib import Path

from .. import gates
from ..evidence import RunDir
from ..server import SessionServer
from ..upstream import Upstream
from . import identity
from . import runtime as runtime_step


def run(
    upstream: Upstream,
    base_dir: Path,
    *,
    firmware: str = "2.03",
    timeout: int = 420,
    runtime_check: bool = False,
) -> dict:
    run_dir = RunDir.create(Path(base_dir), "verify")
    server = SessionServer(
        upstream,
        run_dir.session_dir,
        write=runtime_check,
        firmware=firmware,
        log_dir=run_dir.path,
    )
    try:
        server.start()
        inspect = server.submit({"action": "inspect"}, timeout=timeout)
        installed = gates.check_installed_state(inspect)
        snapshot = str(inspect.get("snapshot") or "")
        body = None
        if snapshot:
            try:
                body = identity.body_id(
                    upstream,
                    run_dir.session_dir / f"{snapshot}-Backup.bin",
                )
            except Exception as exc:  # noqa: BLE001 - identity is supplementary
                run_dir.append_event("identity_error", {"error": repr(exc)})
        boot = server.submit({"action": "boot-check"}, timeout=240)
        post = gates.check_post_boot(boot)
        page1 = boot.get("page1") or {}

        runtime_result = None
        runtime_error = None
        if runtime_check:
            try:
                runtime_result = runtime_step.check(server, boot)
            except Exception as exc:  # noqa: BLE001 - reported in the summary
                runtime_error = str(exc)
                run_dir.append_event("runtime_error", {"error": runtime_error})

        runtime_ok = not runtime_check or (runtime_result is not None and runtime_error is None)
        if installed.ok and post.ok and runtime_ok:
            status = "ok"
        elif (
            installed.ok
            and page1.get("type") == "TypeRK"
            and page1.get("count") == 4
            and runtime_ok
        ):
            status = "wbi_required"
        else:
            status = "failed"

        summary = {
            "kind": "verify",
            "run_dir": str(run_dir.path),
            "session_dir": str(run_dir.session_dir),
            "status": status,
            "installed": {"ok": installed.ok, "detail": installed.detail},
            "post_boot": {"ok": post.ok, "detail": post.detail},
            "page1": page1,
            "warm_resume_markers": boot.get("warm_resume_markers"),
            "sha256": inspect.get("sha256"),
            "backup": inspect.get("backup"),
            "body_id": body,
            "runtime_check": runtime_check,
            "runtime": runtime_result,
            "runtime_error": runtime_error,
        }
        run_dir.write_json("summary.json", summary)
        run_dir.append_event("verify", {"status": status, "page1": page1})
        return summary
    finally:
        try:
            if server.state().get("state") != "closed":
                server.close()
        except Exception as exc:
            run_dir.append_event("close_error", {"error": repr(exc)})
        finally:
            server.terminate()
