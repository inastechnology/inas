#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ ! -f ".shipping-setup.json" ]; then
    ./setup-linux.sh
fi

exec .venv/bin/python run.py
