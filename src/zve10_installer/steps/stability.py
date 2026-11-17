"""Read-only USB stability test before any write.

Repeatedly inspects the camera for at least ``seconds`` seconds and requires at
least ``minimum_passes`` identical results. Each inspect reads the complete
library, both Backup files and the three properties, so a flaky cable or port
shows up before the long backup or the write.
"""

from __future__ import annotations

import time

from ..errors import GateError


def evaluate_passes(passes: list[tuple[str, dict]], minimum: int = 2) -> tuple[str, bool]:
    if len(passes) < minimum:
        return f"only {len(passes)} pass(es); need at least {minimum}", False
    first_hash = passes[0][0]
    first_props = passes[0][1].get("backup")
    for sha, result in passes[1:]:
        if sha != first_hash:
            return "library hash changed between passes", False
        if result.get("backup") != first_props:
            return "Backup properties changed between passes", False
    return "stable", True


def run(
    server,
    *,
    initial: dict | None = None,
    seconds: int = 120,
    minimum_passes: int = 2,
    pass_timeout: int = 90,
) -> dict:
    started = time.monotonic()
    passes: list[tuple[str, dict]] = []
    if initial is not None:
        passes.append((str(initial.get("sha256")), initial))

    while True:
        elapsed = time.monotonic() - started
        if len(passes) >= minimum_passes and elapsed >= seconds:
            break
        if elapsed > seconds + pass_timeout:
            raise GateError("stability", "stability test exceeded its time budget")

        pass_started = time.monotonic()
        result = server.submit({"action": "inspect"}, timeout=pass_timeout)
        pass_elapsed = time.monotonic() - pass_started
        if pass_elapsed > pass_timeout:
            raise GateError(
                "stability",
                f"one read took {pass_elapsed:.1f}s (limit {pass_timeout}s)",
            )
        passes.append((str(result.get("sha256")), result))

        message, ok = evaluate_passes(passes, minimum_passes)
        if not ok:
            raise GateError("stability", message)
        if time.monotonic() - started >= seconds and len(passes) >= minimum_passes:
            break
        time.sleep(0.5)

    message, ok = evaluate_passes(passes, minimum_passes)
    if not ok:
        raise GateError("stability", message)
    return {
        "passes": len(passes),
        "seconds": round(time.monotonic() - started, 1),
        "sha256": passes[0][0],
        "backup": passes[0][1].get("backup"),
    }
