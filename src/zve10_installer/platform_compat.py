"""Host compatibility helpers.

On Windows, the pinned upstream host tools assume a POSIX uid and a working
libusb backend. The compatibility shim under ``compat/windows`` supplies the
minimal stubs and a libusb backend; it is injected through ``sys.path`` /
``PYTHONPATH`` only. No upstream file is ever modified.

In a PyInstaller build, ``sys._MEIPASS`` contains ``upstream/`` and
``compat/``; the same helpers resolve against that extraction directory.
"""

from __future__ import annotations

import sys
from pathlib import Path


def frozen_root() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    root = Path(base)
    if (root / "upstream").is_dir() or (root / "compat" / "windows").is_dir():
        return root
    return None


def repo_root() -> Path:
    frozen = frozen_root()
    if frozen is not None:
        return frozen
    return Path(__file__).resolve().parents[2]


def compat_dir() -> Path:
    return repo_root() / "compat" / "windows"


def is_read_only_build() -> bool:
    """A frozen build may ship a ``READ_ONLY`` marker to hide write commands."""
    frozen = frozen_root()
    return bool(frozen is not None and (frozen / "READ_ONLY").is_file())


def activate() -> None:
    """Activate the Windows shim in this process, if applicable."""
    if sys.platform != "win32":
        return
    compat = compat_dir()
    if compat.is_dir():
        entry = str(compat)
        if entry not in sys.path:
            sys.path.insert(0, entry)
    try:
        import sitecustomize as _shim

        apply_shim = getattr(_shim, "apply", None)
        if apply_shim is not None:
            apply_shim()
    except Exception:
        # The shim is best-effort; doctor will report the actual failure.
        pass
