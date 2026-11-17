#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM="${1:?usage: build_exe.sh <path-to-unlock>}"
PYTHON="${PYTHON:-python3}"
STAGE="$REPO/build/upstream"

to_native() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

rm -rf "$STAGE" "$REPO/dist" "$REPO/build/pyinstaller"
mkdir -p "$STAGE"

tar -C "$UPSTREAM" \
    --exclude=private \
    --exclude=.git \
    --exclude=__pycache__ \
    --exclude='*.bin' \
    --exclude='*.elf' \
    -cf - . | tar -C "$STAGE" -xf -

main="$(git -C "$UPSTREAM" rev-parse HEAD)"
toolkit="$(git -C "$UPSTREAM/vendor/zv-e10-toolkit" rev-parse HEAD)"
pmca="$(git -C "$UPSTREAM/vendor/zv-e10-toolkit/linux/vendor/Sony-PMCA-RE" rev-parse HEAD)"

printf '{\n  "main": "%s",\n  "toolkit": "%s",\n  "pmca": "%s"\n}\n' \
    "$main" "$toolkit" "$pmca" > "$STAGE/PIN.json"

export ZVE10_UPSTREAM_BUILD="$(to_native "$STAGE")"
"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "$(to_native "$REPO/dist")" \
    --workpath "$(to_native "$REPO/build/pyinstaller")" \
    "$(to_native "$REPO/packaging/zve10_installer.spec")"

"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "$(to_native "$REPO/dist")" \
    --workpath "$(to_native "$REPO/build/pyinstaller-gui")" \
    "$(to_native "$REPO/packaging/zve10_installer_gui.spec")"

echo
echo "Built:"
echo "  $REPO/dist/zve10-installer.exe   (console CLI)"
echo "  $REPO/dist/ZV-E10-Installer.exe  (GUI)"
