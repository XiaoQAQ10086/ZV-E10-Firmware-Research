"""Pure gate functions.

Gates take already-collected facts and return a GateResult. They perform no
I/O, so they can be unit-tested without a camera. Callers must refuse to
advance when a required gate fails.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import GateError

SIZE = 17_694_160
FACTORY = "5ad8746a229da259fe00b297e8f897d682f7ae9a13393025b3d1c95a808e68d7"
PATCHED = "14f42cc09ee1b9ddde5352482c13b68e5a5e97d9d79e8456087b5e0b7af6ff6a"
OFFSET = 0xD778E4
SUPPORTED_FIRMWARE = ("30110_05.2025031501", "30110_06.2026060501")
CHINA_REGION = "CN-B2C22"
PROPERTY_KEYS = ("0x1071c54", "0xa5000b", "0xa5000c")


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    detail: str


def require(result: GateResult) -> None:
    if not result.ok:
        raise GateError(result.name, result.detail)


def classify_library(sha256: str) -> str:
    if sha256 == FACTORY:
        return "factory"
    if sha256 == PATCHED:
        return "patched"
    return "unknown"


def check_model_firmware(versions: list[str] | tuple[str, ...]) -> GateResult:
    if len(versions) != 2:
        return GateResult("model_firmware", False, f"expected two version reads, got {len(versions)}")
    if versions[0] != versions[1]:
        return GateResult("model_firmware", False, f"version reads differ: {versions[0]!r} vs {versions[1]!r}")
    if versions[0] not in SUPPORTED_FIRMWARE:
        return GateResult("model_firmware", False, f"unsupported system: {versions[0]!r}")
    return GateResult("model_firmware", True, versions[0])


def check_region(region: str) -> GateResult:
    if region != CHINA_REGION:
        return GateResult("region", False, f"only {CHINA_REGION} is validated; got {region!r}")
    return GateResult("region", True, region)


def _usr_mount(mounts: str) -> list[str] | None:
    rows = [line.split() for line in mounts.splitlines() if line.split()]
    usr = [row for row in rows if len(row) >= 4 and row[1] == "/usr"]
    if len(usr) != 1:
        return None
    return usr[0]


def check_prewrite(result: dict) -> GateResult:
    size = result.get("size")
    if size != SIZE:
        return GateResult("prewrite", False, f"unexpected library size: {size!r}")
    sha = result.get("sha256", "")
    kind = classify_library(sha)
    if kind == "unknown":
        return GateResult("prewrite", False, f"unknown library hash: {sha}")
    mount = _usr_mount(result.get("mounts", ""))
    if mount is None:
        return GateResult("prewrite", False, "expected exactly one /usr mount row")
    if mount[0] != "/dev/nflasha15" or mount[2] != "ext2" or "ro" not in mount[3].split(","):
        return GateResult("prewrite", False, f"unexpected /usr mount: {' '.join(mount)}")
    props = result.get("backup") or {}
    missing = [key for key in PROPERTY_KEYS if key not in props]
    if missing:
        return GateResult("prewrite", False, f"missing Backup properties: {', '.join(missing)}")
    return GateResult("prewrite", True, f"{kind}; properties {props}")


def check_patch_result(result: dict) -> GateResult:
    if result.get("sha256") != PATCHED:
        return GateResult("patch_result", False, f"unexpected patched hash: {result.get('sha256')!r}")
    if result.get("size") != SIZE:
        return GateResult("patch_result", False, f"unexpected size: {result.get('size')!r}")
    if result.get("only_difference") != hex(OFFSET):
        return GateResult("patch_result", False, f"unexpected difference: {result.get('only_difference')!r}")
    return GateResult("patch_result", True, "patched hash, size and unique difference verified")


def check_property_result(result: dict) -> GateResult:
    if result.get("match") is not True:
        return GateResult("property_result", False, f"property write did not match: {result!r}")
    return GateResult("property_result", True, f"{result.get('id')}: {result.get('original')} -> {result.get('value')}")


def check_close_flags(state: dict) -> GateResult:
    if state.get("state") != "closed":
        return GateResult("close_flags", False, f"session state is {state.get('state')!r}")
    if state.get("service_returned") is not True:
        return GateResult("close_flags", False, "service_returned is not true")
    if state.get("loader_files_removed") is not True and state.get("terminal_closed") is not True:
        return GateResult("close_flags", False, "neither loader_files_removed nor terminal_closed is true")
    return GateResult("close_flags", True, "closed, service returned, helper files cleaned")


def check_post_boot(result: dict) -> GateResult:
    page1 = result.get("page1") or {}
    if page1.get("type") != "TypeNB":
        return GateResult("post_boot", False, f"expected TypeNB, got {page1.get('type')!r}")
    if page1.get("count") != 5:
        return GateResult("post_boot", False, f"expected five items, got {page1.get('count')!r}")
    return GateResult("post_boot", True, "Page1 is TypeNB with five items")


BASELINE_PROPERTIES = {
    "0x1071c54": "00",
    "0xa5000b": "09",
    "0xa5000c": "09",
}

TARGET_PROPERTIES = {
    "0x1071c54": "01",
    "0xa5000b": "02",
    "0xa5000c": "16",
}


def check_baseline_properties(props: dict) -> GateResult:
    if props == BASELINE_PROPERTIES:
        return GateResult("baseline_properties", True, "originals are 00/09/09")
    if props == TARGET_PROPERTIES:
        return GateResult(
            "baseline_properties",
            False,
            "already installed (01/02/16); do not patch or write properties again",
        )
    return GateResult(
        "baseline_properties",
        False,
        f"unexpected property values: {props}; stop and review before writing",
    )


def check_backup_result(result: dict) -> GateResult:
    if result.get("completed") is not True:
        return GateResult("backup_result", False, f"backup did not complete: {result!r}")
    if result.get("cancelled"):
        return GateResult("backup_result", False, "backup was cancelled")
    if not result.get("backup_dir"):
        return GateResult("backup_result", False, f"missing backup_dir: {result!r}")
    return GateResult("backup_result", True, str(result.get("backup_dir")))


def check_installed_state(result: dict) -> GateResult:
    if result.get("size") != SIZE:
        return GateResult("installed_state", False, f"unexpected size: {result.get('size')!r}")
    if result.get("sha256") != PATCHED:
        return GateResult("installed_state", False, f"library is not patched: {result.get('sha256')!r}")
    if (result.get("backup") or {}) != TARGET_PROPERTIES:
        return GateResult("installed_state", False, f"unexpected properties: {result.get('backup')!r}")
    mount = _usr_mount(result.get("mounts", ""))
    if mount is None or not _mount_is_expected(mount):
        return GateResult("installed_state", False, "unexpected /usr mount")
    return GateResult("installed_state", True, "patched library, 01/02/16, /usr ro")


def _mount_is_expected(mount: list[str]) -> bool:
    return mount[0] == "/dev/nflasha15" and mount[2] == "ext2" and "ro" in mount[3].split(",")
