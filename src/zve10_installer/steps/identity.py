"""Stable per-body identifier derived from the Backup serial property.

The raw serial is never stored; only a truncated SHA-256 hash is kept in state
and summaries so a backup can be tied to this body without exposing the serial.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

from ..errors import GateError
from ..upstream import Upstream

SERIAL_KEY = 0x00E70003


def body_id(upstream: Upstream, backup_path: Path) -> str:
    pmca = str(upstream.pmca)
    if pmca not in sys.path:
        sys.path.insert(0, pmca)
    from pmca.backup import BackupFile  # type: ignore

    try:
        backup = BackupFile(io.BytesIO(Path(backup_path).read_bytes()))
    except Exception as exc:
        raise GateError("identity", f"cannot parse {Path(backup_path).name}: {exc}") from exc
    properties = dict(backup.listProperties())
    prop = properties.get(SERIAL_KEY)
    if prop is None or not prop.data:
        raise GateError("identity", "Backup serial property 0x00e70003 is missing")
    return hashlib.sha256(bytes(prop.data)).hexdigest()[:16]
