import json
import os
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting

MAX_TEXT_PAYLOAD_LENGTH = 4096
MQTT_CONNECTION_EVENT_TYPES = {
    "mqtt_client_connected",
    "mqtt_client_disconnected",
    "mqtt_client_connection_attempt",
    "mqtt_broker_log",
    "mqtt_hub_connected",
    "mqtt_hub_connect_failed",
}


def append_device_event(
    event_type: str,
    direction: str,
    device_id: str | None,
    *,
    topic: str | None = None,
    category: str | None = None,
    action: str | None = None,
    kind: str | None = None,
    seq_id: str | int | None = None,
    payload: Any = None,
    occurred_at: str | None = None,
    mqtt_rc: int | None = None,
    retain: bool | None = None,
):
    occurred_at = occurred_at or _utc_now()
    normalized_payload = _normalize_payload(payload)
    event = {
        "occurred_at": occurred_at,
        "event_type": event_type,
        "direction": direction,
        "device_id": device_id,
        "topic": topic,
        "category": category,
        "action": action,
        "kind": kind,
        "seq_id": seq_id,
        "mqtt_rc": mqtt_rc,
        "retain": retain,
        "payload": normalized_payload,
    }
    if isinstance(normalized_payload, dict):
        event.update(_status_derived_fields(occurred_at, normalized_payload))

    try:
        _append_device_event_to_turso(event)
    except BaseException:
        logger.exception("Failed to append device event log to Turso")

    try:
        _append_device_event_to_jsonl(event)
    except Exception:
        logger.exception("Failed to append device event log fallback")

    return event


def append_mqtt_hub_event(event_type: str, direction: str, *, topic: str, payload: Any = None, mqtt_rc: int | None = None):
    action = "connect" if event_type == "mqtt_hub_connected" else "connect_failed"
    return append_device_event(
        event_type,
        direction,
        None,
        topic=topic,
        category="mqtt",
        action=action,
        payload=payload,
        mqtt_rc=mqtt_rc,
    )


def append_mqtt_message_event(parsed_message: dict):
    message_type = parsed_message.get("message_type")
    if message_type == "mqtt_broker_log":
        return append_mqtt_broker_log(parsed_message.get("topic"), parsed_message.get("payload"))

    topic = parsed_message.get("topic")
    if not topic:
        return None

    return append_device_event(
        "mqtt_message_received",
        "inbound",
        parsed_message.get("device_id"),
        topic=topic,
        category=parsed_message.get("category"),
        action=parsed_message.get("action"),
        kind=parsed_message.get("kind"),
        seq_id=parsed_message.get("seqId"),
        payload=parsed_message.get("payload"),
    )


def append_mqtt_broker_log(topic: str | None, payload: Any):
    payload_text = _payload_to_text(payload)
    event_type, device_id, action, details = _parse_broker_log(payload_text)
    return append_device_event(
        event_type,
        "broker",
        device_id,
        topic=topic,
        category="mqtt",
        action=action,
        payload={"message": payload_text, **details},
    )


def list_device_events(
    *,
    limit: int = 100,
    device_id: str | None = None,
    event_type: str | None = None,
    direction: str | None = None,
    connection_events_only: bool = False,
):
    try:
        return _fetch_device_events_from_turso(
            limit=limit,
            device_id=device_id,
            event_type=event_type,
            direction=direction,
            connection_events_only=connection_events_only,
        )
    except BaseException:
        logger.exception("Failed to fetch device event logs from Turso; using JSONL fallback")
        return _fetch_device_events_from_jsonl(
            limit=limit,
            device_id=device_id,
            event_type=event_type,
            direction=direction,
            connection_events_only=connection_events_only,
        )


def _append_device_event_to_turso(event: dict):
    _device_event_db_connector().insert_device_event(event)


def _append_device_event_to_jsonl(event: dict):
    with open(_event_log_path(), "a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")


def _fetch_device_events_from_turso(
    *,
    limit: int = 100,
    device_id: str | None = None,
    event_type: str | None = None,
    direction: str | None = None,
    connection_events_only: bool = False,
):
    rows = _device_event_db_connector().fetch_device_events(
        limit=limit,
        device_id=device_id,
        event_type=event_type,
        direction=direction,
        connection_events_only=connection_events_only,
    )
    events = [_row_to_event(row) for row in rows]
    events.reverse()
    return events


@lru_cache(maxsize=1)
def _device_event_db_connector():
    from ina_device_hub.ina_db_connector import InaDBConnector

    return InaDBConnector()


