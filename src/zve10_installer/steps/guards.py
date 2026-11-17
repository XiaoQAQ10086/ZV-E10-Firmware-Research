"""Checks for leftovers from an interrupted native-helper session.

The upstream patch/WBI helpers are uploaded as ``zve10-wifi-*`` under
``/tmp/jiritsu``. A previous crash can leave one behind; running a new write on
top of that is refused until the owner reviews the old result.

The Jiritsu backend itself creates ``libJit.so``, ``run.sh`` and ``out.txt``
after the session starts and removes them on a clean close. Its own start path
already refuses an existing loader workspace before overwriting, so those three
names are not leftovers during an active session and must not be treated as
such here. Checking them after ``start()`` would reject every legitimate
Jiritsu session.
"""

from __future__ import annotations

from ..errors import GateError

TEMP_PREFIXES = ("zve10-wifi-",)


def evaluate_listing(output: str) -> list[str]:
    names: list[str] = []
    for line in output.splitlines():
        for token in line.split():
            token = token.strip()
            if token and token not in {".", ".."}:
                names.append(token)
    return [
        name
        for name in names
        if any(name == prefix or name.startswith(prefix) for prefix in TEMP_PREFIXES)
    ]


def check(session) -> dict:
    listing = session.submit(
        {"action": "shell", "command": "busybox ls /tmp/jiritsu"},
        timeout=60,
    )
    if listing.get("exit_code") == 0:
        leftovers = evaluate_listing(str(listing.get("output", "")))
        if leftovers:
            raise GateError(
                "temp_guard",
                "leftover temporary files in /tmp/jiritsu: "
                + ", ".join(leftovers)
                + "; review the previous result instead of retrying",
            )

    preload = session.submit(
        {"action": "shell", "command": "busybox cat /etc/ld.so.preload"},
        timeout=60,
    )
    if preload.get("exit_code") == 0 and str(preload.get("output", "")).strip():
        raise GateError(
            "temp_guard",
            "/etc/ld.so.preload is non-empty; stop and review before writing",
        )
    return {"leftovers": [], "preload": ""}
