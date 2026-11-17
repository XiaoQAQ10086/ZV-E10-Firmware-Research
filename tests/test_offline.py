from pathlib import Path
import json
import zipfile

import pytest

from zve10_installer.evidence import RunDir
from zve10_installer import history, upstream
from zve10_installer.errors import GateError
from zve10_installer.gates import check_close_flags
from zve10_installer.steps import backup, diagnostics, guards, runtime, stability


def make_fake_upstream(root: Path) -> Path:
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "wifi.py").write_text("# fake\n", encoding="utf-8")
    host = root / "vendor" / "zv-e10-toolkit" / "linux" / "host"
    host.mkdir(parents=True)
    (host / "zve10_terminal_client.py").write_text("# fake\n", encoding="utf-8")
    (host / "zve10_common.py").write_text("# fake\n", encoding="utf-8")
    pmca = root / "vendor" / "zv-e10-toolkit" / "linux" / "vendor" / "Sony-PMCA-RE"
    pmca.mkdir(parents=True)
    return root


def test_locate_fake_checkout(tmp_path):
    root = make_fake_upstream(tmp_path / "unlock")
    found = upstream.locate(root)
    assert found.root == root.resolve()
    assert found.wifi_py.name == "wifi.py"
    assert found.commits["toolkit"] is None  # not a git checkout


def test_run_dir_is_unique_and_writable(tmp_path):
    first = RunDir.create(tmp_path, "inspect")
    second = RunDir.create(tmp_path, "inspect")
    assert first.path != second.path
    first.write_json("summary.json", {"ok": True})
    assert (first.path / "summary.json").is_file()
    first.append_event("test", {"ok": True})
    assert (first.path / "run.jsonl").read_text(encoding="utf-8").strip()


def test_close_flags_are_a_gate():
    assert check_close_flags(
        {"state": "closed", "service_returned": True, "loader_files_removed": True}
    ).ok
    assert not check_close_flags({"state": "closed"}).ok


def test_stability_evaluation():
    same = [
        ("abc", {"backup": {"0x1": "00"}}),
        ("abc", {"backup": {"0x1": "00"}}),
    ]
    assert stability.evaluate_passes(same, 2)[1]
    assert not stability.evaluate_passes([same[0]], 2)[1]
    changed_hash = [same[0], ("def", {"backup": {"0x1": "00"}})]
    assert not stability.evaluate_passes(changed_hash, 2)[1]
    changed_props = [same[0], ("abc", {"backup": {"0x1": "01"}})]
    assert not stability.evaluate_passes(changed_props, 2)[1]


def test_temp_file_listing_guard():
    # libJit.so, run.sh and out.txt belong to the active Jiritsu backend; only
    # an uploaded helper left behind by an interrupted action is a leftover.
    output = "libJit.so\nrun.sh\nzve10-wifi-patch\nordinary.txt\nout.txt\n"
    assert guards.evaluate_listing(output) == ["zve10-wifi-patch"]
    assert guards.evaluate_listing("libJit.so\nrun.sh\nout.txt\n") == []
    assert guards.evaluate_listing("ordinary.txt\n") == []


def test_second_backup_copy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text("{}", encoding="utf-8")
    (source / "SHA256SUMS").write_text("0  file\n", encoding="utf-8")
    (source / "image.bin").write_bytes(b"data" * 1024)

    target = tmp_path / "copy"
    result = backup.copy_to_second(source, target)
    assert result["backup_copy"] == str(target.resolve())
    assert (target / "image.bin").read_bytes() == (source / "image.bin").read_bytes()

    (target / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(GateError):
        backup.copy_to_second(source, target)

    nested = source / "nested"
    with pytest.raises(GateError):
        backup.copy_to_second(source, nested)


def test_diagnostics_bundle_excludes_backups(tmp_path):
    runs = tmp_path / "runs"
    run = runs / "20260101-test"
    run.mkdir(parents=True)
    (run / "state.json").write_text("{}", encoding="utf-8")
    (run / "serve.out").write_text("log", encoding="utf-8")
    session = run / "session"
    session.mkdir()
    (session / "state.json").write_text("{}", encoding="utf-8")
    (run / "nflasha.read1.bin").write_bytes(b"backup")

    path = diagnostics.create_bundle(runs, None)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert "PRIVACY.txt" in names
    assert "env.txt" in names
    assert any(name.endswith("state.json") for name in names)
    assert not any(name.endswith(".bin") for name in names)


def test_history_latest_marks_unfinished(tmp_path):
    runs = tmp_path / "runs"
    run = runs / "20260101-install"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps(
            {
                "stage": "unknown",
                "facts": {"error": "boom"},
                "updated": "2026-01-01T00:00:00+00:00",
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    last = history.latest(runs)
    assert last is not None
    assert last["stage"] == "unknown"
    assert last["unfinished"] is True
    assert "boom" in last["error"]


class _MapServer:
    def __init__(self, output):
        self.output = output

    def submit(self, payload, timeout=60):
        return {"exit_code": 0, "output": self.output}


def test_runtime_mapping_address():
    maps = (
        "10000000-20000000 r-xp 00000000 08:01 123 /usr/lib/CautionConfig.so\n"
        "20000000-20100000 rw-p 10000000 08:01 123 /usr/lib/CautionConfig.so\n"
    )
    address = runtime._mapping_address(_MapServer(maps), 157, runtime.TARGET_OFFSET)
    assert address == 0x10000000 + runtime.TARGET_OFFSET
