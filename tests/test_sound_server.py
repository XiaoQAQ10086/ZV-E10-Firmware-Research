from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from zve10_installer import sound_server


def test_sound_step_module_imports() -> None:
    from zve10_installer.steps import sound

    assert sound.SHUTTER_FILES
    assert sound.ORIGINAL_SHA[sound.SHUTTER_FILES[0]]


class FakeOps:
    def __init__(self, current: bytes) -> None:
        self.current = current
        self.uploaded: dict[str, bytes] = {}
        self.commands: list[str] = []
        self.rw = False

    def check_firmware(self, camera):
        return b"30110_06.2026060501"

    def read_file(self, camera, path: str) -> bytes:
        return self.current

    def save_private(self, folder: Path, name: str, data: bytes) -> None:
        (folder / name).write_bytes(data)

    def upload_verified(self, camera, path: str, data: bytes) -> None:
        self.uploaded[path] = data

    def run(self, camera, command: str) -> str:
        self.commands.append(command)
        if command == "busybox cat /proc/mounts":
            state = "rw" if self.rw else "ro"
            return f"/dev/nflasha15 /usr ext2 {state} 0 0\n"
        if command == "mount -o remount,rw /usr":
            self.rw = True
            return ""
        if command == "mount -o remount,ro /usr":
            self.rw = False
            return ""
        if command.startswith("busybox cp "):
            remote = command.split()[2]
            self.current = self.uploaded[remote]
            return ""
        return ""


DATA = bytes(range(32)) * 38
OTHER = b"\x01" * 32 * 38


def _request(action: str, data: bytes | None = None, expected: str | None = None) -> dict:
    request = {"action": action, "name": "Dslr_Emnt_Shutter_Sha.bin"}
    if data is not None:
        request["data_hex"] = data.hex()
    if expected is not None:
        request["expected_sha256"] = expected
    return request


def test_sound_read_returns_hash_and_snapshot(tmp_path: Path) -> None:
    ops = FakeOps(DATA)
    answer = sound_server._sound_action(None, _request("sound-read"), tmp_path, False, ops)
    assert answer["size"] == len(DATA)
    assert answer["sha256"] == hashlib.sha256(DATA).hexdigest()
    assert bytes.fromhex(answer["data_hex"]) == DATA
    assert (tmp_path / answer["snapshot"]).read_bytes() == DATA


def test_sound_read_missing_is_optional(tmp_path: Path) -> None:
    class Missing(FakeOps):
        def read_file(self, camera, path: str) -> bytes:
            raise RuntimeError("no such file")

    ops = Missing(DATA)
    request = _request("sound-read")
    request["optional"] = True
    answer = sound_server._sound_action(None, request, tmp_path, False, ops)
    assert answer["missing"] is True


def test_sound_write_remounts_and_reads_back(tmp_path: Path) -> None:
    ops = FakeOps(DATA)
    answer = sound_server._sound_action(
        None, _request("sound-write", OTHER, hashlib.sha256(DATA).hexdigest()), tmp_path, True, ops
    )
    assert answer["before_sha256"] == hashlib.sha256(DATA).hexdigest()
    assert answer["after_sha256"] == hashlib.sha256(OTHER).hexdigest()
    assert answer["readonly"] is True
    assert ops.current == OTHER
    assert ops.rw is False
    assert "mount -o remount,rw /usr" in ops.commands
    assert "mount -o remount,ro /usr" in ops.commands
    assert any(cmd.startswith("busybox rm -f /tmp/jiritsu/zve10-wifi-sound-") for cmd in ops.commands)


def test_sound_write_reads_data_file_from_session(tmp_path: Path) -> None:
    token = hashlib.sha256(OTHER).hexdigest()[:16]
    (tmp_path / f"sound-{token}.bin").write_bytes(OTHER)
    ops = FakeOps(DATA)
    request = {
        "action": "sound-write",
        "name": "Dslr_Emnt_Shutter_Sha.bin",
        "data_file": f"sound-{token}.bin",
        "expected_sha256": hashlib.sha256(DATA).hexdigest(),
    }
    answer = sound_server._sound_action(None, request, tmp_path, True, ops)
    assert answer["after_sha256"] == hashlib.sha256(OTHER).hexdigest()
    assert ops.current == OTHER


def test_sound_write_rejects_path_outside_session(tmp_path: Path) -> None:
    ops = FakeOps(DATA)
    request = {
        "action": "sound-write",
        "name": "Dslr_Emnt_Shutter_Sha.bin",
        "data_file": "../outside.bin",
        "expected_sha256": hashlib.sha256(DATA).hexdigest(),
    }
    with pytest.raises(ValueError, match="invalid sound data file"):
        sound_server._sound_action(None, request, tmp_path, True, ops)


def test_sound_write_rejects_hash_mismatch_before_any_write(tmp_path: Path) -> None:
    ops = FakeOps(DATA)
    with pytest.raises(ValueError, match="does not match"):
        sound_server._sound_action(
            None, _request("sound-write", OTHER, hashlib.sha256(OTHER).hexdigest()), tmp_path, True, ops
        )
    assert ops.commands == []
    assert ops.uploaded == {}


def test_sound_write_requires_write_mode(tmp_path: Path) -> None:
    ops = FakeOps(DATA)
    with pytest.raises(ValueError, match="owner-authorized-write"):
        sound_server._sound_action(
            None, _request("sound-write", OTHER, hashlib.sha256(DATA).hexdigest()), tmp_path, False, ops
        )
    assert ops.uploaded == {}


def test_sound_write_readback_mismatch_restores_ro(tmp_path: Path) -> None:
    class BadCopy(FakeOps):
        def run(self, camera, command: str) -> str:
            if command.startswith("busybox cp "):
                self.commands.append(command)
                return ""
            return super().run(camera, command)

    ops = BadCopy(DATA)
    with pytest.raises(RuntimeError, match="readback mismatch"):
        sound_server._sound_action(
            None, _request("sound-write", OTHER, hashlib.sha256(DATA).hexdigest()), tmp_path, True, ops
        )
    assert ops.rw is False
    assert "mount -o remount,ro /usr" in ops.commands
