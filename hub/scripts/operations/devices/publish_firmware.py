#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))

from common.api_client import OperationsApiClient, OperationsApiError, load_operations_env  # noqa: E402


def _parser():
    parser = argparse.ArgumentParser(description="Publish firmware and optionally reserve an OTA rollout through the Hub Operations API.")
    parser.add_argument("firmware", type=Path, help="firmware.bin path")
    parser.add_argument("--device-kind", required=True, help="Three-character device kind, for example WTR")
    parser.add_argument("--version", required=True, help="Firmware version embedded in the binary")
    parser.add_argument("--device-id", action="append", default=[], help="Limit rollout to a device ID; repeat for multiple devices")
    parser.add_argument("--env-file", default=str(Path("~/.config/inas/operations-api.env").expanduser()))
    parser.add_argument("--apply", action="store_true", help="Apply targets after a successful dry-run; default only publishes and previews")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    firmware_path = args.firmware.expanduser().resolve()
    if not firmware_path.is_file() or firmware_path.stat().st_size == 0:
        raise OperationsApiError(f"firmware binary not found or empty: {firmware_path}")
    device_kind = args.device_kind.strip().upper()
    version = args.version.strip()
    binary = firmware_path.read_bytes()
    local_sha256 = hashlib.sha256(binary).hexdigest()
    client = OperationsApiClient(load_operations_env(args.env_file))

    health = client.get("health")
    artifact = client.post_binary(f"devices/firmware-artifacts/{device_kind}/{version}", binary)
    if artifact.get("sha256") != local_sha256:
        raise OperationsApiError(f"artifact SHA-256 mismatch: local={local_sha256} remote={artifact.get('sha256')}")
    rollout = {"device_kind": device_kind, "version": version, "dry_run": True}
    if args.device_id:
        rollout["device_ids"] = args.device_id
    preview = client.post_json("devices/firmware-rollouts", rollout)
    result = {"health": health, "artifact": artifact, "preview": preview}

    if args.apply:
        apply_payload = dict(rollout)
        apply_payload["dry_run"] = False
        applied = client.post_json("devices/firmware-rollouts", apply_payload)
        if applied.get("candidate_device_ids") != preview.get("candidate_device_ids"):
            raise OperationsApiError("rollout candidates changed between dry-run and apply")
        result["applied"] = applied
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OperationsApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
