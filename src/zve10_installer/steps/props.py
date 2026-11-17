"""Three one-byte Backup property writes."""

from __future__ import annotations

from ..errors import GateError
from ..gates import check_property_result, require

PROPERTIES = (
    ("0x01071C54", "0x1071c54", "01"),
    ("0x00A5000B", "0xa5000b", "02"),
    ("0x00A5000C", "0xa5000c", "16"),
)


def run(server, run_dir, originals: dict, *, timeout: int = 300) -> list[dict]:
    results: list[dict] = []
    for prop_id, inspect_key, value in PROPERTIES:
        expected = originals.get(inspect_key)
        if expected is None:
            raise GateError("properties", f"missing inspected original for {inspect_key}")
        result = server.submit(
            {
                "action": "backup-write",
                "id": prop_id,
                "expected": expected,
                "value": value,
            },
            timeout=timeout,
        )
        gate = check_property_result(result)
        run_dir.append_event(
            "property",
            {
                "id": prop_id,
                "expected": expected,
                "value": value,
                "ok": gate.ok,
            },
        )
        require(gate)
        results.append(result)
    return results
