#!/usr/bin/env python3
"""Validate firmware-owned Device Definitions and build the Hub registry."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEVICE_ROOT = ROOT / "client-devices"
OUTPUT = ROOT / "hub/src/ina_device_hub/device_definitions/generated/registry.json"
REFERENCES = {
    "runtime_config": "runtime_config",
    "status": "status",
    "ui": "ui",
    "actions": "actions",
}


def _read_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing Device Definition file: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Device Definition must be an object: {path.relative_to(ROOT)}")
    return value


def build_registry():
    definitions = {}
    for device_path in sorted(DEVICE_ROOT.glob("*/hub-definition/device.json")):
        directory = device_path.parent
        definition = _read_json(device_path)
        device = definition.get("device")
        files = definition.get("files")
        if definition.get("schema_version") != 1 or not isinstance(device, dict) or not isinstance(files, dict):
            raise ValueError(f"invalid Device Definition header: {device_path.relative_to(ROOT)}")
        kind = str(device.get("kind") or "").strip().upper()
        if len(kind) != 3 or not kind.isascii() or not kind.isalnum():
            raise ValueError(f"device.kind must be a three-character ASCII code: {device_path.relative_to(ROOT)}")
        if kind in definitions:
            raise ValueError(f"duplicate device kind: {kind}")
        for collection in ("sensor_slots", "output_slots", "runtime_sections"):
            if not isinstance(definition.get(collection), list):
                raise ValueError(f"{collection} must be an array for {kind}")
        slot_ids = [str(slot.get("id") or "") for slot in definition["output_slots"] if isinstance(slot, dict)]
        if not all(slot_ids) or len(slot_ids) != len(set(slot_ids)):
            raise ValueError(f"output slot IDs must be non-empty and unique for {kind}")
        assembled = dict(definition)
        assembled["source"] = str(directory.relative_to(ROOT))
        for file_key, registry_key in REFERENCES.items():
            relative_name = files.get(file_key)
            if not isinstance(relative_name, str) or Path(relative_name).name != relative_name:
                raise ValueError(f"invalid {file_key} file reference for {kind}")
            assembled[registry_key] = _read_json(directory / relative_name)
        send_keys = assembled["runtime_config"].get("send_keys")
        if not isinstance(send_keys, list) or not send_keys or len(send_keys) != len(set(send_keys)):
            raise ValueError(f"runtime_config.send_keys must be a non-empty unique array for {kind}")
        fixed_values = assembled["runtime_config"].get("fixed_values", {})
        if not isinstance(fixed_values, dict) or not all(isinstance(path, str) and path and path.split(".", 1)[0] in send_keys for path in fixed_values):
            raise ValueError(f"runtime_config.fixed_values must use paths below send_keys for {kind}")
        if assembled["status"].get("metrics") != definition["sensor_slots"]:
            raise ValueError(f"status metrics must match device sensor_slots for {kind}")
        definitions[kind] = assembled
    if not definitions:
        raise ValueError("no Device Definitions found")
    return {"schema_version": 1, "definitions": definitions}


def serialized_registry():
    return json.dumps(build_registry(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the generated registry is stale")
    args = parser.parse_args()
    expected = serialized_registry()
    if args.check:
        actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if actual != expected:
            print(f"Device Definition registry is stale: {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
