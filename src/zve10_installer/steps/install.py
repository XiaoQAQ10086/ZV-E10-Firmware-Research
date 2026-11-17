"""Guided install: precondition check + backup, then explicit confirmation and write.

The actual stateful flow lives in ``InstallSession`` so the GUI can reuse it and
pause between the precondition checklist and the write confirmation.
"""

from __future__ import annotations

from pathlib import Path

from .. import doctor, gates
from ..errors import InstallerError, PreflightError
from ..prompts import confirm_exact
from ..upstream import Upstream
from .install_session import InstallSession


def _format_facts(facts: dict) -> str:
    props = facts.get("backup") or {}
    lines = [
        "Preconditions passed:",
        "  camera: authenticated Jiritsu session",
        f"  firmware: {facts.get('firmware')}",
        f"  library: {facts.get('library')} ({str(facts.get('sha256'))[:16]}...)",
        f"  properties: {props.get('0x1071c54')}/{props.get('0xa5000b')}/{props.get('0xa5000c')}",
        "  /usr: checked by inspect (must be ro)",
        f"  region: {facts.get('region')}",
        f"  backup: {facts.get('backup_dir')}",
    ]
    return "\n".join(lines)


def run(
    upstream: Upstream,
    runs_dir: Path,
    *,
    firmware: str = "2.03",
    backup_passes: int = 1,
    backup_copy: Path | None = None,
    stability_seconds: int = 120,
    battery_percent: int | None = None,
) -> dict:
    checks = doctor.run(upstream)
    if doctor.has_failures(checks):
        raise PreflightError("doctor reported required failures:\n" + doctor.format_checks(checks))
    camera = next((check for check in checks if check.name == "camera_usb"), None)
    if camera is None or not camera.ok:
        raise PreflightError(
            "camera 054c not enumerated; connect it in Mass Storage mode and "
            "make sure WinUSB is bound"
        )

    confirm_exact(
        gates.CHINA_REGION,
        "Confirm the camera will be used in mainland China (B=2 / C=22).",
    )

    session = InstallSession(
        upstream,
        runs_dir,
        firmware=firmware,
        backup_passes=backup_passes,
        backup_copy=backup_copy,
        stability_seconds=stability_seconds,
        battery_percent=battery_percent,
    )
    try:
        facts = session.prepare(gates.CHINA_REGION)
        print(_format_facts(facts))
        confirm_exact(
            f"PATCH ZV-E10 {firmware}",
            "This writes one byte to /usr/lib/CautionConfig.so and three Backup properties.",
        )
        return session.execute()
    except InstallerError:
        session.close()
        raise
