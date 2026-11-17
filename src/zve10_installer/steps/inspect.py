"""Read-only inspect step.

Starts one read-only Jiritsu session, runs the upstream ``inspect`` action, and
records the library hash, Backup properties and mount table. The upstream action
exports snapshots into the session directory; those files stay local.
"""

from __future__ import annotations

from pathlib import Path

from .. import gates
from ..errors import InstallerError
from ..evidence import RunDir
from ..server import SessionServer
from ..state import RunState, Stage
from ..upstream import Upstream
from . import identity


def run(
    upstream: Upstream,
    runs_dir: Path,
    *,
    firmware: str = "2.03",
    timeout: int = 420,
) -> dict:
    run_dir = RunDir.create(Path(runs_dir), "inspect")
    state = RunState.load_or_create(run_dir.state_path)
    server = SessionServer(
        upstream,
        run_dir.session_dir,
        write=False,
        firmware=firmware,
        log_dir=run_dir.path,
    )
    try:
        server.start()
        state.advance(Stage.ENV_READY, {"upstream": str(upstream.root), "firmware": firmware})
        state.advance(Stage.CONNECTED, {"session_dir": str(run_dir.session_dir)})
        result = server.submit({"action": "inspect"}, timeout=timeout)
        gate = gates.check_prewrite(result)
        snapshot = str(result.get("snapshot") or "")
        body = None
        if snapshot:
            try:
                body = identity.body_id(
                    upstream,
                    run_dir.session_dir / f"{snapshot}-Backup.bin",
                )
            except Exception as exc:  # noqa: BLE001 - identity is supplementary
                run_dir.append_event("identity_error", {"error": repr(exc)})
        facts = {
            "size": result.get("size"),
            "sha256": result.get("sha256"),
            "library": gates.classify_library(str(result.get("sha256", ""))),
            "backup": result.get("backup"),
            "snapshot": result.get("snapshot"),
            "body_id": body,
        }
        if gate.ok:
            state.advance(Stage.INSPECTED, facts)
        else:
            state.advance(Stage.STOPPED, {"gate": gate.detail, **facts})
        summary = {
            "kind": "inspect",
            "run_dir": str(run_dir.path),
            "session_dir": str(run_dir.session_dir),
            "gate": {"name": gate.name, "ok": gate.ok, "detail": gate.detail},
            "facts": facts,
            "result": result,
        }
        run_dir.write_json("summary.json", summary)
        run_dir.append_event("inspect", {"gate_ok": gate.ok, "sha256": facts["sha256"]})
        gates.require(gate)
        return summary
    except InstallerError as exc:
        if state.stage in {Stage.IDLE, Stage.ENV_READY, Stage.CONNECTED}:
            try:
                state.advance(Stage.STOPPED, {"error": repr(exc)})
            except Exception:
                pass
        raise
    except Exception as exc:
        try:
            state.advance(Stage.STOPPED, {"error": repr(exc)})
        except Exception:
            pass
        raise
    finally:
        try:
            if server.state().get("state") != "closed":
                server.close()
        except Exception as exc:
            run_dir.append_event("close_error", {"error": repr(exc)})
        finally:
            server.terminate()
