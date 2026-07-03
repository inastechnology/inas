import copy
import hashlib
import json
import os
import re
import socket
import time
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import quote

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

ARTIFACT_ROLLOUT_STATES = {"active", "paused", "revoked"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:+-]+$")
IPV4_HOST_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
OTA_UPDATE_REPLY_RETRY_DELAYS_SEC = (0.25, 0.6, 1.2)


class FirmwareArtifactValidationError(ValueError):
    pass


def _utc_now():
    return datetime.now(UTC).isoformat()


class FirmwareArtifactRepository:
    artifact_path = os.path.join(setting().get_work_dir(), ".firmware_artifacts.json")
    firmware_root = os.path.join(setting().get_work_dir(), "firmware")

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

    def firmware_path(self, device_kind: str, version: str):
        device_kind = _normalize_device_kind(device_kind)
        version = _normalize_version(version)
        return os.path.join(self.firmware_root, device_kind, version, "firmware.bin")

    def public_firmware_url(self, device_kind: str, version: str):
        device_kind = _normalize_device_kind(device_kind)
        version = _normalize_version(version)
        base_url = _firmware_base_url()
        return f"{base_url}/firmware/{quote(device_kind, safe='')}/{quote(version, safe='._:+-')}/firmware.bin"

    def upsert_binary(self, device_kind: str, version: str, content: bytes, metadata: dict | None = None):
        metadata = metadata or {}
        device_kind = _normalize_device_kind(device_kind)
        version = _normalize_version(version)
        if not isinstance(content, bytes | bytearray) or len(content) == 0:
            raise FirmwareArtifactValidationError("firmware binary must not be empty")

        binary = bytes(content)
        sha256 = hashlib.sha256(binary).hexdigest()
        path = self.firmware_path(device_kind, version)
        artifact = {
            "device_kind": device_kind,
            "version": version,
            "update_id": metadata.get("update_id"),
            "build_id": metadata.get("build_id"),
            "url": self.public_firmware_url(device_kind, version),
            "size": len(binary),
            "sha256": sha256,
            "rollout_state": metadata.get("rollout_state", "active"),
            "force": metadata.get("force", False),
            "allow_downgrade": metadata.get("allow_downgrade", False),
        }
        validate_firmware_artifact(version, artifact)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp-{uuid.uuid4()}"
        try:
            with open(tmp_path, "wb") as file:
                file.write(binary)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return self.upsert(version, artifact)


