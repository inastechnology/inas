#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

echo "INAS Shipping Tool - initial setup"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m platformio platform install "espressif32@6.10.0"
.venv/bin/python -c "import esptool, serial, tkinterdnd2"
.venv/bin/python -m platformio platform show espressif32

cat > .shipping-setup.json <<EOF
{"platformio":"6.1.18","espressif32":"6.10.0"}
EOF

echo "Setup completed. Run ./start-linux.sh."
