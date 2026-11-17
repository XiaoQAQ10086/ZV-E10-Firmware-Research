"""Full user-area backup step.

The upstream raw-backup action streams the user area plus B0/B1 into the session
directory and writes ``manifest.json`` and ``SHA256SUMS``. This step runs the
upstream verifier against both files before reporting success.
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

from ..errors import GateError
from ..gates import check_backup_result, require
from ..upstream import Upstream


def run(
    server,
    upstream: Upstream,
    run_dir,
    *,
    passes: int = 1,
    chunk_kib: int = 4096,
    timeout: int = 3600,
) -> dict:
    result = server.submit(
        {"action": "raw-backup", "passes": passes, "chunk_kib": chunk_kib},
        timeout=timeout,
    )
    gate = check_backup_result(result)
    run_dir.append_event(
        "backup",
        {
            "completed": result.get("completed"),
            "cancelled": result.get("cancelled"),
            "backup_dir": result.get("backup_dir"),
            "passes": passes,
        },
    )
    require(gate)
    verify(upstream, Path(result["backup_dir"]))
    return result


def verify(upstream: Upstream, backup_dir: Path) -> None:
    manifest = backup_dir / "manifest.json"
    sums = backup_dir / "SHA256SUMS"
    missing = [str(path) for path in (manifest, sums) if not path.is_file()]
    if missing:
        raise GateError("backup_verify", "missing backup files: " + ", ".join(missing))

    script = upstream.host_dir / "zve10_verify.py"
    checks = (
        ("manifest", ["manifest", "--manifest", str(manifest)]),
        ("sums", ["sums", "--sums", str(sums)]),
    )
    for name, args in checks:
        proc = subprocess.run(
            [sys.executable, "-B", str(script), *args],
            cwd=str(upstream.toolkit / "linux"),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise GateError(
                "backup_verify",
                f"{name} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}",
            )


def copy_to_second(source_dir: Path, copy_dir: Path) -> dict:
    """Copy the completed backup to a second, empty directory and verify it."""
    source = Path(source_dir).expanduser().resolve()
    target = Path(copy_dir).expanduser().resolve()
    if not source.is_dir():
        raise GateError("backup_copy", f"backup directory not found: {source}")
    if target == source or source in target.parents or target in source.parents:
        raise GateError(
            "backup_copy",
            "the second backup directory must be outside the session backup directory",
        )
    if target.exists() and any(target.iterdir()):
        raise GateError("backup_copy", f"second backup directory must be empty: {target}")
    target.mkdir(parents=True, exist_ok=True)

    copied: list[dict] = []
    for src in sorted(path for path in source.rglob("*") if path.is_file()):
        rel = src.relative_to(source)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if src.stat().st_size != dst.stat().st_size or not filecmp.cmp(src, dst, shallow=False):
            raise GateError("backup_copy", f"copy verification failed: {rel}")
        copied.append({"name": str(rel), "bytes": src.stat().st_size})

    if not any(Path(entry["name"]).name == "manifest.json" for entry in copied):
        raise GateError("backup_copy", "manifest.json missing from the completed backup")
    return {"backup_copy": str(target), "files": copied}
