import pytest

from zve10_installer.errors import InstallerError
from zve10_installer.state import RunState, Stage


def test_advance_and_persist(tmp_path):
    path = tmp_path / "state.json"
    state = RunState.load_or_create(path)
    state.advance(Stage.ENV_READY)
    state.advance(Stage.CONNECTED)
    state.advance(Stage.INSPECTED, {"sha256": "abc"})
    loaded = RunState.load_or_create(path)
    assert loaded.stage is Stage.INSPECTED
    assert loaded.facts["sha256"] == "abc"
    assert len(loaded.history) == 3


def test_invalid_transition_is_rejected(tmp_path):
    state = RunState.load_or_create(tmp_path / "state.json")
    with pytest.raises(InstallerError):
        state.advance(Stage.PATCHED)


def test_stopped_is_terminal(tmp_path):
    state = RunState.load_or_create(tmp_path / "state.json")
    state.advance(Stage.STOPPED)
    with pytest.raises(InstallerError):
        state.advance(Stage.CONNECTED)


def test_unknown_requires_recovery_review(tmp_path):
    state = RunState.load_or_create(tmp_path / "state.json")
    for stage in (Stage.ENV_READY, Stage.CONNECTED, Stage.INSPECTED, Stage.SCOPE_CONFIRMED, Stage.BACKUP_DONE, Stage.PREWRITE_INSPECTED, Stage.PATCHED):
        state.advance(stage)
    state.advance(Stage.UNKNOWN)
    with pytest.raises(InstallerError):
        state.advance(Stage.PATCHED)
    state.advance(Stage.RECOVERY_REQUIRED)
