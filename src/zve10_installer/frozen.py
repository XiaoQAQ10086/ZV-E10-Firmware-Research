"""Frozen-build helpers.

A PyInstaller build runs the installer from an extracted directory. The
upstream ``wifi.py serve`` process is launched by re-running the same executable
with ``__serve``; this module reconstructs the upstream import paths and calls
``wifi.main()`` with a synthetic ``sys.argv``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import platform_compat


def serve_upstream(args: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--upstream-root", required=True)
    known, rest = parser.parse_known_args(args)

    root = Path(known.upstream_root).resolve()
    paths = [
        root / "tools",
        root / "vendor" / "zv-e10-toolkit" / "linux" / "host",
        root / "vendor" / "zv-e10-toolkit" / "linux" / "vendor" / "Sony-PMCA-RE",
        platform_compat.compat_dir(),
    ]
    for path in reversed(paths):
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))

    platform_compat.activate()

    import wifi  # type: ignore  # upstream tools/wifi.py

    forwarded = rest if rest and rest[0] == "serve" else ["serve", *rest]
    sys.argv = ["wifi.py", *forwarded]
    wifi.main()
    return 0


def serve_sound_upstream(args: list[str]) -> int:
    """Frozen entry for the sound wrapper server."""
    from .sound_server import main as sound_main

    return sound_main(args)
