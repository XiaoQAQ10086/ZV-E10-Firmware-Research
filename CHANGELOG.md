# Changelog

## 0.12.2 — 2026-11-17

- **Fix `SoundSession.write` shadowed by a boolean attribute.** `__init__` used
  `self.write = write`, hiding the `write()` method and causing
  `TypeError: 'bool' object is not callable` at the first real write attempt.
  The flag is now `write_mode`; a test asserts the method stays callable.
- The exception fired before the `sound-write` request, so no camera write
  occurred. This was a latent bug in 0.11/0.12.
- 43 offline tests pass.
- **Real-machine result (2026-11-17)**: custom audio was written to all nine
  `avsystemsound` slots; per-file readback and cold-boot persistence passed,
  but the shutter sound did not change. All nine were then restored and
  verified against the official hashes. On this 2.03 camera the shutter sound
  is not played from these files; do not modify DSP/`av-cam.bin`.

## 0.12.1 — 2026-11-17

- **Fix temp-guard false positive on Jiritsu sessions.** The Jiritsu backend
  creates `/tmp/jiritsu/libJit.so`, `run.sh` and `out.txt` after the session
  starts and removes them on close. The guard previously treated them as
  leftovers and rejected every legitimate 2.03 write session. It now treats
  only uploaded `zve10-wifi-*` helpers as leftovers; the backend's own start
  check still refuses an existing loader workspace before overwriting.
- This unblocks `install` and `sound-write` on 2.03/Jiritsu.
- 42 offline tests pass.

## 0.12.0 — 2026-11-17

- **One-command factory restore**: `sound-restore-all --from <sound run or
  original/> --confirm "RESTORE ALL SHUTTER"`.
- Preflights all nine backup files before opening a camera write session; each
  file must exist and match the official 2.03 `avsystemsound` hash. A missing or
  non-factory file refuses the whole restore with no camera write.
- Files already at the factory hash are skipped; only modified files are
  written back. A failure stops the loop and reports partial progress.
- Offline tests cover the preflight (complete set, missing file, wrong hash,
  and no session construction before preflight). 42 tests pass.
- GUI still has no sound panel.

## 0.11.0 — 2026-11-17

- **Shutter-sound write path** (experimental): a sound-only service wrapper
  (`zve10_installer.sound_server`) adds `sound-read` / `sound-write` without
  modifying pinned upstream files.
- `sound-write` gates: write-authorized session, whitelist of shutter files,
  32-byte blocks and ≤24,832 bytes, fresh read must match `--expected` sha256,
  typed `WRITE <name>` confirmation.
- Write sequence: save `.before` backup, Jiritsu SET_FILE2 upload with full
  readback, `/usr` mount check, remount rw, stage the new file under a hidden
  temporary name, `chmod 644` + `sync` + readback, atomic `busybox mv` over the
  target, target readback, and a `finally` cleanup + remount ro with
  verification. A failed copy never truncates the original file.
- New CLI commands:
  - `sound-inspect` (read-only; saves originals under `runs/<...>/original/`)
  - `sound-write --name ... --file ... --expected ... --confirm "WRITE ..."`
  - `sound-write-all --file ... --confirm "WRITE ALL SHUTTER"` (all nine
    shutter/10fps variants, each gated by a fresh read of its current hash)
- First planned hardware control test: only `Dslr_Emnt_Shutter_Sha.bin`, using
  the original 1,216-byte file decoded/re-encoded; cold boot and listen.
- Hashing/remount/readback logic covered by offline fake-transport tests; no
  camera write has been performed yet. GUI has no sound panel yet.

## 0.10.0 — 2026-11-17

- Offline shutter-sound codec: PCM WAV ↔ ZV-E10 `/usr/share/avsystemsound`
  native 32-byte-block ADPCM (24 kHz, ≤1 s, ≤24,832 bytes).
- New CLI commands:
  - `sound-convert <wav> --out <bin> [--preview <wav>]`
  - `sound-decode <bin> --out <wav>`
- First control test uses the original 1,216-byte `Dslr_Emnt_Shutter_Sha.bin`
  decoded and re-encoded to exactly 1,216 bytes; no camera write yet.
- Format facts are taken from the public zve10-qemu research notes; the codec
  is an independent implementation (PolyForm-licensed code was not copied).

## 0.9.0 — 2026-11-17

P2 additions from the A7C2Tools review:

- **Runtime loaded-byte check**: `verify --runtime-check` (enabled in the GUI)
  locates the mapping containing file offset `0xD778E4` and reads the loaded
  byte from `/proc/<pid>/mem`; it must be `0x1B`. This uses a diagnostic
  write-flag session (no write commands are sent) because the read uses a shell
  pipe.
- **Per-body ID hash**: reads Backup serial property `0x00e70003` and stores a
  truncated SHA-256 in inspect/install/verify summaries; the GUI warns if the
  verification body differs from the installation body. The raw serial is not
  stored.
- **Sony USB identity scan**: `doctor` lists all `054c` product IDs; the driver
  guidance tells the user to install WinUSB for a second service identity if it
  appears.
