"""One-byte CautionConfig.so patch step."""

from __future__ import annotations

from ..gates import check_patch_result, require


def run(server, run_dir, *, timeout: int = 420) -> dict:
    result = server.submit({"action": "patch"}, timeout=timeout)
    gate = check_patch_result(result)
    run_dir.append_event(
        "patch",
        {
            "ok": gate.ok,
            "sha256": result.get("sha256"),
            "size": result.get("size"),
            "only_difference": result.get("only_difference"),
        },
    )
    require(gate)
    return result
