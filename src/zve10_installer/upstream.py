"""Locate and verify a pinned upstream checkout.

The installer never clones, updates, or edits upstream. It only accepts a local
checkout whose toolkit and Sony-PMCA-RE revisions match the pins below, then
invokes the upstream ``tools/wifi.py`` with that checkout's own code.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PreflightError
from .platform_compat import compat_dir, frozen_root

EXPECTED_MAIN = "9def1681ee20a88f26daaf7ae43f4dbc51b43b2d"
EXPECTED_TOOLKIT = "373bd482f9ef4e54ecaf5faf00e0afcbb4f041de"
EXPECTED_PMCA = "a82f5baaa8e9c3d9f28f94699e860fb2e48cc8e0"


@dataclass(frozen=True)
class Upstream:
    root: Path
    toolkit: Path
    pmca: Path
    host_dir: Path
    wifi_py: Path
    commits: dict[str, str | None] = field(default_factory=dict)

    @property
    def compat_dir(self) -> Path:
        return compat_dir()

    def pythonpath(self) -> str:
        entries = [str(self.compat_dir), str(self.pmca)]
        existing = os.environ.get("PYTHONPATH")
        if existing:
            entries.append(existing)
        return os.pathsep.join(entries)


def _is_upstream(root: Path) -> bool:
    return (
        (root / "tools" / "wifi.py").is_file()
        and (root / "vendor" / "zv-e10-toolkit" / "linux" / "host" / "zve10_terminal_client.py").is_file()
    )


def _git_head(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _candidates(explicit: str | Path | None) -> list[Path]:
    found: list[Path] = []
    if explicit:
        found.append(Path(explicit))
    env = os.environ.get("ZVE10_UPSTREAM")
    if env:
        found.append(Path(env))
    frozen = frozen_root()
    if frozen is not None:
        found.append(frozen / "upstream")
    cwd = Path.cwd()
    found.extend(
        [
            cwd,
            cwd / "unlock",
            cwd.parent / "unlock",
            cwd.parent / "5ghz-unlock" / "unlock",
        ]
    )
    return found


def locate(explicit: str | Path | None = None) -> Upstream:
    """Find a usable upstream checkout, or raise PreflightError."""
    seen: set[Path] = set()
    for candidate in _candidates(explicit):
        try:
            root = candidate.expanduser().resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        if _is_upstream(root):
            return from_path(root)
    raise PreflightError(
        "No upstream checkout found. Pass --upstream <path-to-unlock> or set "
        "ZVE10_UPSTREAM. Expected tools/wifi.py and the pinned toolkit checkout."
    )


def _read_pins(root: Path) -> dict:
    path = root / "PIN.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def from_path(root: str | Path) -> Upstream:
    root = Path(root).expanduser().resolve()
    if not _is_upstream(root):
        raise PreflightError(
            f"{root} does not look like the ZV-E10-5GHz-WiFi-Unlock checkout "
            "(missing tools/wifi.py or the toolkit client)."
        )
    toolkit = root / "vendor" / "zv-e10-toolkit"
    host_dir = toolkit / "linux" / "host"
    pmca = toolkit / "linux" / "vendor" / "Sony-PMCA-RE"
    if not (host_dir / "zve10_common.py").is_file():
        raise PreflightError(f"Toolkit host helpers missing under {host_dir}.")
    if not pmca.is_dir():
        raise PreflightError(f"Sony-PMCA-RE checkout missing under {pmca}.")
    pins = _read_pins(root)
    commits = {
        "main": _git_head(root) or pins.get("main"),
        "toolkit": _git_head(toolkit) or pins.get("toolkit"),
        "pmca": _git_head(pmca) or pins.get("pmca"),
    }
    return Upstream(
        root=root,
        toolkit=toolkit,
        pmca=pmca,
        host_dir=host_dir,
        wifi_py=root / "tools" / "wifi.py",
        commits=commits,
    )


def pin_report(upstream: Upstream) -> list[tuple[str, str | None, str, bool]]:
    """Return (name, actual, expected, required) pin checks for doctor."""
    return [
        ("main", upstream.commits.get("main"), EXPECTED_MAIN, False),
        ("toolkit", upstream.commits.get("toolkit"), EXPECTED_TOOLKIT, True),
        ("pmca", upstream.commits.get("pmca"), EXPECTED_PMCA, True),
    ]
