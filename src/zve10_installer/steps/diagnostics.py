"""Build a small, privacy-aware diagnostic bundle.

Only logs, state summaries and environment information are included. Camera
backups, firmware, helper binaries and Sony tools are excluded.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__, doctor
from ..platform_compat import repo_root
from ..upstream import Upstream

PRIVACY = """\
This bundle contains local paths, session logs and device check results.
It does not contain camera backups, firmware, helper binaries or Sony tools.
Review it before sharing publicly.
"""

RUN_FILES = ("state.json", "run.jsonl", "summary.json", "serve.out", "serve.err")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_bundle(
    runs_dir: Path,
    upstream: Upstream | None,
    extra: dict | None = None,
    *,
    max_runs: int = 3,
) -> Path:
    runs_dir = Path(runs_dir).expanduser().resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = runs_dir / f"diagnostics-{stamp}.zip"

    env_lines = [
        f"app_version: {__version__}",
        f"time_utc: {datetime.now(timezone.utc).isoformat()}",
        f"platform: {platform.platform()}",
        f"python: {sys.version.split()[0]}",
        f"executable: {sys.executable}",
    ]
    if upstream is not None:
        env_lines.append(f"upstream: {upstream.root}")
        for name, commit in sorted(upstream.commits.items()):
            env_lines.append(f"pin_{name}: {commit}")
    zadig = repo_root() / "vendor" / "zadig" / "zadig-2.9.exe"
    if zadig.is_file():
        env_lines.append(f"zadig_sha256: {_sha256(zadig)}")

    checks = doctor.run(upstream) if upstream is not None else []

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("PRIVACY.txt", PRIVACY)
        archive.writestr("env.txt", "\n".join(env_lines) + "\n")
        archive.writestr("doctor.txt", doctor.format_checks(checks) + "\n")
        if extra:
            archive.writestr("extra.json", json.dumps(extra, indent=2, ensure_ascii=False) + "\n")

        run_dirs = sorted(
            (path for path in runs_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:max_runs]
        for run in run_dirs:
            for name in RUN_FILES:
                path = run / name
                if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                    archive.write(path, f"runs/{run.name}/{name}")
            session_state = run / "session" / "state.json"
            if session_state.is_file() and session_state.stat().st_size <= 256 * 1024:
                archive.write(session_state, f"runs/{run.name}/session/state.json")
    return target