class OTAUpdateService:
    def __init__(self, repository=None, artifact_repository=None):
        self.repository = repository or device_config_repository()
        self.artifact_repository = artifact_repository or firmware_artifact_repository()
        self.mqtt_client = None

    def attach_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.sync_retained_offers()

    def get_artifacts(self):
        return self.artifact_repository.get_all()

    def upsert_artifact(self, version: str, artifact: dict):
        saved = self.artifact_repository.upsert(version, artifact)
        self.sync_retained_offers(device_kind=saved["device_kind"], target_firmware_version=saved["version"])
        return saved

    def upsert_firmware_binary(self, device_kind: str, version: str, content: bytes, metadata: dict | None = None):
        saved = self.artifact_repository.upsert_binary(device_kind, version, content, metadata=metadata)
        self.sync_retained_offers(device_kind=saved["device_kind"], target_firmware_version=saved["version"])
        return saved

    def get_firmware_path(self, device_kind: str, version: str):
        return self.artifact_repository.firmware_path(device_kind, version)

    def set_firmware_target(self, device_id: str, target_firmware_version: str | None):
        record = self.repository.set_firmware_target(device_id, target_firmware_version)
        self.sync_retained_offer_for_record(record)
        return record

    def list_ota_statuses(self, device_id: str, limit: int = 100):
        return self.repository.list_ota_statuses(device_id, limit=limit)

    def sync_retained_offers(self, *, device_kind: str | None = None, target_firmware_version: str | None = None):
        if self.mqtt_client is None:
            return []

        results = []
        for record in self.repository.get_all().values():
            if device_kind is not None and record.get("device_kind") != device_kind:
                continue
            if target_firmware_version is not None and record.get("target_firmware_version") != target_firmware_version:
                continue
            published = self.sync_retained_offer_for_record(record)
            if published is not None:
                results.append(published)
        return results

    def sync_retained_offer_for_record(self, record: dict):
        if self.mqtt_client is None:
            return None

        device_id = record.get("device_id")
        device_kind = record.get("device_kind")
        if not isinstance(device_id, str) or not device_id:
            return None
        if not _is_device_kind(device_kind):
            return None

        request_payload = {
            "request": "firmware_update",
            "schema_version": 1,
            "device_kind": device_kind,
            "firmware_version": record.get("firmware_version"),
            "firmware_build_id": record.get("firmware_build_id"),
        }
        offer = self.decide_offer(device_id, request_payload, record=record)
        if offer.get("action") == "update":
            published = self.publish_retained_offer(device_id, offer, notify=False, log_event=False)
            self._record_offer_publish(device_id, published["topic"], offer, published["mqtt_rc"], retain=True)
            return published

        published = self.clear_retained_offer(device_id, device_kind=device_kind, notify=False, log_event=False)
        if published["topic"]:
            self._record_offer_publish(device_id, published["topic"], {"action": "clear", "reason": offer.get("reason")}, published["mqtt_rc"], retain=True)
        return published

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

            record = self.repository.get(device_id)
            offer = self.decide_offer(device_id, request_payload, record=record)
            published = self.publish_reply(device_id, offer, notify=False, log_event=False)
            if offer.get("action") == "update":
                retained_offer_published = self.publish_retained_offer(device_id, offer, notify=False, log_event=False)
            else:
                retained_offer_published = self.clear_retained_offer(device_id, device_kind=request_payload.get("device_kind"), notify=False, log_event=False)
            retry_results = self._retry_update_offer(device_id, offer)

            append_device_event(
                "ota_request",
                "inbound",
                device_id,
                topic=message.get("topic"),
                category="ota",
                action="request",
                payload=request_payload,
            )
            self._record_decision(device_id, request_payload, record, offer, retry_results)
            self.repository.record_ota_request(device_id, request_payload)
            self._record_offer_publish(
                device_id,
                published["topic"],
                offer,
                published["mqtt_rc"],
                retain=False,
                retry_results=retry_results,
            )
            if retained_offer_published["topic"]:
                self._record_offer_publish(
                    device_id,
                    retained_offer_published["topic"],
                    offer if offer.get("action") == "update" else {"action": "clear"},
                    retained_offer_published["mqtt_rc"],
                    retain=True,
                )
            return True

        if action == "status":
            try:
                status_payload = _decode_json_payload(message.get("payload"))
            except ValueError:
                logger.exception("OTA status payload parse failure for device_id=%s", device_id)
                return True

            record = self.repository.record_ota_status(device_id, status_payload)
            self.sync_retained_offer_for_record(record)
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

    def publish_reply(self, device_id: str, offer: dict, *, notify: bool = True, log_event: bool = True):
        return self._publish_offer(device_id, offer, "reply", retain=False, notify=notify, log_event=log_event)

    def publish_retained_offer(self, device_id: str, offer: dict, *, notify: bool = True, log_event: bool = True):
        device_kind = offer.get("device_kind")
        if not _is_device_kind(device_kind):
            raise ValueError("retained OTA offer requires device_kind")
        topic = f"/kinds/{device_kind}/devices/{device_id}/ota/offer"
        return self._publish_offer_to_topic(device_id, topic, offer, retain=True, notify=notify, log_event=log_event)

    def clear_retained_offer(self, device_id: str, device_kind: str | None = None, *, notify: bool = True, log_event: bool = True):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        if not _is_device_kind(device_kind):
            record = self.repository.get(device_id)
            device_kind = record.get("device_kind") if isinstance(record, dict) else None
        if not _is_device_kind(device_kind):
            return {"topic": "", "payload": "", "mqtt_rc": 0}

        topic = f"/kinds/{device_kind}/devices/{device_id}/ota/offer"
        try:
            result = self.mqtt_client.publish(topic, "", qos=0, retain=True, notify=notify)
        except TypeError:
            result = self.mqtt_client.publish(topic, "", qos=0, retain=True)
        if log_event:
            self._record_offer_publish(device_id, topic, {"action": "clear"}, result.rc, retain=True)
        if result.rc != 0:
            logger.error("Failed to clear retained OTA offer for device_id=%s topic=%s rc=%s", device_id, topic, result.rc)
        return {"topic": topic, "payload": "", "mqtt_rc": result.rc}

    def _publish_offer(self, device_id: str, offer: dict, mode: str, *, retain: bool, notify: bool, log_event: bool):
        topic = f"/{device_id}/kinds/ota/{mode}"
        return self._publish_offer_to_topic(device_id, topic, offer, retain=retain, notify=notify, log_event=log_event)

    def _publish_offer_to_topic(self, device_id: str, topic: str, offer: dict, *, retain: bool, notify: bool, log_event: bool):
        if self.mqtt_client is None:
            raise RuntimeError("mqtt client is not attached")

        payload = json.dumps(offer, ensure_ascii=True, separators=(",", ":"))
        try:
            result = self.mqtt_client.publish(topic, payload, qos=0, retain=retain, notify=notify)
        except TypeError:
            result = self.mqtt_client.publish(topic, payload, qos=0, retain=retain)
        if log_event:
            self._record_offer_publish(device_id, topic, offer, result.rc, retain=retain)
        if result.rc != 0:
            logger.error("Failed to publish OTA offer for device_id=%s topic=%s rc=%s", device_id, topic, result.rc)
        return {"topic": topic, "payload": offer, "mqtt_rc": result.rc}

    def _record_offer_publish(self, device_id: str, topic: str, offer: dict, mqtt_rc: int, *, retain: bool, retry_results: list[dict] | None = None):
        payload = dict(offer)
        if retry_results is not None:
            payload["reply_retry_results"] = retry_results
        append_device_event(
            "ota_offer_publish",
            "outbound",
            device_id,
            topic=topic,
            category="ota",
            action=topic.rsplit("/", 1)[-1],
            payload=payload,
            mqtt_rc=mqtt_rc,
            retain=retain,
        )

    def _retry_update_offer(self, device_id: str, offer: dict):
        if offer.get("action") != "update":
            return []

        results = []
        for attempt, delay_sec in enumerate(OTA_UPDATE_REPLY_RETRY_DELAYS_SEC, start=1):
            time.sleep(delay_sec)
            published = self.publish_reply(device_id, offer, notify=False, log_event=False)
            results.append(
                {
                    "attempt": attempt,
                    "delay_ms": int(delay_sec * 1000),
                    "mqtt_rc": published["mqtt_rc"],
                }
            )
            if published["mqtt_rc"] != 0:
                logger.error(
                    "Failed to publish OTA offer retry for device_id=%s attempt=%s rc=%s",
                    device_id,
                    attempt,
                    published["mqtt_rc"],
                )
        return results

    def _record_decision(self, device_id: str, request_payload: dict, record: dict | None, offer: dict, retry_results: list[dict]):
        target = record.get("target_firmware_version") if isinstance(record, dict) else None
        request_device_kind = request_payload.get("device_kind")
        artifact = self.artifact_repository.get(target, request_device_kind) if target and _is_device_kind(request_device_kind) else None
        append_device_event(
            "ota_decision",
            "internal",
            device_id,
            category="ota",
            action=offer.get("action"),
            payload={
                "request": {
                    "seq": request_payload.get("seq"),
                    "device_kind": request_payload.get("device_kind"),
                    "firmware_version": request_payload.get("firmware_version"),
                    "firmware_build_id": request_payload.get("firmware_build_id"),
                    "running_partition": request_payload.get("running_partition"),
                    "free_heap": request_payload.get("free_heap"),
                },
                "device_record": {
                    "state": record.get("state") if isinstance(record, dict) else None,
                    "device_kind": record.get("device_kind") if isinstance(record, dict) else None,
                    "target_firmware_version": target,
                    "last_firmware_version": record.get("firmware_version") if isinstance(record, dict) else None,
                    "last_firmware_build_id": record.get("firmware_build_id") if isinstance(record, dict) else None,
                },
                "artifact": _decision_artifact_summary(artifact),
                "decision": {
                    "action": offer.get("action"),
                    "reason": offer.get("reason"),
                    "update_id": offer.get("update_id"),
                    "version": offer.get("version"),
                    "build_id": offer.get("build_id"),
                    "size": offer.get("size"),
                    "sha256": offer.get("sha256"),
                    "url": offer.get("url"),
                    "force": offer.get("force"),
                    "allow_downgrade": offer.get("allow_downgrade"),
                    "retry_count": len(retry_results),
                },
            },
        )


