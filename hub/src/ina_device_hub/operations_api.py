from flask import Blueprint, jsonify, request

from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.ota_update_service import FirmwareArtifactValidationError, ota_update_service
from ina_device_hub.user_context import current_user_from_request

operations_api = Blueprint("operations_api", __name__, url_prefix="/operations/api/v1")


def _actor_id() -> str:
    return current_user_from_request(request).email


@operations_api.get("/health")
def operations_health():
    return jsonify({"status": "ok", "actor": _actor_id(), "api_version": "v1"})


@operations_api.get("/devices")
def list_devices():
    requested_kind = str(request.args.get("device_kind") or "").strip().upper()
    requested_states = {value.strip() for value in request.args.getlist("state") if value.strip()}
    records = {}
    for device_id, record in ota_update_service().repository.get_all().items():
        device_kind = str(record.get("device_kind") or "").upper()
        state = str(record.get("state") or "pending")
        if requested_kind and device_kind != requested_kind:
            continue
        if requested_states and state not in requested_states:
            continue
        summary = dict(record)
        summary.pop("status_history", None)
        summary.pop("ota_status_history", None)
        records[device_id] = summary
    return jsonify({"items": records, "count": len(records)})


@operations_api.post("/devices/firmware-artifacts/<device_kind>/<version>")
def publish_firmware_artifact(device_kind, version):
    firmware_binary = request.get_data(cache=False)
    if not firmware_binary:
        return jsonify({"error": "firmware binary must not be empty"}), 400
    try:
        artifact = ota_update_service().upsert_firmware_binary(device_kind, version, firmware_binary)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    append_device_event(
        "operations_firmware_published",
        "operations",
        None,
        category="firmware",
        action="publish",
        payload={"actor": _actor_id(), "device_kind": artifact["device_kind"], "version": artifact["version"], "sha256": artifact["sha256"]},
    )
    return jsonify(artifact), 201


@operations_api.post("/devices/firmware-rollouts")
def create_firmware_rollout():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    device_kind = str(body.get("device_kind") or "").strip().upper()
    version = str(body.get("version") or "").strip()
    dry_run = body.get("dry_run", True)
    if len(device_kind) != 3 or not device_kind.isascii() or not device_kind.isalnum():
        return jsonify({"error": "device_kind must be a three-character ASCII code"}), 400
    if not version:
        return jsonify({"error": "version must not be empty"}), 400
    if not isinstance(dry_run, bool):
        return jsonify({"error": "dry_run must be a boolean"}), 400
    artifact = ota_update_service().artifact_repository.get(version, device_kind=device_kind)
    if artifact is None or artifact.get("rollout_state") != "active":
        return jsonify({"error": "active firmware artifact not found"}), 409

    requested_ids = body.get("device_ids")
    if requested_ids is not None and (not isinstance(requested_ids, list) or not all(isinstance(value, str) and value.strip() for value in requested_ids)):
        return jsonify({"error": "device_ids must be an array of non-empty strings"}), 400
    requested_id_set = {value.strip() for value in requested_ids} if requested_ids is not None else None
    candidates = []
    skipped = []
    records = ota_update_service().repository.get_all()
    if requested_id_set is not None:
        for missing_id in sorted(requested_id_set - set(records)):
            skipped.append({"device_id": missing_id, "reason": "not_found"})
    for device_id, record in sorted(records.items()):
        if requested_id_set is not None and device_id not in requested_id_set:
            continue
        if str(record.get("device_kind") or "").upper() != device_kind:
            if requested_id_set is not None:
                skipped.append({"device_id": device_id, "reason": "device_kind_mismatch"})
            continue
        if record.get("state") == "retired":
            skipped.append({"device_id": device_id, "reason": "retired"})
            continue
        candidates.append(device_id)

    updated = []
    if not dry_run:
        for device_id in candidates:
            record = ota_update_service().set_firmware_target(device_id, version)
            updated.append({"device_id": device_id, "target_firmware_version": record.get("target_firmware_version")})
            append_device_event(
                "operations_firmware_target_set",
                "operations",
                device_id,
                category="firmware",
                action="set_target",
                payload={"actor": _actor_id(), "device_kind": device_kind, "version": version},
            )

    return jsonify(
        {
            "device_kind": device_kind,
            "version": version,
            "dry_run": dry_run,
            "candidate_device_ids": candidates,
            "updated": updated,
            "skipped": skipped,
        }
    )
