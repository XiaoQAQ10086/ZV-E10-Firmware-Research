"""Service session lifecycle.

Starts the upstream ``wifi.py serve`` process, waits for ``state.json`` to say
ready, submits requests through the upstream client, and waits for the documented
teardown flags on close. It never kills a session to "fix" a timeout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import client
from .errors import SessionError
from .gates import check_close_flags
from .platform_compat import frozen_root
from .upstream import Upstream

_CREATE_NO_WINDOW = 0x08000000


class SessionServer:
    def __init__(
        self,
        upstream: Upstream,
        session_dir: Path,
        *,
        write: bool = False,
        backend: str = "jiritsu",
        firmware: str = "2.03",
        idle_timeout: int = 3600,
        log_dir: Path | None = None,
        ready_timeout: int = 180,
        close_timeout: int = 120,
        server_mode: str = "upstream",
    ) -> None:
        if server_mode not in {"upstream", "sound"}:
            raise ValueError("server_mode must be 'upstream' or 'sound'")
        self.upstream = upstream
        self.session_dir = Path(session_dir)
        self.server_mode = server_mode
        self.write = write
        self.backend = backend
        self.firmware = firmware
        self.idle_timeout = idle_timeout
        self.log_dir = Path(log_dir) if log_dir else self.session_dir.parent
        self.ready_timeout = ready_timeout
        self.close_timeout = close_timeout
        self.proc: subprocess.Popen | None = None
        self._stdout = None
        self._stderr = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self.session_dir.exists() and any(self.session_dir.iterdir()):
            raise SessionError(
                f"session directory is not empty: {self.session_dir}. "
                "Every session needs a new, empty directory."
            )
        self.session_dir.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if (self.log_dir / "serve.out").exists():
            raise SessionError(
                f"refusing to overwrite existing logs in {self.log_dir}; use a new run directory"
            )

        env = os.environ.copy()
        env["PYTHONPATH"] = self.upstream.pythonpath()
        if self.server_mode == "sound" and frozen_root() is None:
            # The child runs ``python -m zve10_installer.sound_server`` from
            # source; keep this package importable alongside the upstream tree.
            package_root = str(Path(__file__).resolve().parents[1])
            env["PYTHONPATH"] = os.pathsep.join([package_root, env["PYTHONPATH"]])
        env["ZVE10_TOOLKIT"] = str(self.upstream.toolkit)

        command = [sys.executable]
        if frozen_root() is not None:
            hidden = "__sound-serve" if self.server_mode == "sound" else "__serve"
            command += [hidden, "--upstream-root", str(self.upstream.root)]
            if self.server_mode == "sound":
                command += ["--pmca-root", str(self.upstream.pmca)]
        elif self.server_mode == "sound":
            command += [
                "-B",
                "-m",
                "zve10_installer.sound_server",
                "--upstream-root",
                str(self.upstream.root),
                "--pmca-root",
                str(self.upstream.pmca),
            ]
        else:
            command += ["-B", str(self.upstream.wifi_py)]
        command += [
            "serve",
            "--client-uid",
            "0",
            "--idle-timeout",
            str(self.idle_timeout),
            "--session-dir",
            str(self.session_dir),
            "--backend",
            self.backend,
            "--firmware",
            self.firmware,
            "--owner-authorized-exec",
        ]
        if self.write:
            command.append("--owner-authorized-write")

        self._stdout = (self.log_dir / "serve.out").open("ab")
        self._stderr = (self.log_dir / "serve.err").open("ab")
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            command,
            cwd=str(self.upstream.root),
            env=env,
            stdout=self._stdout,
            stderr=self._stderr,
            **kwargs,
        )
        try:
            self._wait_ready()
        except Exception:
            self.terminate()
            raise

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise SessionError(f"service exited before ready:\n{self._log_tail()}")
            state = self.state()
            if state.get("state") == "ready":
                return
            if state.get("state") in {"error", "failed"}:
                raise SessionError(f"service reported {state.get('state')}: {state!r}")
            time.sleep(0.5)
        raise SessionError(f"service did not become ready within {self.ready_timeout}s:\n{self._log_tail()}")

    def _log_tail(self, limit: int = 4000) -> str:
        chunks = []
        for name in ("serve.out", "serve.err"):
            path = self.log_dir / name
            if path.is_file():
                chunks.append(f"--- {name} ---\n{path.read_text(errors='replace')[-limit:]}")
        return "\n".join(chunks) or "(no logs)"

    # -- requests ----------------------------------------------------------
    def state(self) -> dict:
        path = self.session_dir / "state.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def submit(self, payload: dict, timeout: int = 360) -> dict:
        return client.submit(self.upstream, self.session_dir, payload, timeout=timeout)

    # -- teardown ----------------------------------------------------------
    def close(self) -> dict:
        if self.proc is None:
            return {}
        answer = self.submit({"action": "close"}, timeout=120)
        deadline = time.monotonic() + self.close_timeout
        while time.monotonic() < deadline:
            state = self.state()
            if check_close_flags(state).ok:
                self._reap()
                return state
            if self.proc.poll() is not None:
                state = self.state()
                if check_close_flags(state).ok:
                    return state
                raise SessionError(f"service exited without teardown flags: {state!r}")
            time.sleep(0.5)
        raise SessionError(f"session did not close cleanly within {self.close_timeout}s: {self.state()!r}")

    def _reap(self) -> None:
        if self.proc is not None:
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.terminate()

    def terminate(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for handle in (self._stdout, self._stderr):
            if handle is not None:
                handle.close()
        self._stdout = self._stderr = None

    def __enter__(self) -> "SessionServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.proc is not None and self.proc.poll() is None:
                if self.state().get("state") != "closed":
                    self.close()
        except Exception:
            if exc_type is None:
                raise
        finally:
            self.terminate()