- Runtime/body-ID hardware validation is still pending a factory-state camera.

## 0.8.0 — 2026-11-17

P1 additions from the A7C2Tools review:

- **Non-target Backup preservation check**: parse the full Backup database
  before/after and require all non-target properties to be unchanged; keys that
  already moved during the read-only preparation window are allowed to move
  again.
- **Battery percentage**: GUI entry and CLI `--battery-percent`; 50–100 is
  required before preparation.
- **Last-run view**: the prepare page warns about `unknown`/`interrupted` runs;
  “技术详情” shows the latest stage, error and directory.
- **Offline self-check**: `check-package` verifies upstream pins, helper hashes,
  `tools/wifi.py`/`wbi.py`, the Windows shim and the bundled Zadig hash.
- Validation status table in the README.

## 0.7.0 — 2026-11-17

P0 safety additions from the A7C2Tools review:

- **USB stability test**: at least 2 minutes of repeated read-only inspections;
  identical library hash and properties required before backup/write.
- **Double backup**: a second, empty directory is required; every backup file is
  copied and byte-compared (`filecmp`).
- **Temporary-file guard**: `/tmp/jiritsu` leftovers (`zve10-wifi-*`, `libJit.so`,
  `run.sh`, `out.txt`) and a non-empty `/etc/ld.so.preload` stop the session.
- **Driver recovery**: GUI button opens Device Manager with exact uninstall
  steps; the bundled Zadig path remains for install.
- **Diagnostic bundle**: exports env/doctor/latest run logs to a zip, excluding
  backups, firmware, helper binaries and Sony tools.
- `install` CLI now requires `--backup-copy`; GUI requires the second directory
  before “开始检查”.

## 0.6.0 — 2026-11-17

- Five-step GUI wizard: prepare → check → flash → cold boot → acceptance.
- Precondition card: camera, firmware, Mass Storage, WinUSB driver, region,
  battery. The check button stays disabled until the conditions pass.
- Bundled offline **Zadig 2.9** driver helper (GPLv3, separate program) launched
  from the precondition card when the driver is missing.
- Automatic WBI branch: if acceptance reports `TypeRK/4`, the same page continues
  into the WBI step (still gated by ELF hash, recovery confirmation, double
  backup and exact confirmation string).
- Doctor / Inspect / Verify and logs moved behind “技术详情 / 高级”.
- `install` and WBI write paths remain code-complete but not yet validated
  end-to-end on a factory-state camera.

## 0.5.0 — 2026-11-16

- Light-theme GUI.
- Gated install card: precondition check, full backup, typed region and write
  confirmations; `install` is enabled in full builds and disabled in read-only
  builds.
- `InstallSession` keeps one write-authorized session open between the
  precondition checklist and the write, so no extra cold boot is needed.
- Preconditions: camera/authentication, supported firmware, known library hash,
  untouched `00/09/09` properties, `/usr` read-only, verified backup, region.
- Advanced WBI tab: user-supplied official `ud_wbi_drop.elf` (size/hash checked),
  `already-invalid` refusal, double 60 MiB backup, `RECOVERY-READY`
  confirmation, exact confirmation string, drop and full readback.
- The write path is implemented but has not been exercised end-to-end on a
  factory-state camera.

## 0.4.0 — 2026-11-16

- CustomTkinter GUI (read-only): status card, Doctor / Inspect / Verify
  actions, output panel and evidence-folder button.
- New windowed single-file exe `ZV-E10-Installer.exe`; the console CLI
  `zve10-installer.exe` remains available.
- GUI entry handles the frozen `__serve` mode used to start the upstream
  session in a subprocess.
- `install` remains hidden in read-only builds.

## 0.3.0 — 2026-11-16

- Single-file Windows exe built with PyInstaller (read-only commands:
  `doctor`, `inspect`, `verify`).
- Bundled pinned upstream checkout and Windows compatibility shim; pins are
  verified from `PIN.json` inside the bundle.
- Frozen `__serve` mode lets the exe launch the upstream service session.
- `install` is hidden in read-only builds via the bundled `READ_ONLY` marker.
- No Sony binaries, firmware, BootROM dumps or device backups are bundled.

## 0.2.0 — 2026-11-16

- `install`: guided inspect → region → backup → recheck → patch → properties →
  final inspect → close.
- `verify`: read-only post-cold-boot check of patched hash, `01/02/16`,
  `/usr` read-only and `Page1`.
- New gates: baseline properties `00/09/09`, installed state, raw-backup result.
- Backup step runs the upstream `zve10_verify.py manifest/sums` checks.
- State machine records `UNKNOWN` if a write step fails or times out.
- No WBI, restore or unattended mode.

## 0.1.0 — 2026-11-16

- Initial skeleton.
- `doctor`: platform, Python, dependencies, upstream pins, USB enumeration,
  WinUSB configuration read.
- `inspect`: read-only Jiritsu session, inspect action, prewrite gate, local
  evidence.
- State machine, pure gate functions, typed confirmations, error categories.
- Windows compatibility shim under `compat/windows`.
- Offline tests for gates, state and fake upstream discovery.
