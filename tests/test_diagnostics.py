from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from zve10_installer import paths
from zve10_installer.steps import diagnostics
from zve10_installer.steps.install_session import InstallSession


def test_diagnostics_includes_failure_and_gui_log(tmp_path: Path) -> None:
    runs = tmp_path / "backup" / "runs"
    run = runs / "20260101-000000-install-test"
    (run / "session").mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"stage": "patched"}), encoding="utf-8")
    (run / "run.jsonl").write_text('{"event":"failure"}\n', encoding="utf-8")
    (run / "failure.json").write_text('{"error":"boom"}\n', encoding="utf-8")
    (run / "session" / "state.json").write_text('{"state":"failed"}', encoding="utf-8")
    logs = tmp_path / "backup" / "logs"
    logs.mkdir(parents=True)
    (logs / "gui-20260101-000000.log").write_text("clicked start\n", encoding="utf-8")

    bundle = diagnostics.create_bundle(runs, None)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
    assert f"runs/{run.name}/failure.json" in names
    assert f"runs/{run.name}/run.jsonl" in names
    assert f"runs/{run.name}/session/state.json" in names
    assert "logs/gui-20260101-000000.log" in names
    assert "doctor.txt" in names


def test_logs_dir_uses_portable_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZVE10_DATA_DIR", str(tmp_path))
    assert paths.logs_dir() == tmp_path.resolve() / "logs"


def test_install_failure_is_recorded(tmp_path: Path) -> None:
    upstream = SimpleNamespace(root=tmp_path / "upstream")
    session = InstallSession(upstream, tmp_path / "runs", battery_confirmed=True)
    with pytest.raises(AttributeError):
        session.prepare("CN-B2C22")
    failure = session.run_dir.path / "failure.json"
    assert failure.is_file()
    data = json.loads(failure.read_text(encoding="utf-8"))
    assert data["error"]
    assert "Traceback" in data["traceback"]
