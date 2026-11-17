"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, doctor, paths, platform_compat, selfcheck
from . import upstream as upstream_mod
from .errors import InstallerError
from .steps import diagnostics
from .steps import inspect as inspect_step
from .steps import install as install_step
from .steps import sound as sound_step
from .steps import verify as verify_step
from .steps import wbi as wbi_step


def build_parser() -> argparse.ArgumentParser:
    # Common options are accepted both before and after the subcommand. Using
    # SUPPRESS in the subparser keeps the top-level value when the option is not
    # repeated after the command.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--upstream", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--runs-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        prog="zve10-installer",
        description="Guided, gate-enforced installer for the ZV-E10 5GHz Wi-Fi menu.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--upstream", help="path to the pinned ZV-E10-5GHz-WiFi-Unlock checkout")
    parser.add_argument("--runs-dir", default=None, help="directory for local evidence (default: <app>/backup/runs)")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_cmd = sub.add_parser(
        "doctor",
        parents=[common],
        help="check environment, pins and USB device (read-only)",
    )
    doctor_cmd.add_argument("--json", action="store_true", help="print machine-readable results")

    inspect_cmd = sub.add_parser(
        "inspect",
        parents=[common],
        help="read-only inspection (no camera writes)",
    )
    inspect_cmd.add_argument("--firmware", default="2.03", choices=["2.02", "2.03"])

    if not platform_compat.is_read_only_build():
        install_cmd = sub.add_parser(
            "install",
            parents=[common],
            help="guided write: backup, patch and three Backup properties",
        )
        install_cmd.add_argument("--firmware", default="2.03", choices=["2.02", "2.03"])
        install_cmd.add_argument(
            "--backup-passes",
            type=int,
            default=1,
            choices=[1, 2],
            help="raw-backup passes (default 1; 2 is recommended if a recovery route is planned)",
        )
        install_cmd.add_argument(
            "--backup-copy",
            default=None,
            help="optional override for the second backup directory (default: <app>/backup/second/<run>)",
        )
        install_cmd.add_argument(
            "--stability-seconds",
            type=int,
            default=120,
            help="read-only USB stability test duration (default 120)",
        )
        install_cmd.add_argument(
            "--battery-ok",
            action="store_true",
            help="confirm the camera battery is at least 75%% before preparation",
        )

        wbi_cmd = sub.add_parser(
            "wbi",
            parents=[common],
            help="advanced WBI invalidation (eMMC write; explicit confirmation required)",
        )
        wbi_cmd.add_argument(
            "--sony-tool",
            required=True,
            help="path to your own official ud_wbi_drop.elf (6200 bytes)",
        )
        wbi_cmd.add_argument("--firmware", default="2.03", choices=["2.02", "2.03"])
    verify_cmd = sub.add_parser(
        "verify",
        parents=[common],
        help="read-only post-install verification after a cold boot",
    )
    verify_cmd.add_argument("--firmware", default="2.03", choices=["2.02", "2.03"])
    verify_cmd.add_argument(
        "--runtime-check",
        action="store_true",
        help="also read the loaded CautionConfig.so byte from the running firmware (uses a diagnostic write-flag session, no writes)",
    )

    sub.add_parser(
        "check-package",
        parents=[common],
        help="offline self-check of upstream pins, helpers and bundled Zadig",
    )
    sub.add_parser(
        "diagnose",
        parents=[common],
        help="export a privacy-aware diagnostic bundle from runs/ (no camera)",
    )

    sound_convert = sub.add_parser(
        "sound-convert",
        parents=[common],
        help="offline WAV -> ZV-E10 avsystemsound BIN (no camera)",
    )
    sound_convert.add_argument("input", help="PCM WAV file")
    sound_convert.add_argument("--out", required=True, help="output BIN path")
    sound_convert.add_argument("--preview", help="optional decoded preview WAV path")

    sound_decode = sub.add_parser(
        "sound-decode",
        parents=[common],
        help="offline ZV-E10 avsystemsound BIN -> preview WAV (no camera)",
    )
    sound_decode.add_argument("input", help="native 32-byte-block BIN file")
    sound_decode.add_argument("--out", required=True, help="output preview WAV path")

    sub.add_parser(
        "sound-inspect",
        parents=[common],
        help="read the camera's shutter sound files (read-only; no writes)",
    )
    sound_write = sub.add_parser(
        "sound-write",
        parents=[common],
        help="replace one shutter sound file (experimental; explicit confirmation)",
    )
    sound_write.add_argument("--name", required=True, help="target file name, e.g. Dslr_Emnt_Shutter_Sha.bin")
    sound_write.add_argument("--file", required=True, help="replacement 32-byte-block BIN")
    sound_write.add_argument("--expected", required=True, help="sha256 of the current camera file")
    sound_write.add_argument(
        "--confirm",
        required=True,
        help="type exactly: WRITE <name>",
    )
    sound_write_all = sub.add_parser(
        "sound-write-all",
        parents=[common],
        help="replace all nine shutter/10fps sound files (experimental)",
    )
    sound_write_all.add_argument("--file", required=True, help="replacement 32-byte-block BIN")
    sound_write_all.add_argument(
        "--confirm",
        required=True,
        help="type exactly: WRITE ALL SHUTTER",
    )
    sound_restore_all = sub.add_parser(
        "sound-restore-all",
        parents=[common],
        help="write all nine factory shutter sounds back from a verified backup",
    )
    sound_restore_all.add_argument(
        "--from",
        dest="from_dir",
        required=True,
        help="sound run directory or its original/ directory",
    )
    sound_restore_all.add_argument(
        "--confirm",
        required=True,
        help="type exactly: RESTORE ALL SHUTTER",
    )
    return parser


