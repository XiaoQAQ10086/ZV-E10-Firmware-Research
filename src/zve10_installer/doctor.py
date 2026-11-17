"""Environment and device checks for v0.1.

Doctor is read-only: it enumerates USB and, if a camera is present, tries to
read its active configuration. It never opens a service session and never
writes to the camera.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import upstream as upstream_mod


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _check_modules() -> Check:
    required = ["usb", "Cryptodome", "asn1crypto", "yaml", "tlslite", "serial"]
    if sys.platform == "win32":
        required.append("libusb_package")
    missing = [name for name in required if not _module(name)]
    if missing:
        return Check("python_deps", False, "missing: " + ", ".join(missing))
    return Check("python_deps", True, ", ".join(required))


def run(up: upstream_mod.Upstream | None) -> list[Check]:
    checks: list[Check] = []

    checks.append(
        Check(
            "platform",
            sys.platform in {"win32", "darwin", "linux"},
            f"{sys.platform} (v0.1 is validated on Windows only)",
            required=True,
        )
    )

    checks.append(
        Check(
            "python",
            sys.version_info >= (3, 10),
            f"{sys.version.split()[0]} (need 3.10+)",
            required=True,
        )
    )

    checks.append(_check_modules())

    if up is None:
        checks.append(Check("upstream", False, "not located; pass --upstream", required=True))
    else:
        checks.append(Check("upstream", True, str(up.root), required=True))
        for name, actual, expected, required in upstream_mod.pin_report(up):
            checks.append(
                Check(
                    f"pin_{name}",
                    actual == expected,
                    f"{actual or 'unknown'} (expected {expected})",
                    required=required,
                )
            )

    checks.append(
        Check(
            "git",
            shutil.which("git") is not None,
            shutil.which("git") or "git not on PATH",
            required=False,
        )
    )

    if up is not None:
        try:
            import usb.core  # type: ignore

            device = usb.core.find(idVendor=0x054C)
        except Exception as exc:
            checks.append(Check("camera_usb", False, repr(exc), required=False))
        else:
            if device is None:
                checks.append(Check("camera_usb", False, "054c: absent", required=False))
            else:
                checks.append(
                    Check("camera_usb", True, f"{device.idVendor:04x}:{device.idProduct:04x}", required=False)
                )
                try:
                    all_sony = usb.core.find(find_all=True, idVendor=0x054C)
                    pids = sorted({f"{item.idProduct:04x}" for item in all_sony})
                except Exception:
                    pids = [f"{device.idProduct:04x}"]
                checks.append(
                    Check(
                        "sony_pids",
                        True,
                        ", ".join(pids) if pids else "none",
                        required=False,
                    )
                )
                try:
                    config = device.get_active_configuration()
                except Exception as exc:
                    checks.append(Check("winusb_open", False, repr(exc), required=False))
                    checks.append(Check("mass_storage", False, "configuration unreadable", required=False))
                else:
                    checks.append(Check("winusb_open", True, "configuration readable", required=False))
                    try:
                        interfaces = list(config)
                        is_mass_storage = any(
                            intf.bInterfaceClass == 0x08 and intf.bInterfaceSubClass == 0x06
                            for intf in interfaces
                        )
                    except Exception as exc:
                        checks.append(Check("mass_storage", False, repr(exc), required=False))
                    else:
                        checks.append(
                            Check(
                                "mass_storage",
                                is_mass_storage,
                                "Mass Storage"
                                if is_mass_storage
                                else "not Mass Storage; set USB connection to Mass Storage",
                                required=False,
                            )
                        )

    runs = Path.cwd()
    checks.append(
        Check(
            "working_dir",
            os.access(runs, os.W_OK),
            f"{runs} writable={os.access(runs, os.W_OK)}",
            required=True,
        )
    )
    return checks


def has_failures(checks: list[Check]) -> bool:
    return any(check.required and not check.ok for check in checks)


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        if check.ok:
            status = "OK"
        else:
            status = "FAIL" if check.required else "WARN"
        lines.append(f"[{status:4}] {check.name}: {check.detail}")
    return "\n".join(lines)


def checks_as_dict(checks: list[Check]) -> list[dict]:
    return [check.__dict__ for check in checks]
