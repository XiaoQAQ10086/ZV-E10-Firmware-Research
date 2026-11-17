"""Compare the complete Backup database before and after the property writes.

Target keys must become 01/02/16. Every other property must be byte-identical,
except for keys that already changed during the read-only preparation window
(typically runtime counters). Those are recorded and allowed to move again.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from ..errors import GateError
from ..upstream import Upstream

TARGET = {
    0x01071C54: b"\x01",
    0x00A5000B: b"\x02",
    0x00A5000C: b"\x16",
}


def _properties(upstream: Upstream, path: Path) -> dict[int, tuple[int, bytes]]:
    pmca = str(upstream.pmca)
    if pmca not in sys.path:
        sys.path.insert(0, pmca)
    from pmca.backup import BackupFile  # type: ignore

    try:
        backup = BackupFile(io.BytesIO(Path(path).read_bytes()))
    except Exception as exc:
        raise GateError("preservation", f"cannot parse {Path(path).name}: {exc}") from exc
    return {
        key: (prop.attr, bytes(prop.data))
        for key, prop in backup.listProperties()
    }


def _pair(
    upstream: Upstream,
    before_paths: list[Path],
    after_paths: list[Path],
) -> tuple[dict[int, tuple[int, bytes]], dict[int, tuple[int, bytes]]]:
    errors: list[str] = []
    for before_path, after_path in zip(before_paths, after_paths):
        try:
            return _properties(upstream, before_path), _properties(upstream, after_path)
        except GateError as exc:
            errors.append(str(exc))
    raise GateError("preservation", "no parseable Backup pair: " + "; ".join(errors))


def changed_keys(
    upstream: Upstream,
    before_paths: list[Path],
    after_paths: list[Path],
    target: dict[int, bytes] = TARGET,
) -> set[int]:
    before, after = _pair(upstream, before_paths, after_paths)
    if set(before) != set(after):
        raise GateError("preservation", "Backup property set changed during preparation")
    changed: set[int] = set()
    for key in before:
        b_attr, b_data = before[key]
        a_attr, a_data = after[key]
        if key in target:
            if (a_attr, a_data) != (b_attr, b_data):
                raise GateError(
                    "preservation",
                    f"target property {key:#x} changed during preparation",
                )
            continue
        if (a_attr, a_data) != (b_attr, b_data):
            changed.add(key)
    return changed


def compare(
    upstream: Upstream,
    before_paths: list[Path],
    after_paths: list[Path],
    allowed_keys: set[int] | None = None,
    target: dict[int, bytes] = TARGET,
) -> dict:
    before, after = _pair(upstream, before_paths, after_paths)
    if set(before) != set(after):
        raise GateError("preservation", "Backup property set changed after writing")

    allowed = allowed_keys or set()
    changed: list[dict] = []
    for key in before:
        b_attr, b_data = before[key]
        a_attr, a_data = after[key]
        if key in target:
            if a_data != target[key] or a_attr != b_attr:
                raise GateError(
                    "preservation",
                    f"target property {key:#x} is not the expected value",
                )
            continue
        if (a_attr, a_data) != (b_attr, b_data) and key not in allowed:
            changed.append(
                {
                    "key": hex(key),
                    "before": b_data.hex()[:64],
                    "after": a_data.hex()[:64],
                    "bytes": len(a_data),
                }
            )

    if changed:
        raise GateError(
            "preservation",
            "unexpected non-target changes: " + json.dumps(changed[:10]),
        )
    return {"properties": len(before), "allowed_changes": len(allowed)}
