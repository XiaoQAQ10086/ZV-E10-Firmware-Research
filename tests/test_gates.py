from zve10_installer import gates

MOUNTS = """rootfs / rootfs rw 0 0
/dev/nflasha7 / ext2 ro,relatime 0 0
/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
/dev/nflasha10 /tmp vfat rw 0 0
"""


def inspect_result(**overrides):
    base = {
        "size": gates.SIZE,
        "sha256": gates.FACTORY,
        "mounts": MOUNTS,
        "backup": {"0x1071c54": "00", "0xa5000b": "09", "0xa5000c": "09"},
    }
    base.update(overrides)
    return base


def test_model_firmware_accepts_known_pairs():
    for version in gates.SUPPORTED_FIRMWARE:
        assert gates.check_model_firmware([version, version]).ok


def test_model_firmware_rejects_mismatch_and_unknown():
    assert not gates.check_model_firmware(["30110_06.2026060501", "30110_05.2025031501"]).ok
    assert not gates.check_model_firmware(["unknown", "unknown"]).ok
    assert not gates.check_model_firmware(["30110_06.2026060501"]).ok


def test_prewrite_accepts_factory_and_patched():
    assert gates.check_prewrite(inspect_result()).ok
    assert gates.check_prewrite(inspect_result(sha256=gates.PATCHED)).ok


def test_prewrite_rejects_unknown_hash_and_bad_mount():
    assert not gates.check_prewrite(inspect_result(sha256="00" * 32)).ok
    bad = inspect_result(mounts="/dev/nflasha15 /usr ext2 rw 0 0\n")
    assert not gates.check_prewrite(bad).ok


def test_patch_result_requires_exact_hash_size_and_offset():
    good = {"sha256": gates.PATCHED, "size": gates.SIZE, "only_difference": "0xd778e4"}
    assert gates.check_patch_result(good).ok
    assert not gates.check_patch_result({**good, "only_difference": "0x0"}).ok
    assert not gates.check_patch_result({**good, "sha256": gates.FACTORY}).ok


def test_property_result_requires_match():
    assert gates.check_property_result({"match": True}).ok
    assert not gates.check_property_result({"match": False}).ok


def test_close_flags_require_teardown():
    good = {"state": "closed", "service_returned": True, "loader_files_removed": True}
    assert gates.check_close_flags(good).ok
    assert not gates.check_close_flags({**good, "loader_files_removed": False}).ok
    assert not gates.check_close_flags({**good, "state": "ready"}).ok


def test_post_boot_requires_type_nb_and_five_items():
    assert gates.check_post_boot({"page1": {"type": "TypeNB", "count": 5}}).ok
    assert not gates.check_post_boot({"page1": {"type": "TypeRK", "count": 4}}).ok
    assert not gates.check_post_boot({"page1": {"type": "TypeNB", "count": 4}}).ok


def test_region_only_china():
    assert gates.check_region("CN-B2C22").ok
    assert not gates.check_region("US").ok


def test_baseline_properties():
    assert gates.check_baseline_properties(gates.BASELINE_PROPERTIES).ok
    assert not gates.check_baseline_properties(gates.TARGET_PROPERTIES).ok
    partial = {"0x1071c54": "01", "0xa5000b": "09", "0xa5000c": "09"}
    assert not gates.check_baseline_properties(partial).ok


def test_installed_state():
    good = inspect_result(sha256=gates.PATCHED, backup=dict(gates.TARGET_PROPERTIES))
    assert gates.check_installed_state(good).ok
    assert not gates.check_installed_state(inspect_result()).ok
    assert not gates.check_installed_state(inspect_result(sha256=gates.PATCHED)).ok
    bad_mount = inspect_result(
        sha256=gates.PATCHED,
        backup=dict(gates.TARGET_PROPERTIES),
        mounts="/dev/nflasha15 /usr ext2 rw 0 0\n",
    )
    assert not gates.check_installed_state(bad_mount).ok


def test_backup_result():
    assert gates.check_backup_result({"completed": True, "backup_dir": "/x"}).ok
    assert not gates.check_backup_result({"completed": False, "backup_dir": "/x"}).ok
    assert not gates.check_backup_result({"completed": True, "cancelled": True, "backup_dir": "/x"}).ok
    assert not gates.check_backup_result({"completed": True}).ok