def validate_firmware_artifact(version: str, artifact: dict):
    if not isinstance(artifact, dict):
        raise FirmwareArtifactValidationError("artifact must be an object")

    version = _normalize_version(version)

    url = artifact.get("url")
    size = artifact.get("size")
    sha256 = artifact.get("sha256")
    device_kind = _normalize_device_kind(artifact.get("device_kind"))
    if not isinstance(url, str) or not url.startswith("http://"):
        raise FirmwareArtifactValidationError("url must be an HTTP URL")
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


def _decision_artifact_summary(artifact: dict | None):
    if artifact is None:
        return None
    return {
        "device_kind": artifact.get("device_kind"),
        "version": artifact.get("version"),
        "update_id": artifact.get("update_id"),
        "build_id": artifact.get("build_id"),
        "url": artifact.get("url"),
        "size": artifact.get("size"),
        "sha256": artifact.get("sha256"),
        "rollout_state": artifact.get("rollout_state"),
        "force": artifact.get("force"),
        "allow_downgrade": artifact.get("allow_downgrade"),
    }


def _artifact_key(device_kind: str, version: str):
    return f"{device_kind}:{version}"


def _is_device_kind(value):
    return isinstance(value, str) and DEVICE_KIND_RE.match(value) is not None


def _normalize_device_kind(value):
    if not _is_device_kind(value):
        raise FirmwareArtifactValidationError("device_kind must be exactly three uppercase letters")
    return value


