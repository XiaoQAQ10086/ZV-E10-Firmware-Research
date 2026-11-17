"""Check the byte actually loaded in the running firmware process.

After a cold boot, locate the mapping that contains file offset 0xD778E4 in
/proc/<pid>/maps, read one byte from /proc/<pid>/mem and require 0x1B. This
distinguishes "the file on flash is patched" from "the running firmware loaded
the patch".
"""

from __future__ import annotations

from ..errors import GateError

TARGET_OFFSET = 0xD778E4
TARGET_PATH = "/usr/lib/CautionConfig.so"
EXPECTED_BYTE = "1b"


def _mapping_address(server, pid: int, offset: int) -> int:
    result = server.submit(
        {
            "action": "shell",
            "command": f"busybox grep CautionConfig.so /proc/{pid}/maps",
        },
        timeout=60,
    )
    if result.get("exit_code") != 0:
        raise GateError("runtime", f"cannot read maps: {result!r}")
    for line in str(result.get("output", "")).splitlines():
        parts = line.split()
        if len(parts) < 6 or TARGET_PATH not in line:
            continue
        try:
            start_text, end_text = parts[0].split("-")
            start = int(start_text, 16)
            end = int(end_text, 16)
            file_offset = int(parts[2], 16)
        except ValueError:
            continue
        if "r" not in parts[1]:
            continue
        if file_offset <= offset < file_offset + (end - start):
            return start + (offset - file_offset)
    raise GateError("runtime", "target file offset is not in a readable CautionConfig.so mapping")


def check(server, boot: dict) -> dict:
    pid = boot.get("pid")
    if not isinstance(pid, int):
        raise GateError("runtime", "boot-check did not return a usable pid")
    address = _mapping_address(server, pid, TARGET_OFFSET)
    command = (
        f"busybox dd if=/proc/{pid}/mem bs=1 skip={address} count=1 "
        "2>/dev/null | busybox xxd -p"
    )
    result = server.submit({"action": "shell", "command": command}, timeout=60)
    if result.get("exit_code") != 0:
        raise GateError("runtime", f"memory read failed: {result!r}")
    value = str(result.get("output", "")).strip().lower()
    if value != EXPECTED_BYTE:
        raise GateError(
            "runtime",
            f"loaded byte at 0x{address:x} is {value!r}, expected {EXPECTED_BYTE!r}; "
            "the running firmware may still use old code",
        )
    return {"pid": pid, "address": hex(address), "byte": value}
