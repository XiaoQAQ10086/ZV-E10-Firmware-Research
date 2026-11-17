# ZV-E10 Firmware Research and Gate-Enforced Installer Framework

**English** | [简体中文](README.zh-CN.md)

Research records and a controlled Windows installer framework for the Sony ZV-E10 (ILCE-ZV-E10), firmware 2.02/2.03. Current modules cover 5 GHz menu restoration and an evaluated shutter-sound replacement attempt. Every write step remains behind explicit gates, backups, and rollback checks.

## Scope and results

| Area | Result |
|---|---|
| 5 GHz menu | A single-byte patch to `CautionConfig.so`, three Backup properties, and WBI invalidation were completed on one ZV-E10 2.03. After a cold boot, `Page1=TypeNB/5` and the camera menu exposed the 5 GHz band option. RF link behavior was not tested. |
| Installer | Source, state machine, gates, double backup, preservation checks, runtime byte check, and a five-step GUI are implemented. Read-only `verify` passed on hardware; `install` has not been validated end-to-end on a factory-state camera. |
| Shutter sound | Writes to all nine `avsystemsound` slots, per-file readback, cold-boot persistence, and one-command restore passed on hardware. The camera did not play the custom audio; the shutter sound on this firmware does not come from these files. |
| Offline tests | 48 pytest cases pass, covering gates, state transitions, backup, stability, preservation, the sound codec, the sound service actions, restore preflight, and portable data paths. |

## Repository layout

```text
src/zve10_installer/       installer, CLI, GUI, state machine, gates, sound codec/server
tests/                     offline tests
packaging/                 PyInstaller specifications and frozen entry points
scripts/                   environment bootstrap and build scripts
compat/windows/            uid/chown/pwd and libusb compatibility shim
docs/INSTALLER.md          installer manual (Chinese)
docs/TESTER-GUIDE.md       tester procedure and log requirements (Chinese)
docs/RESEARCH.md           full research record (Chinese)
```

## Build

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\zve10-installer.exe doctor --upstream "D:\path\to\unlock"
.\.venv\Scripts\zve10-installer.exe check-package --upstream "D:\path\to\unlock"
```

`--upstream` must point to a local checkout at the pinned commits. The installer does not clone or modify upstream files. The build produces two executables and a portable zip:

```powershell
.\scripts\build_exe.ps1 -Upstream "D:\path\to\unlock"
```

Extract `dist\ZV-E10-Portable.zip` to a writable folder and run the executable there. Backups and run evidence are written to `backup\` next to the executable; no backup directory selection is required. Do not run the executable directly from inside the zip.

## Safety model

- WBI is never automatic. It writes the first 512 bytes of `/dev/nflasha5`; the operation recorded here was authorized by the device owner without a Pico/BootROM recovery path, which deviates from the upstream recovery-route requirement. Do not repeat it.
- A write requires a full backup, a second byte-compared backup, a read-only stability test, and preservation checks. Both backups are written automatically under `backup\`; they share one disk, so copy them elsewhere after a write.
- The GUI requires a checkbox confirming the camera battery is at least 75%. The CLI uses `--battery-ok`; no percentage is entered or stored. The software cannot verify the battery level.
- Timeouts, short reads, or hash mismatches mark the run `UNKNOWN`; no new session is opened to retry before a read-only review.
- Sony `ud_wbi_drop.elf`, firmware, BootROM dumps, device backups, and keys are not included.
- `backup/` and upstream session directories may contain device identifiers and full library snapshots. Keep them private.
- Firmware modification may affect warranty; 5 GHz operation is subject to local regulations.

## Extending the framework

The current tool is a guided, gate-enforced installer, not an unattended one-click writer. WBI and write confirmations remain manual. Additional same-model features should be integrated as independent modules:

- place each feature under `src/zve10_installer/steps/` with its own read-only preflight, write, final inspection, and readback;
- define per-module state stages, gates, backup scope, confirmation string, and failure handling;
- prove the factory state, target hashes, partition mount identity, and rollback material before any write;
- review the license, source, and hash of third-party code or binaries; do not merge unverified binaries;
- require offline tests and end-to-end validation on a factory-state camera before marking a module usable;
- keep WBI, BootROM, and DSP paths outside the automatic flow.

## Documentation and license

- [Research record](docs/RESEARCH.md) (Chinese): 5 GHz unlock, installer gates, shutter-sound experiment, failures and corrections.
- [Installer manual](docs/INSTALLER.md) (Chinese): GUI flow, CLI commands, driver, backup, acceptance.
- [Tester guide](docs/TESTER-GUIDE.md) (Chinese): read-only testing, diagnostic bundle, prohibited data.
- [Changelog](CHANGELOG.md): version history and the 2026-11-17 hardware result.

The code in this repository is MIT-licensed. Upstream projects, Sony-PMCA-RE, and Zadig notices and pinned revisions are in [NOTICE.md](NOTICE.md). `cokeenet/zve10-qemu` is PolyForm Noncommercial 1.0.0; only its published format facts are cited, and no code was copied.
