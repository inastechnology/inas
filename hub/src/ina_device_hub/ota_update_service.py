import copy
import json
import os
import re
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

ARTIFACT_ROLLOUT_STATES = {"active", "paused", "revoked"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:+-]+$")


class FirmwareArtifactValidationError(ValueError):
    pass


def _utc_now():
    return datetime.now(UTC).isoformat()


class FirmwareArtifactRepository:
    artifact_path = os.path.join(setting().get_work_dir(), ".firmware_artifacts.json")

    def __init__(self):
        self.artifacts = {}
        self.load()

    def load(self):
        if not os.path.exists(self.artifact_path):
            with open(self.artifact_path, "w", encoding="utf-8") as file:
                json.dump({}, file)
        try:
            with open(self.artifact_path, encoding="utf-8") as file:
                self.artifacts = json.load(file)
        except FileNotFoundError:
            self.artifacts = {}

    def save(self):
        with open(self.artifact_path, "w", encoding="utf-8") as file:
            json.dump(self.artifacts, file, ensure_ascii=True, indent=2)

    def get(self, version: str, device_kind: str | None = None):
        artifact_key = _artifact_key(device_kind, version) if device_kind else version
        artifact = self.artifacts.get(artifact_key)
        return copy.deepcopy(_normalize_artifact(version, artifact)) if artifact else None

    def get_all(self):
        return {key: copy.deepcopy(_normalize_artifact(artifact.get("version", key), artifact)) for key, artifact in self.artifacts.items()}

    def upsert(self, version: str, artifact: dict):
        normalized = validate_firmware_artifact(version, artifact)
        artifact_key = _artifact_key(normalized["device_kind"], normalized["version"])
        existing = self.artifacts.get(artifact_key) or {}
        normalized["created_at"] = existing.get("created_at") or _utc_now()
        normalized["updated_at"] = _utc_now()
        self.artifacts[artifact_key] = normalized
        self.save()
        return copy.deepcopy(normalized)


class OTAUpdateService:
    def __init__(self, repository=None, artifact_repository=None):
        self.repository = repository or device_config_repository()
        self.artifact_repository = artifact_repository or firmware_artifact_repository()
        self.mqtt_client = None

    def attach_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def get_artifacts(self):
        return self.artifact_repository.get_all()

    def upsert_artifact(self, version: str, artifact: dict):
        return self.artifact_repository.upsert(version, artifact)

    def set_firmware_target(self, device_id: str, target_firmware_version: str | None):
        return self.repository.set_firmware_target(device_id, target_firmware_version)

    def list_ota_statuses(self, device_id: str, limit: int = 100):
        return self.repository.list_ota_statuses(device_id, limit=limit)

    def handle_mqtt_message(self, mqtt_client, message: dict):
        del mqtt_client
        if message.get("message_type") != "device_config":
            return False
        if message.get("category") != "ota":
            return False

        device_id = message["device_id"]
        action = message.get("action")
        if action == "request":
            try:
                request_payload = _decode_json_payload(message.get("payload"))
            except ValueError:
                logger.exception("OTA request payload parse failure for device_id=%s", device_id)
                request_payload = {}

            append_device_event(
                "ota_request",
                "inbound",
                device_id,
                topic=message.get("topic"),
                category="ota",
                action="request",
                payload=request_payload,
            )
            record = self.repository.record_ota_request(device_id, request_payload)
            offer = self.decide_offer(device_id, request_payload, record=record)
            self.publish_reply(device_id, offer)
            return True

        if action == "status":
            try:
                status_payload = _decode_json_payload(message.get("payload"))
            except ValueError:
                logger.exception("OTA status payload parse failure for device_id=%s", device_id)
                return True

            record = self.repository.record_ota_status(device_id, status_payload)
            append_device_event(
                "ota_status",
                "inbound",
                device_id,
                topic=message.get("topic"),
                category="ota",
                action="status",
                payload=status_payload,
                occurred_at=record["last_ota_status_at"],
            )
            return True

        return False

    def decide_offer(self, device_id: str, request_payload: dict, record: dict | None = None):
        record = record or self.repository.get(device_id)
        if record is None:
            return _none_offer("unknown_device")

        if record.get("state") != "active":
            return _none_offer("device_not_active")

        if request_payload.get("request") != "firmware_update" or request_payload.get("schema_version") != 1:
            return _none_offer("invalid_request")

        request_device_kind = request_payload.get("device_kind")
        if not _is_device_kind(request_device_kind):
            return _none_offer("invalid_device_kind")

        record_device_kind = record.get("device_kind")
        if record_device_kind and record_device_kind != request_device_kind:
            return _none_offer("device_kind_mismatch")

        target = record.get("target_firmware_version")
        current = request_payload.get("firmware_version")
        if not target:
            return _none_offer("no_target")
        if current == target:
            return _none_offer("already_target")

        artifact = self.artifact_repository.get(target, request_device_kind)
        if artifact is None:
            return _none_offer("artifact_missing")
        if artifact.get("device_kind") != request_device_kind:
            return _none_offer("artifact_device_kind_mismatch")
        if artifact.get("rollout_state") != "active":
            return _none_offer(f"artifact_{artifact.get('rollout_state')}")
        if not artifact.get("allow_downgrade") and _is_version_downgrade(current, target):
            return _none_offer("downgrade_rejected")

        return {
            "schema_version": 1,
            "action": "update",
            "device_kind": artifact["device_kind"],
            "update_id": artifact["update_id"],
            "version": artifact["version"],
            "build_id": artifact.get("build_id"),
            "url": artifact["url"],
            "size": artifact["size"],
            "sha256": artifact["sha256"],
            "force": artifact.get("force", False),
            "allow_downgrade": artifact.get("allow_downgrade", False),
        }

    def publish_reply(self, device_id: str, offer: dict):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        topic = f"/{device_id}/kinds/ota/reply"
        payload = json.dumps(offer, ensure_ascii=True, separators=(",", ":"))
        result = self.mqtt_client.publish(topic, payload, qos=0, retain=False)
        append_device_event(
            "ota_offer_publish",
            "outbound",
            device_id,
            topic=topic,
            category="ota",
            action="reply",
            payload=offer,
            mqtt_rc=result.rc,
            retain=False,
        )
        if result.rc != 0:
            logger.error("Failed to publish OTA offer for device_id=%s topic=%s rc=%s", device_id, topic, result.rc)
        return {"topic": topic, "payload": offer, "mqtt_rc": result.rc}


