#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: ./flash-linux.sh /dev/ttyACM0"
    exit 2
fi

python3 -m esptool --chip esp32s3 --port "$1" --baud 460800 \
    write-flash 0x0 rs485-debug-device-esp32s3.bin

echo "Flash completed. Reconnect the board and open USB Debug COM at 115200 bps."
