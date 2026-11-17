from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from zve10_installer.errors import InstallerError
from zve10_installer.steps import sound


def _make_backup(folder: Path, monkeypatch) -> None:
    folder.mkdir(parents=True)
    hashes = {}
    for index, name in enumerate(sound.SHUTTER_FILES):
        data = bytes([index + 1]) * 32
        (folder / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(sound, "ORIGINAL_SHA", hashes)


def test_sound_session_write_method_is_not_shadowed(tmp_path: Path) -> None:
    session = sound.SoundSession(None, tmp_path / "runs", write=True)
    assert session.write_mode is True
    assert callable(session.write)
    read_only = sound.SoundSession(None, tmp_path / "runs", write=False)
    assert read_only.write_mode is False
    assert callable(read_only.write)


def test_original_plan_accepts_complete_factory_set(tmp_path: Path, monkeypatch) -> None:
    _make_backup(tmp_path / "original", monkeypatch)
    plan = sound.original_plan(tmp_path / "original")
    assert [item["name"] for item in plan] == list(sound.SHUTTER_FILES)
    assert all(item["sha256"] for item in plan)


def test_resolve_original_dir_accepts_run_or_original(tmp_path: Path, monkeypatch) -> None:
    _make_backup(tmp_path / "run" / "original", monkeypatch)
    assert sound.resolve_original_dir(tmp_path / "run") == tmp_path / "run" / "original"
    assert sound.resolve_original_dir(tmp_path / "run" / "original") == tmp_path / "run" / "original"


def test_original_plan_rejects_missing_file(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "original"
    _make_backup(folder, monkeypatch)
    (folder / sound.SHUTTER_FILES[0]).unlink()
    with pytest.raises(InstallerError, match="missing"):
        sound.original_plan(folder)


def test_original_plan_rejects_non_factory_file(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "original"
    _make_backup(folder, monkeypatch)
    (folder / sound.SHUTTER_FILES[0]).write_bytes(b"\xff" * 32)
    with pytest.raises(InstallerError, match="not factory original"):
        sound.original_plan(folder)


def test_restore_all_preflights_before_opening_a_session(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "original"
    _make_backup(folder, monkeypatch)
    (folder / sound.SHUTTER_FILES[0]).unlink()

    class Boom:
        def __init__(self, *args, **kwargs):
            raise AssertionError("SoundSession must not be constructed before preflight")

    monkeypatch.setattr(sound, "SoundSession", Boom)
    with pytest.raises(InstallerError, match="missing"):
        sound.restore_all(None, tmp_path / "runs", original_dir=folder)