def validate_firmware_artifact(version: str, artifact: dict):
    if not isinstance(version, str) or not version.strip():
        raise FirmwareArtifactValidationError("version must be a non-empty string")
    if not isinstance(artifact, dict):
        raise FirmwareArtifactValidationError("artifact must be an object")

    version = version.strip()
    if SAFE_TOKEN_RE.match(version) is None:
        raise FirmwareArtifactValidationError("version contains unsupported characters")
    if len(version) >= 32:
        raise FirmwareArtifactValidationError("version must be shorter than 32 characters")

    url = artifact.get("url")
    size = artifact.get("size")
    sha256 = artifact.get("sha256")
    device_kind = artifact.get("device_kind")
    if not _is_device_kind(device_kind):
        raise FirmwareArtifactValidationError("device_kind must be exactly three uppercase letters")
    if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
        raise FirmwareArtifactValidationError("url must be an HTTP or HTTPS URL")
    if len(url) >= 256:
        raise FirmwareArtifactValidationError("url must be shorter than 256 characters")
    if not isinstance(size, int) or size <= 0:
        raise FirmwareArtifactValidationError("size must be a positive integer")
    if not isinstance(sha256, str) or SHA256_RE.match(sha256) is None:
        raise FirmwareArtifactValidationError("sha256 must be a 64-character hex string")

    rollout_state = artifact.get("rollout_state", "active")
    if rollout_state not in ARTIFACT_ROLLOUT_STATES:
        raise FirmwareArtifactValidationError(f"rollout_state must be one of: {', '.join(sorted(ARTIFACT_ROLLOUT_STATES))}")

    update_id = artifact.get("update_id") or f"watering-device-{version}-{sha256[:8].lower()}"
    if not isinstance(update_id, str) or SAFE_TOKEN_RE.match(update_id) is None:
        raise FirmwareArtifactValidationError("update_id contains unsupported characters")
    if len(update_id) >= 64:
        raise FirmwareArtifactValidationError("update_id must be shorter than 64 characters")

    build_id = artifact.get("build_id")
    if build_id is not None and not isinstance(build_id, str):
        raise FirmwareArtifactValidationError("build_id must be a string or null")
    if build_id is not None and SAFE_TOKEN_RE.match(build_id) is None:
        raise FirmwareArtifactValidationError("build_id contains unsupported characters")
    if build_id is not None and len(build_id) >= 64:
        raise FirmwareArtifactValidationError("build_id must be shorter than 64 characters")

    return {
        "device_kind": device_kind,
        "version": version,
        "update_id": update_id,
        "build_id": build_id,
        "url": url,
        "size": size,
        "sha256": sha256.lower(),
        "rollout_state": rollout_state,
        "force": bool(artifact.get("force", False)),
        "allow_downgrade": bool(artifact.get("allow_downgrade", False)),
    }


def _normalize_artifact(version: str, artifact: dict):
    normalized = validate_firmware_artifact(version, artifact)
    normalized["created_at"] = artifact.get("created_at")
    normalized["updated_at"] = artifact.get("updated_at")
    return normalized


def _none_offer(reason: str):
    return {
        "schema_version": 1,
        "action": "none",
        "reason": reason,
    }


def _artifact_key(device_kind: str, version: str):
    return f"{device_kind}:{version}"


def _is_device_kind(value):
    return isinstance(value, str) and DEVICE_KIND_RE.match(value) is not None


def _decode_json_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("payload must be valid JSON") from exc
    else:
        decoded = payload

    if not isinstance(decoded, dict):
        raise ValueError("payload must be a JSON object")
    return decoded


def _is_version_downgrade(current: str | None, target: str | None):
    current_tuple = _version_tuple(current)
    target_tuple = _version_tuple(target)
    if current_tuple is None or target_tuple is None:
        return False
    return target_tuple < current_tuple


def _version_tuple(version: str | None):
    if not isinstance(version, str):
        return None
    parts = version.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values = []
    for part in parts:
        if not part.isdigit():
            return None
        values.append(int(part))
    while len(values) < 4:
        values.append(0)
    return tuple(values)


@lru_cache(maxsize=1)
def firmware_artifact_repository():
    return FirmwareArtifactRepository()


@lru_cache(maxsize=1)
def ota_update_service():
    return OTAUpdateService()
