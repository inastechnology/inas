import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from ina_edge_runtime.mqtt_topics import parse_mqtt_message
from ina_edge_runtime.protocol import format_timestamp
from ina_edge_runtime.store import EdgeStore

LOGGER = logging.getLogger(__name__)
MAX_MQTT_PAYLOAD_BYTES = 256 * 1024
MAX_RUNTIME_CONFIG_BYTES = 4095
MAX_EVENT_TEXT_LENGTH = 4096


class DeviceMessageController:
    def __init__(self, *, store: EdgeStore, node_id: str, publisher):
        self.store = store
        self.node_id = node_id
        self.publisher = publisher

    def handle_message(self, topic: str, payload: bytes) -> bool:
        if len(payload) > MAX_MQTT_PAYLOAD_BYTES:
            self._enqueue_event(
                "mqtt.payload_rejected",
                payload={"topic": topic, **_bounded_payload(payload)},
            )
            return False
        parsed = parse_mqtt_message(topic, payload)
        message_type = parsed["message_type"]
        if message_type == "device_config":
            return self._handle_device_message(parsed)
        if message_type == "sensor_data":
            return self._handle_sensor_message(parsed)
        if message_type == "mqtt_broker_log":
            self._enqueue_event(
                "mqtt.broker_log",
                payload={"topic": topic, "kind": parsed.get("kind"), "message": _safe_text(payload)},
            )
            return True
        self._enqueue_event("mqtt.unknown_topic", payload={"topic": topic, **_bounded_payload(payload)})
        return False

    def _handle_device_message(self, message: dict[str, Any]) -> bool:
        device_id = message["device_id"]
        category = message.get("category")
        action = message.get("action")
        if category == "config" and action == "request":
            self._reply_runtime_config(device_id, message.get("topic"))
            return True

        event_type = {
            ("agri", "immediate"): "device.status",
            ("debug", "log"): "device.debug_log",
            ("ota", "request"): "device.ota_request",
            ("ota", "status"): "device.ota_status",
        }.get((category, action), "device.message")
        self._enqueue_event(
            event_type,
            device_id=device_id,
            payload={
                "topic": message.get("topic"),
                "category": category,
                "action": action,
                "body": _bounded_payload(message.get("payload")),
            },
        )
        return True

    def _handle_sensor_message(self, message: dict[str, Any]) -> bool:
        kind = message.get("kind")
        event_type = "device.telemetry" if kind == "telemetry" else "device.sensor"
        self._enqueue_event(
            event_type,
            device_id=message.get("device_id"),
            payload={
                "topic": message.get("topic"),
                "kind": kind,
                "sequence_id": message.get("seqId"),
                "body": _bounded_payload(message.get("payload")),
            },
        )
        return True

    def _reply_runtime_config(self, device_id: str, request_topic: str | None) -> None:
        resource = self.store.get_desired_resource("device.runtime_config", device_id)
        if resource is None or resource.operation != "upsert" or not isinstance(resource.payload, dict):
            self._enqueue_event(
                "device.config_cache_miss",
                device_id=device_id,
                payload={"request_topic": request_topic},
            )
            return

        encoded = json.dumps(resource.payload, ensure_ascii=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_RUNTIME_CONFIG_BYTES:
            self._enqueue_event(
                "device.config_invalid",
                device_id=device_id,
                payload={"reason": "payload_too_large", "revision": resource.revision},
            )
            return

        reply_topic = f"/{device_id}/kinds/config/reply"
        result = self.publisher.publish(reply_topic, encoded, qos=0, retain=False)
        self._enqueue_event(
            "device.config_reply",
            device_id=device_id,
            payload={
                "request_topic": request_topic,
                "reply_topic": reply_topic,
                "revision": resource.revision,
                "mqtt_rc": int(result.rc),
            },
        )

    def _enqueue_event(self, event_type: str, *, payload: Any, device_id: str | None = None) -> None:
        try:
            self.store.enqueue_event(
                event_id=str(uuid.uuid4()),
                origin_node_id=self.node_id,
                event_type=event_type,
                occurred_at=format_timestamp(datetime.now(UTC)),
                device_id=device_id,
                payload=payload,
            )
        except Exception:
            LOGGER.exception("Failed to enqueue Edge event type=%s device_id=%s", event_type, device_id)


def _bounded_payload(payload: Any) -> Any:  # noqa: PLR0911
    if payload is None:
        return None
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        raw = payload
    else:
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError):
            return {"encoding": "unsupported", "type": type(payload).__name__}
        return payload

    if len(raw) > MAX_MQTT_PAYLOAD_BYTES:
        return {
            "encoding": "omitted",
            "reason": "payload_too_large",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "encoding": "omitted",
            "reason": "binary_payload",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "encoding": "utf-8",
            "text": text[:MAX_EVENT_TEXT_LENGTH],
            "truncated": len(text) > MAX_EVENT_TEXT_LENGTH,
        }


def _safe_text(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")[:4096]
