# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build for the GUI (windowed) installer."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO = Path(SPECPATH).parent
UPSTREAM = Path(os.environ.get("ZVE10_UPSTREAM_BUILD", REPO / "build" / "upstream")).resolve()

datas = [
    (str(UPSTREAM), "upstream"),
    (str(REPO / "compat"), "compat"),
    (str(REPO / "vendor" / "zadig"), "vendor/zadig"),
]
if os.environ.get("ZVE10_READ_ONLY_BUILD") == "1":
    datas.append((str(REPO / "packaging" / "READ_ONLY"), "."))
for package in ("libusb_package", "certifi", "axmlparserpy", "customtkinter"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

hiddenimports = []
for package in (
    "usb",
    "libusb_package",
    "Cryptodome",
    "asn1crypto",
    "yaml",
    "tlslite",
    "serial",
    "axmlparserpy",
    "pycparser",
    "certifi",
    "six",
    "comtypes",
    "win32api",
    "win32com",
    "pythoncom",
    "pywintypes",
    "customtkinter",
    "darkdetect",
):
    try:
        found = collect_submodules(package)
    except Exception:
        found = []
    hiddenimports += found or [package]

hiddenimports += ["zve10_installer.sound_server"]

a = Analysis(
    [str(REPO / "packaging" / "gui_entry.py")],
    pathex=[str(REPO / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ZV-E10-Installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