def _normalize_version(version: str):
    if not isinstance(version, str) or not version.strip():
        raise FirmwareArtifactValidationError("version must be a non-empty string")
    version = version.strip()
    if SAFE_TOKEN_RE.match(version) is None:
        raise FirmwareArtifactValidationError("version contains unsupported characters")
    if len(version) >= 32:
        raise FirmwareArtifactValidationError("version must be shorter than 32 characters")
    return version


def _firmware_base_url():
    firmware_settings = setting().get("firmware")
    base_url = ""
    if isinstance(firmware_settings, dict):
        base_url = str(firmware_settings.get("base_url") or "").strip()
    base_url = base_url or os.environ.get("FIRMWARE_BASE_URL", "").strip()
    if not base_url:
        base_url = _build_firmware_base_url_from_hostname(firmware_settings)
    if not base_url.startswith("http://"):
        raise FirmwareArtifactValidationError("FIRMWARE_BASE_URL must start with http://")
    return base_url.rstrip("/")


def _build_firmware_base_url_from_hostname(firmware_settings):
    hostname = ""
    port = ""
    if isinstance(firmware_settings, dict):
        hostname = str(firmware_settings.get("hostname") or "").strip()
        port = str(firmware_settings.get("port") or "").strip()
    hostname = hostname or os.environ.get("FIRMWARE_HOSTNAME", "").strip() or os.environ.get("HOSTNAME", "").strip() or socket.gethostname().strip()
    port = port or os.environ.get("FIRMWARE_PORT", "").strip() or os.environ.get("HUB_HTTP_PORT", "39151").strip()

    if not hostname:
        raise FirmwareArtifactValidationError("FIRMWARE_HOSTNAME or HOSTNAME must be set before uploading firmware")
    if "://" in hostname or any(separator in hostname for separator in "/?#"):
        raise FirmwareArtifactValidationError("FIRMWARE_HOSTNAME must be a hostname, not a URL")
    if ":" in hostname and not (hostname.startswith("[") and hostname.endswith("]")):
        raise FirmwareArtifactValidationError("FIRMWARE_HOSTNAME must not include a port; use FIRMWARE_PORT")
    hostname = _normalize_firmware_hostname(hostname)

    try:
        port_number = int(port)
    except (TypeError, ValueError) as exc:
        raise FirmwareArtifactValidationError("FIRMWARE_PORT must be an integer") from exc
    if port_number < 1 or port_number > 65535:
        raise FirmwareArtifactValidationError("FIRMWARE_PORT must be between 1 and 65535")
    if port_number == 80:
        return f"http://{hostname}"
    return f"http://{hostname}:{port_number}"


def _normalize_firmware_hostname(hostname: str):
    if hostname.startswith("[") and hostname.endswith("]"):
        return hostname
    if hostname == "localhost" or "." in hostname or IPV4_HOST_RE.match(hostname):
        return hostname
    return f"{hostname}.local"


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
