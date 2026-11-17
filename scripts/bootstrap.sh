#!/usr/bin/env bash
set -euo pipefail

UPSTREAM="${1:?usage: bootstrap.sh <path-to-unlock>}"

if [ ! -d "$UPSTREAM" ]; then
    echo "upstream checkout not found: $UPSTREAM" >&2
    exit 1
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

echo
echo "Installed. Next:"
echo "  .venv/bin/zve10-installer doctor --upstream $UPSTREAM"
echo "  .venv/bin/zve10-installer inspect --upstream $UPSTREAM"
echo
echo "Remember: install the upstream toolkit dependencies in this venv too."
