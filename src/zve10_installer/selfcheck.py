"""Offline package self-check. No camera access."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .platform_compat import repo_root
from .upstream import Upstream, pin_report

PATCH_HELPER = "f8270987db52912e987d2a8c8fd7576096085571a1aa5de73bc98fe21c865ea6"
RESTORE_HELPER = "ae3ce7d823a4e19a162befd236db9af99f222bc3b48a44468288b62888a7f712"
ZADIG_SIZE = 5_334_088
ZADIG_HASH = "4ecaa95df3da3621486a043aef8b3050b8bafe7c901402871e816229ef82039b"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(upstream: Upstream) -> list[Check]:
    checks: list[Check] = [
        Check("upstream", True, str(upstream.root)),
    ]
    for name, actual, expected, required in pin_report(upstream):
        checks.append(Check(f"pin_{name}", actual == expected, f"{actual} (expected {expected})", required))

    for helper, expected in (
        ("patch.arm", PATCH_HELPER),
        ("restore.arm", RESTORE_HELPER),
    ):
        path = upstream.root / "tools" / helper
        if not path.is_file():
            checks.append(Check(helper, False, "missing", True))
        else:
            checks.append(Check(helper, _sha256(path) == expected, path.name, True))

    checks.append(Check("tools/wifi.py", (upstream.root / "tools" / "wifi.py").is_file(), "present"))
    checks.append(Check("tools/wbi.py", (upstream.root / "tools" / "wbi.py").is_file(), "present"))

    compat = repo_root() / "compat" / "windows" / "sitecustomize.py"
    checks.append(Check("windows_shim", compat.is_file(), str(compat), False))

    zadig = repo_root() / "vendor" / "zadig" / "zadig-2.9.exe"
    if zadig.is_file():
        size = zadig.stat().st_size
        checks.append(
            Check(
                "zadig",
                size == ZADIG_SIZE and _sha256(zadig) == ZADIG_HASH,
                f"{size} bytes",
                True,
            )
        )
    else:
        checks.append(Check("zadig", True, "not bundled (CLI build)", False))
    return checks


def has_failures(checks: list[Check]) -> bool:
    return any(check.required and not check.ok for check in checks)


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else ("FAIL" if check.required else "WARN")
        lines.append(f"[{status:4}] {check.name}: {check.detail}")
    return "\n".join(lines)
