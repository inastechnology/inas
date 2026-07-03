import argparse
import json
from pathlib import Path

from ina_device_hub.firmware_manifest import FirmwareManifestValidationError, extract_firmware_manifest


def check_firmware_file(path: str | Path):
    firmware_path = Path(path)
    try:
        content = firmware_path.read_bytes()
    except OSError as exc:
        raise FirmwareManifestValidationError(f"firmware file cannot be read: {exc}") from exc
    return extract_firmware_manifest(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that firmware.bin embeds the INAS firmware manifest.")
    parser.add_argument("firmware", help="Path to firmware.bin")
    parser.add_argument("--json", action="store_true", help="Print only manifest JSON on success")
    args = parser.parse_args(argv)

    try:
        manifest = check_firmware_file(args.firmware)
    except FirmwareManifestValidationError as exc:
        print(f"NG: {exc}")
        return 1

    if not args.json:
        print("OK: firmware manifest found")
    print(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True))
    return 0