def _menu(upstream: upstream_mod.Upstream, runs_dir: Path) -> int:
    print(f"\nZV-E10 5GHz Installer {__version__} — read-only")
    print("  1) Doctor  — check environment, pins and camera")
    print("  2) Inspect — read library hash, properties and mounts")
    print("  3) Verify  — check the installed state after a cold boot")
    print("  0) Exit")
    while True:
        try:
            choice = input("\nSelect: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in {"0", "q", "quit", "exit"}:
            return 0
        try:
            if choice == "1":
                checks = doctor.run(upstream)
                print(doctor.format_checks(checks))
            elif choice == "2":
                summary = inspect_step.run(upstream, runs_dir)
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            elif choice == "3":
                summary = verify_step.run(upstream, runs_dir)
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            else:
                print("Unknown choice; enter 0, 1, 2 or 3.")
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
        try:
            input("\nPress Enter to return to the menu...")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0


def _sound_command(args) -> int:
    from . import sound_codec

    try:
        if args.command == "sound-convert":
            result = sound_codec.prepare_wav(args.input)
            output = Path(args.out)
            output.write_bytes(result.data)
            if args.preview:
                Path(args.preview).write_bytes(result.preview_wav)
            print(json.dumps({"output": str(output), **result.summary()}, indent=2))
        else:
            result = sound_codec.decode_bin(args.input)
            output = Path(args.out)
            output.write_bytes(result.preview_wav)
            print(json.dumps({"output": str(output), **result.summary()}, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    platform_compat.activate()
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] in {"__serve", "__sound-serve"}:
        if argv[0] == "__sound-serve":
            from .frozen import serve_sound_upstream

            return serve_sound_upstream(argv[1:])
        from .frozen import serve_upstream

        return serve_upstream(argv[1:])

    if not argv:
        if sys.stdin.isatty():
            try:
                upstream = upstream_mod.locate(None)
            except InstallerError as exc:
                print(f"error: {exc}", file=sys.stderr)
                try:
                    input("\nPress Enter to close...")
                except (EOFError, KeyboardInterrupt):
                    pass
                return 2
            return _menu(upstream, paths.default_runs_dir())
        build_parser().print_help()
        return 2

    args = build_parser().parse_args(argv)
    args.runs_dir = Path(args.runs_dir) if args.runs_dir else paths.default_runs_dir()

    if args.command in {"sound-convert", "sound-decode"}:
        return _sound_command(args)

    try:
        upstream = upstream_mod.locate(args.upstream)
    except InstallerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "doctor":
        checks = doctor.run(upstream)
        if args.json:
            print(json.dumps(doctor.checks_as_dict(checks), indent=2, ensure_ascii=False))
        else:
            print(doctor.format_checks(checks))
        return 1 if doctor.has_failures(checks) else 0

    if args.command == "inspect":
        try:
            summary = inspect_step.run(upstream, Path(args.runs_dir), firmware=args.firmware)
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "install":
        try:
            summary = install_step.run(
                upstream,
                Path(args.runs_dir),
                firmware=args.firmware,
                backup_passes=args.backup_passes,
                backup_copy=Path(args.backup_copy) if args.backup_copy else None,
                stability_seconds=args.stability_seconds,
                battery_confirmed=args.battery_ok,
            )
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify":
        try:
            summary = verify_step.run(
                upstream,
                Path(args.runs_dir),
                firmware=args.firmware,
                runtime_check=args.runtime_check,
            )
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        if summary.get("status") == "ok":
            return 0
        if summary.get("status") == "wbi_required":
            return 4
        return 3

    if args.command == "wbi":
        try:
            summary = wbi_step.run(
                upstream,
                Path(args.runs_dir),
                sony_tool=args.sony_tool,
                firmware=args.firmware,
            )
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "sound-inspect":
        try:
            summary = sound_step.inspect(upstream, Path(args.runs_dir))
        except InstallerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "sound-write":
        if args.confirm != f"WRITE {args.name}":
            print(f"error: --confirm must be exactly: WRITE {args.name}", file=sys.stderr)
            return 2
        try:
            data = Path(args.file).read_bytes()
            summary = sound_step.write_file(
                upstream,
                Path(args.runs_dir),
                name=args.name,
                data=data,
                expected_sha256=args.expected,
            )
        except (InstallerError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "sound-write-all":
        if args.confirm != "WRITE ALL SHUTTER":
            print("error: --confirm must be exactly: WRITE ALL SHUTTER", file=sys.stderr)
            return 2
        try:
            data = Path(args.file).read_bytes()
            summary = sound_step.write_all(upstream, Path(args.runs_dir), data=data)
        except (InstallerError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "sound-restore-all":
        if args.confirm != "RESTORE ALL SHUTTER":
            print("error: --confirm must be exactly: RESTORE ALL SHUTTER", file=sys.stderr)
            return 2
        try:
            summary = sound_step.restore_all(
                upstream,
                Path(args.runs_dir),
                original_dir=Path(args.from_dir),
            )
        except (InstallerError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "check-package":
        checks = selfcheck.run(upstream)
        print(selfcheck.format_checks(checks))
        return 1 if selfcheck.has_failures(checks) else 0

    if args.command == "diagnose":
        path = diagnostics.create_bundle(Path(args.runs_dir), upstream)
        print(path)
        print("包含本机路径与日志，公开分享前请检查；不包含备份、固件或 Sony 工具。")
        return 0

    return 2
