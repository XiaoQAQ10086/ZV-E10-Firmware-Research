"""Sound-specific service server wrapper.

Launches the pinned upstream terminal server with two extra structured actions:

    sound-read   read a file under /usr/share/avsystemsound and return its hex
    sound-write  back up the current file, upload a replacement via the
                 Jiritsu SET_FILE2 path, remount /usr rw, copy, read back,
                 remount ro, and remove the temporary file

No upstream file is modified. The wrapper only replaces REQUEST_HANDLER in the
server process; all transport, authentication, queueing and teardown remain in
the pinned toolkit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import uuid
from pathlib import Path

SOUND_DIR = "/usr/share/avsystemsound/"
NAME_RE = re.compile(r"^Dslr_Emnt_(?:Shutter|10FPS_Kasha)[A-Za-z0-9_]*\.bin$")
MAX_SOUND_BYTES = 24832
MAX_READ_BYTES = 262144


def _add_paths(root: Path, pmca: Path | None) -> None:
    from . import platform_compat

    paths = [
        root / "tools",
        root / "vendor" / "zv-e10-toolkit" / "linux" / "host",
        pmca or (root / "vendor" / "zv-e10-toolkit" / "linux" / "vendor" / "Sony-PMCA-RE"),
        platform_compat.compat_dir(),
    ]
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if entry:
            paths.append(Path(entry))
    for path in reversed(paths):
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    platform_compat.activate()


def _sound_path(request: dict) -> tuple[str, str]:
    name = request.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValueError("invalid sound file name")
    return name, SOUND_DIR + name


def _usr_mount(camera, ops, state: str = "ro") -> list[str]:
    mounts = ops.run(camera, "busybox cat /proc/mounts")
    rows = [
        line.split()
        for line in mounts.splitlines()
        if len(line.split()) >= 4 and line.split()[1] == "/usr"
    ]
    if (
        len(rows) != 1
        or rows[0][0] != "/dev/nflasha15"
        or rows[0][2] != "ext2"
        or state not in rows[0][3].split(",")
    ):
        raise ValueError(f"/usr is not mounted {state}; no sound write")
    return rows[0]


def _sound_action(camera, request, folder: Path, allow_write, ops) -> dict:
    action = request.get("action")
    name, path = _sound_path(request)
    ops.check_firmware(camera)

    if action == "sound-read":
        try:
            data = ops.read_file(camera, path)
        except RuntimeError as exc:
            # ``read_file`` uses RuntimeError for a failed FileControl read
            # (including a missing path). Do not swallow USB/backend errors.
            if request.get("optional"):
                return {"name": name, "path": path, "missing": True, "error": str(exc)[:300]}
            raise
        if len(data) > MAX_READ_BYTES:
            raise ValueError("sound file is unexpectedly large")
        snapshot = f"{uuid.uuid4().hex[:8]}-{name}.orig"
        ops.save_private(folder, snapshot, data)
        return {
            "name": name,
            "path": path,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "data_hex": data.hex(),
            "snapshot": snapshot,
        }

    if action == "sound-write":
        if not allow_write:
            raise ValueError("sound write requires --owner-authorized-write")
        if "data_file" in request:
            rel = request.get("data_file")
            if not isinstance(rel, str) or not re.fullmatch(r"sound-[0-9a-f]{16}\.bin", rel):
                raise ValueError("invalid sound data file")
            candidate = folder / rel
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("sound data file is missing")
            data = candidate.read_bytes()
        else:
            # Small offline tests only; the real client uses data_file because
            # the upstream request queue rejects requests of 4096 bytes or more.
            data = bytes.fromhex(str(request.get("data_hex", "")))
        if not data or len(data) > MAX_SOUND_BYTES:
            raise ValueError("replacement sound is empty or too large")
        if len(data) % 32:
            raise ValueError("replacement sound must be 32-byte blocks")
        expected = str(request.get("expected_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("expected_sha256 is required")

        before = ops.read_file(camera, path)
        before_hash = hashlib.sha256(before).hexdigest()
        if before_hash != expected:
            raise ValueError("current sound hash does not match expected_sha256")
        ops.save_private(folder, f"{uuid.uuid4().hex[:8]}-{name}.before", before)
        _usr_mount(camera, ops, "ro")

        token = hashlib.sha256(data).hexdigest()[:16]
        remote = "/tmp/jiritsu/zve10-wifi-sound-" + token
        staged_path = SOUND_DIR + "." + name + ".new"
        ops.run(camera, "busybox mkdir -p /tmp/jiritsu")
        read_only = False
        ro_error = None
        try:
            ops.upload_verified(camera, remote, data)
            ops.run(camera, "busybox chmod 600 " + remote)
            try:
                ops.run(camera, "mount -o remount,rw /usr")
                _usr_mount(camera, ops, "rw")
                # Stage the whole file first; only rename it over the original
                # after a full readback, so a failed copy never truncates it.
                ops.run(camera, "busybox rm -f " + staged_path)
                ops.run(camera, "busybox cp " + remote + " " + staged_path)
                ops.run(camera, "busybox chmod 644 " + staged_path)
                try:
                    ops.run(camera, "busybox sync")
                except Exception:
                    pass
                staged = ops.read_file(camera, staged_path)
                if staged != data:
                    raise RuntimeError("staged sound readback mismatch; STOP")
                ops.run(camera, "busybox mv " + staged_path + " " + path)
                try:
                    ops.run(camera, "busybox sync")
                except Exception:
                    pass
                after = ops.read_file(camera, path)
                after_hash = hashlib.sha256(after).hexdigest()
                if after != data:
                    raise RuntimeError("sound readback mismatch; STOP")
            finally:
                try:
                    ops.run(camera, "busybox rm -f " + staged_path)
                except Exception:
                    pass
                try:
                    ops.run(camera, "mount -o remount,ro /usr")
                    _usr_mount(camera, ops, "ro")
                    read_only = True
                except Exception as exc:  # noqa: BLE001 - reported to the client
                    ro_error = repr(exc)
            if not read_only:
                raise RuntimeError("failed to restore /usr read-only: " + str(ro_error))
            return {
                "name": name,
                "path": path,
                "before_sha256": before_hash,
                "after_sha256": after_hash,
                "size": len(after),
                "readonly": True,
            }
        finally:
            try:
                ops.run(camera, "busybox rm -f " + remote)
            except Exception:
                pass

    raise ValueError("unknown sound action")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--upstream-root", required=True)
    parser.add_argument("--pmca-root")
    known, rest = parser.parse_known_args(argv)

    root = Path(known.upstream_root).resolve()
    pmca = Path(known.pmca_root).resolve() if known.pmca_root else None
    _add_paths(root, pmca)

    import wifi  # type: ignore
    import zve10_terminal_server as server  # type: ignore

    def dispatch(camera, request, folder: Path, allow_write: bool):
        action = request.get("action")
        if action in {"sound-read", "sound-write"}:
            return _sound_action(camera, request, Path(folder), allow_write, wifi)
        # A sound session must not become a general 5GHz write session.
        raise ValueError("sound session only accepts sound-read/sound-write")

    server.REQUEST_HANDLER = dispatch
    forwarded = rest if rest and rest[0] == "serve" else ["serve", *rest]
    sys.argv = ["zve10-sound-server", *forwarded]
    server.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
