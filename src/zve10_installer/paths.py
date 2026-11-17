"""Portable application paths.

The distributed build is a zip containing the executables and an empty
``backup/`` directory. Backups and run evidence stay next to the executable, so
the user does not choose a directory. The zip must be extracted to a writable
folder; running an executable directly from the zip archive is not supported.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get("ZVE10_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return app_dir() / "backup"


def default_runs_dir() -> Path:
    return data_dir() / "runs"


def logs_dir() -> Path:
    return data_dir() / "logs"


def second_copy_dir(run_name: str) -> Path:
    return data_dir() / "second" / run_name


def ensure_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write-test"
    probe.write_text("ok", encoding="ascii")
    probe.unlink()
    return path
