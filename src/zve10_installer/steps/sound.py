"""Shutter-sound inspection and write path (experimental).

The sound files are ordinary files on the read-only ``/usr`` ext2 partition.
The service side (``zve10_installer.sound_server``) adds two structured actions:
``sound-read`` and ``sound-write``. Writes back up the current file, upload it
through the upstream Jiritsu SET_FILE2 path with readback, remount ``/usr`` rw,
copy, read back the target, and remount ro in a ``finally`` block.

No WBI is involved: a cold boot reloads the sound files.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..errors import InstallerError
from ..evidence import RunDir
from ..server import SessionServer
from ..upstream import Upstream
from . import guards

# Mechanical/electronic shutter sounds plus the 10 fps burst variants. The
# front-panel "Shutter_Ka/Sha" files do not exist in the 2.03 nflasha15 image;
# they are listed only if a future camera image contains them.
SHUTTER_FILES = (
    "Dslr_Emnt_Shutter_Ka.bin",
    "Dslr_Emnt_Shutter_Sha.bin",
    "Dslr_Emnt_Shutter_Sha2.bin",
    "Dslr_Emnt_Shutter_Sha3.bin",
    "Dslr_Emnt_Shutter_Sha4.bin",
    "Dslr_Emnt_10FPS_Kasha.bin",
    "Dslr_Emnt_10FPS_Kasha2.bin",
    "Dslr_Emnt_10FPS_Kasha3.bin",
    "Dslr_Emnt_10FPS_Kasha4.bin",
)

# Hashes of the same files in the official 2.03 nflasha15 image. They are used
# only as a sanity display; the write gate compares against a fresh read.
ORIGINAL_SHA = {
    "Dslr_Emnt_Shutter_Ka.bin": "3cff4023af0b3d9d4481124d605c651a661697a87ebb0640148946b84a5e44df",
    "Dslr_Emnt_Shutter_Sha.bin": "957ae8939f66bff6fdc1810cf854dbed51306d34cf6c8838e944bb5ed78be3fd",
    "Dslr_Emnt_Shutter_Sha2.bin": "957ae8939f66bff6fdc1810cf854dbed51306d34cf6c8838e944bb5ed78be3fd",
    "Dslr_Emnt_Shutter_Sha3.bin": "e932f7080872ca3c425c939235a24715099d106c8284442ee11e44b1b8f80c02",
    "Dslr_Emnt_Shutter_Sha4.bin": "0ef386730a84e782232e50aa8f55059555367f439697d005597982bb7049a170",
    "Dslr_Emnt_10FPS_Kasha.bin": "957ae8939f66bff6fdc1810cf854dbed51306d34cf6c8838e944bb5ed78be3fd",
    "Dslr_Emnt_10FPS_Kasha2.bin": "957ae8939f66bff6fdc1810cf854dbed51306d34cf6c8838e944bb5ed78be3fd",
    "Dslr_Emnt_10FPS_Kasha3.bin": "e932f7080872ca3c425c939235a24715099d106c8284442ee11e44b1b8f80c02",
    "Dslr_Emnt_10FPS_Kasha4.bin": "0ef386730a84e782232e50aa8f55059555367f439697d005597982bb7049a170",
}

MAX_SOUND_BYTES = 24832
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_replacement(name: str, data: bytes) -> None:
    if name not in SHUTTER_FILES:
        raise InstallerError(f"unsupported sound file: {name}")
    if not data or len(data) > MAX_SOUND_BYTES:
        raise InstallerError(
            f"replacement is {len(data)} bytes; expected 1..{MAX_SOUND_BYTES}"
        )
    if len(data) % 32:
        raise InstallerError("replacement must be a whole number of 32-byte blocks")


class SoundSession:
    def __init__(self, upstream: Upstream, runs_dir: Path, *, write: bool) -> None:
        self.run_dir = RunDir.create(Path(runs_dir), "sound")
        self.write_mode = write
        self.server = SessionServer(
            upstream,
            self.run_dir.session_dir,
            write=write,
            server_mode="sound",
            log_dir=self.run_dir.path,
        )
        self.opened = False

    def open(self) -> None:
        self.server.start()
        self.opened = True
        try:
            if self.write_mode:
                guards.check(self.server)
        except Exception:
            try:
                self.close()
            except Exception:
                pass
            raise
        self.run_dir.append_event("sound_session_open", {"write": self.write_mode})

    def read(self, name: str) -> dict:
        answer = self.server.submit(
            {"action": "sound-read", "name": name, "optional": True},
            timeout=120,
        )
        if answer.get("missing"):
            return {"name": name, "missing": True, "error": answer.get("error", "")}
        data = bytes.fromhex(str(answer.get("data_hex", "")))
        digest = _sha(data)
        if digest != answer.get("sha256") or len(data) != answer.get("size"):
            raise InstallerError(f"sound readback mismatch for {name}")
        folder = self.run_dir.path / "original"
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(data)
        return {
            "name": name,
            "size": len(data),
            "sha256": digest,
            "original_in_image": ORIGINAL_SHA.get(name),
            "matches_image": digest == ORIGINAL_SHA.get(name),
            "path": answer.get("path"),
        }

    def write(self, name: str, data: bytes, expected_sha256: str) -> dict:
        if not self.write_mode:
            raise InstallerError("sound write requires a write session")
        validate_replacement(name, data)
        if not SHA_RE.match(expected_sha256):
            raise InstallerError("expected_sha256 must be 64 lowercase hex characters")
        current = self.read(name)
        if current.get("missing"):
            raise InstallerError(f"target sound file is missing: {name}")
        if current["sha256"] != expected_sha256:
            raise InstallerError(
                "current sound hash changed: "
                f"{current['sha256']} != {expected_sha256}; re-inspect first"
            )
        folder = self.run_dir.path / "replacement"
        folder.mkdir(exist_ok=True)
        (folder / name).write_bytes(data)
        upload_name = f"sound-{_sha(data)[:16]}.bin"
        (self.server.session_dir / upload_name).write_bytes(data)

        answer = self.server.submit(
            {
                "action": "sound-write",
                "name": name,
                "data_file": upload_name,
                "expected_sha256": expected_sha256,
            },
            timeout=300,
        )
        after = str(answer.get("after_sha256", ""))
        if after != _sha(data) or not answer.get("readonly"):
            raise InstallerError("sound write did not verify; STOP and inspect")
        self.run_dir.append_event(
            "sound_written",
            {"name": name, "before": answer.get("before_sha256"), "after": after},
        )
        return {
            "name": name,
            "before_sha256": answer.get("before_sha256"),
            "after_sha256": after,
            "size": answer.get("size"),
            "readonly": True,
            "run": str(self.run_dir.path),
        }

    def close(self) -> None:
        if self.opened:
            self.server.close()
            self.opened = False

    def __enter__(self) -> "SoundSession":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise


def inspect(upstream: Upstream, runs_dir: Path) -> dict:
    with SoundSession(upstream, runs_dir, write=False) as session:
        files = [session.read(name) for name in SHUTTER_FILES]
    summary = {
        "run": str(session.run_dir.path),
        "camera_files": files,
        "note": "no camera writes; originals saved under original/",
    }
    session.run_dir.write_json("sound-inspect.json", summary)
    return summary


def write_file(
    upstream: Upstream,
    runs_dir: Path,
    *,
    name: str,
    data: bytes,
    expected_sha256: str,
) -> dict:
    validate_replacement(name, data)
    with SoundSession(upstream, runs_dir, write=True) as session:
        result = session.write(name, data, expected_sha256)
    result["note"] = "cold boot the camera, then listen; nothing else was changed"
    session.run_dir.write_json("sound-write.json", result)
    return result


def write_all(
    upstream: Upstream,
    runs_dir: Path,
    *,
    data: bytes,
) -> dict:
    """Route 2: replace every shutter/10fps variant with the same sound.

    Each current file is read and backed up first; the fresh hash becomes the
    expected hash for that file. A failure stops the loop and reports exactly
    which files were already replaced; nothing is retried.
    """
    validate_replacement(SHUTTER_FILES[0], data)
    session = SoundSession(upstream, runs_dir, write=True)
    results: list[dict] = []
    error: str | None = None
    try:
        session.open()
    except Exception:
        try:
            session.close()
        except Exception:
            pass
        raise
    try:
        for name in SHUTTER_FILES:
            try:
                current = session.read(name)
                if current.get("missing"):
                    results.append({"name": name, "skipped": "missing"})
                    continue
                results.append(session.write(name, data, current["sha256"]))
            except Exception as exc:  # noqa: BLE001 - report partial progress
                error = f"{name}: {exc}"
                results.append({"name": name, "error": str(exc)})
                break
    finally:
        try:
            session.close()
        except Exception:
            pass

    summary = {
        "run": str(session.run_dir.path),
        "replacement_sha256": _sha(data),
        "replacement_size": len(data),
        "files": results,
        "error": error,
        "note": "cold boot the camera, then listen; restore from original/ if needed",
    }
    session.run_dir.write_json("sound-write-all.json", summary)
    if error:
        raise InstallerError(
            "sound write stopped after a failure: "
            + error
            + "; inspect "
            + str(session.run_dir.path)
            + " before retrying"
        )
    return summary


def resolve_original_dir(path: Path) -> Path:
    """Accept either a sound run directory or its ``original`` directory."""
    path = Path(path).expanduser()
    candidate = path / "original"
    return candidate if candidate.is_dir() else path


def original_plan(original_dir: Path) -> list[dict]:
    """Preflight a factory backup before any camera write is opened."""
    folder = Path(original_dir)
    if not folder.is_dir():
        raise InstallerError(f"backup directory does not exist: {folder}")
    plan: list[dict] = []
    missing: list[str] = []
    mismatched: list[str] = []
    for name in SHUTTER_FILES:
        source = folder / name
        if source.is_symlink() or not source.is_file():
            missing.append(name)
            continue
        data = source.read_bytes()
        digest = _sha(data)
        if digest != ORIGINAL_SHA.get(name):
            mismatched.append(f"{name} ({digest[:12]}...)")
        plan.append({"name": name, "data": data, "sha256": digest})
    if missing or mismatched:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if mismatched:
            details.append("not factory original: " + ", ".join(mismatched))
        raise InstallerError("backup directory is not a complete factory set: " + "; ".join(details))
    return plan


def restore_all(
    upstream: Upstream,
    runs_dir: Path,
    *,
    original_dir: Path,
) -> dict:
    """Write every factory original back with one command.

    The whole backup is preflighted (all nine files, hashes must match the
    official 2.03 image) before the camera write session is opened. Files that
    are already original are left untouched.
    """
    folder = resolve_original_dir(Path(original_dir))
    plan = original_plan(folder)

    session = SoundSession(upstream, runs_dir, write=True)
    results: list[dict] = []
    error: str | None = None
    try:
        session.open()
    except Exception:
        try:
            session.close()
        except Exception:
            pass
        raise
    try:
        for item in plan:
            name = item["name"]
            try:
                current = session.read(name)
                if current.get("missing"):
                    raise InstallerError(f"target sound file is missing: {name}")
                if current["sha256"] == item["sha256"]:
                    results.append({"name": name, "status": "already-original"})
                    continue
                written = session.write(name, item["data"], current["sha256"])
                results.append({**written, "status": "restored"})
            except Exception as exc:  # noqa: BLE001 - report partial progress
                error = f"{name}: {exc}"
                results.append({"name": name, "error": str(exc)})
                break
    finally:
        try:
            session.close()
        except Exception:
            pass

    summary = {
        "run": str(session.run_dir.path),
        "source": str(folder),
        "files": results,
        "error": error,
        "note": "cold boot the camera, then confirm sound-inspect matches the official hashes",
    }
    session.run_dir.write_json("sound-restore-all.json", summary)
    if error:
        raise InstallerError(
            "sound restore stopped after a failure: "
            + error
            + "; inspect "
            + str(session.run_dir.path)
            + " before retrying"
        )
    return summary
