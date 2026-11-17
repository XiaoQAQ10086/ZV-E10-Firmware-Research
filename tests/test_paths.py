from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from zve10_installer import paths
from zve10_installer.errors import GateError
from zve10_installer.steps.install_session import InstallSession


def test_portable_data_paths(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "portable-data"
    monkeypatch.setenv("ZVE10_DATA_DIR", str(target))
    assert paths.data_dir() == target.resolve()
    assert paths.default_runs_dir() == target.resolve() / "runs"
    assert paths.second_copy_dir("run-1") == target.resolve() / "second" / "run-1"
    assert paths.ensure_data_dir() == target.resolve()
    assert target.is_dir()


def test_install_session_requires_battery_confirmation(tmp_path: Path) -> None:
    upstream = SimpleNamespace(root=tmp_path / "upstream")
    session = InstallSession(upstream, tmp_path / "runs", battery_confirmed=False)
    with pytest.raises(GateError, match="75%"):
        session.prepare("CN-B2C22")