def _fetch_device_events_from_jsonl(
    *,
    limit: int = 100,
    device_id: str | None = None,
    event_type: str | None = None,
    direction: str | None = None,
    connection_events_only: bool = False,
):
    events = []
    try:
        with open(_event_log_path(), encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid device event log line: %r", line[:200])
                    continue
                if device_id and event.get("device_id") != device_id:
                    continue
                if event_type and event.get("event_type") != event_type:
                    continue
                if direction and event.get("direction") != direction:
                    continue
                if connection_events_only and event.get("event_type") not in MQTT_CONNECTION_EVENT_TYPES:
                    continue
                events.append(event)
    except FileNotFoundError:
        return []

    return events[-limit:]


def _row_to_event(row):
    payload = row[14]
    try:
        payload = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        pass

    return {
        "id": row[0],
        "occurred_at": row[1],
        "event_type": row[2],
        "direction": row[3],
        "device_id": row[4],
        "topic": row[5],
        "category": row[6],
        "action": row[7],
        "kind": row[8],
        "seq_id": row[9],
        "mqtt_rc": row[10],
        "retain": bool(row[11]) if row[11] is not None else None,
        "next_sleep_sec": row[12],
        "next_wake_at": row[13],
        "payload": payload,
    }


def _event_log_path():
    log_dir = os.path.join(setting().get_work_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "device_events.jsonl")


def _utc_now():
    return datetime.now(UTC).isoformat()


def _normalize_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")

    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            if len(payload) <= MAX_TEXT_PAYLOAD_LENGTH:
                return payload
            return {
                "text": payload[:MAX_TEXT_PAYLOAD_LENGTH],
                "truncated": True,
                "original_length": len(payload),
            }

    return payload


def _payload_to_text(payload):
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _parse_broker_log(message: str):
    connected = re.search(r"New client connected from (?P<address>[^ ]+) as (?P<client_id>[^ ]+)", message)
    if connected:
        return (
            "mqtt_client_connected",
            _device_id_from_client_id(connected.group("client_id")),
            "connect",
            {"client_id": connected.group("client_id"), "remote_address": connected.group("address")},
        )

    new_connection = re.search(r"New connection from (?P<address>[^ ]+) on port (?P<port>\d+)", message)
    if new_connection:
        return (
            "mqtt_client_connection_attempt",
            None,
            "connection_attempt",
            {"remote_address": new_connection.group("address"), "listener_port": int(new_connection.group("port"))},
        )

    timeout = re.search(r"Client (?P<client_id>[^ ]+) has exceeded timeout, disconnecting", message)
    if timeout:
        client_id = timeout.group("client_id")
        return (
            "mqtt_client_disconnected",
            _device_id_from_client_id(client_id),
            "disconnect_timeout",
            {"client_id": client_id, "reason": "timeout"},
        )

    disconnected = re.search(r"Client (?P<client_id>[^ ]+) disconnected", message)
    if disconnected:
        client_id = disconnected.group("client_id")
        return (
            "mqtt_client_disconnected",
            _device_id_from_client_id(client_id),
            "disconnect",
            {"client_id": client_id, "reason": "disconnect"},
        )

    closed = re.search(r"Client (?P<client_id>[^ ]+) closed its connection", message)
    if closed:
        client_id = closed.group("client_id")
        return (
            "mqtt_client_disconnected",
            _device_id_from_client_id(client_id),
            "disconnect_closed",
            {"client_id": client_id, "reason": "closed"},
        )

    replaced = re.search(r"Client (?P<client_id>[^ ]+) already connected, closing old connection", message)
    if replaced:
        client_id = replaced.group("client_id")
        return (
            "mqtt_client_disconnected",
            _device_id_from_client_id(client_id),
            "disconnect_replaced",
            {"client_id": client_id, "reason": "replaced"},
        )

    return "mqtt_broker_log", None, "log", {}


def _device_id_from_client_id(client_id: str | None):
    if client_id and client_id.startswith("INADS-"):
        return client_id
    return None


def _status_derived_fields(occurred_at: str, payload: dict):
    next_sleep_sec = payload.get("next_sleep_sec")
    if not isinstance(next_sleep_sec, int | float):
        return {}

    occurred_at_dt = datetime.fromisoformat(occurred_at)
    if occurred_at_dt.tzinfo is None:
        occurred_at_dt = occurred_at_dt.replace(tzinfo=UTC)

    return {
        "next_sleep_sec": next_sleep_sec,
        "next_wake_at": (occurred_at_dt + timedelta(seconds=next_sleep_sec)).isoformat(),
    }
