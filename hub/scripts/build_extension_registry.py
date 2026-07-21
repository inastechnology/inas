#!/usr/bin/env python3
"""Validate repository Extensions and build the Hub Extension registry."""

import argparse
import json
import sys
from pathlib import Path

from ina_device_hub.extension_manifest import validate_extension_manifest

ROOT = Path(__file__).resolve().parents[2]
EXTENSION_ROOT = ROOT / "extensions"
OUTPUT = ROOT / "hub/src/ina_device_hub/extensions/generated/registry.json"


def _read_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing Extension file: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Extension manifest must be an object: {path.relative_to(ROOT)}")
    return value


def build_registry():
    extensions = {}
    for manifest_path in sorted(EXTENSION_ROOT.glob("*/extension.json")):
        manifest = _read_json(manifest_path)
        extension_id = str(manifest.get("id") or "").strip()
        validate_extension_manifest(manifest)
        if extension_id in extensions:
            raise ValueError(f"duplicate Extension ID: {extension_id}")
        assembled = dict(manifest)
        assembled["source"] = str(manifest_path.parent.relative_to(ROOT))
        extensions[extension_id] = assembled
    return {"schema_version": 1, "extension_api_version": 1, "extensions": extensions}


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
            print(f"Extension registry is stale: {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
