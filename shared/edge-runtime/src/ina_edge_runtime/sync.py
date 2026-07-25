import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ina_edge_runtime.identity import parse_node_id, validate_device_id, validate_uuid_v4
from ina_edge_runtime.models import ApplyDesiredResult, StoredCommand
from ina_edge_runtime.protocol import (
    PROTOCOL_VERSION,
    RESULT_STATUSES,
    canonical_json,
    format_timestamp,
    normalize_timestamp,
    parse_timestamp,
    utc_now,
    validate_event_type,
    validate_sha256,
)
from ina_edge_runtime.store import EdgeStore

_HEALTH_STATUSES = {"ok", "degraded", "critical"}
_HEALTH_REQUIRED_FIELDS = {"status", "software_version", "mqtt_connected", "storage_free_bytes", "capabilities"}
_HEALTH_OPTIONAL_FIELDS = {"hardware_profile_id", "storage_total_bytes", "details"}
_HARDWARE_PROFILE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_HEALTH_STRING_LENGTH = 100
_MAX_CAPABILITIES = 50
_MAX_HEALTH_DETAILS = 50
_MAX_CURSOR_LENGTH = 1000
_MAX_NEXT_POLL_SECONDS = 3600
_MAX_EVENTS = 500
_MAX_COMMAND_RESULTS = 200
_MAX_DESIRED_RESOURCES = 500
_MAX_RESOURCE_ID_LENGTH = 200
_MAX_COMMANDS = 100
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_ERROR_CODE_LENGTH = 100
_MAX_MESSAGE_LENGTH = 1000
_REQUEST_FIELDS = {
    "protocol_version",
    "request_id",
    "node_id",
    "node_type",
    "sent_at",
    "cursor",
    "events",
    "command_results",
    "health",
}
_RESPONSE_FIELDS = {
    "protocol_version",
    "correlation_request_id",
    "server_time",
    "next_cursor",
    "ack_event_ids",
    "ack_command_result_ids",
    "desired_resources",
    "commands",
    "next_poll_seconds",
}
_DESIRED_FIELDS = {
    "resource_type",
    "resource_id",
    "target_node_id",
    "revision",
    "operation",
    "content_sha256",
    "updated_at",
    "payload",
}
_COMMAND_REQUIRED_FIELDS = {
    "command_id",
    "idempotency_key",
    "command_type",
    "target_node_id",
    "issued_at",
    "expires_at",
    "payload",
}
_COMMAND_FIELDS = _COMMAND_REQUIRED_FIELDS | {"device_id"}
_EVENT_REQUIRED_FIELDS = {
    "event_id",
    "origin_node_id",
    "sequence",
    "schema_version",
    "event_type",
    "occurred_at",
    "payload",
}
_EVENT_FIELDS = _EVENT_REQUIRED_FIELDS | {"device_id"}
_COMMAND_RESULT_REQUIRED_FIELDS = {
    "result_id",
    "command_id",
    "origin_node_id",
    "status",
    "occurred_at",
}
_COMMAND_RESULT_FIELDS = _COMMAND_RESULT_REQUIRED_FIELDS | {"error_code", "message", "payload"}
_DESIRED_RESOURCE_TYPES = {"device.runtime_config", "device.assignment", "device.firmware_target", "node.policy"}


@dataclass(frozen=True)
class SyncRequestBatch:
    document: dict[str, Any]
    event_ids: tuple[str, ...]
    command_result_ids: tuple[str, ...]


@dataclass(frozen=True)
class SyncApplyResult:
    acknowledged_event_count: int
    acknowledged_command_result_count: int
    desired_results: tuple[ApplyDesiredResult, ...]
    commands: tuple[StoredCommand, ...]
    next_cursor: str | None
    next_poll_seconds: int


def build_sync_request(
    store: EdgeStore,
    *,
    node_id: str,
    health: Mapping[str, Any],
    request_id: str | None = None,
    sent_at: datetime | None = None,
    event_limit: int = 500,
    command_result_limit: int = 200,
) -> SyncRequestBatch:
    identity = parse_node_id(node_id)
    request_id = request_id or str(uuid.uuid4())
    validate_uuid_v4(request_id, field_name="request_id")
    sent_at = sent_at or utc_now()
    sent_at_text = format_timestamp(sent_at)

    events = store.pending_events(limit=event_limit)
    command_results = store.pending_command_results(limit=command_result_limit)
    normalized_health = _normalize_health(health)
    normalized_health["outbox_depth"] = store.sync_outbox_depth()

    document = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "node_id": identity.value,
        "node_type": identity.node_type.value,
        "sent_at": sent_at_text,
        "cursor": store.get_sync_cursor(),
        "events": [event.to_sync_dict() for event in events],
        "command_results": [result.to_sync_dict() for result in command_results],
        "health": normalized_health,
    }
    canonical_json(document)
    return SyncRequestBatch(
        document=document,
        event_ids=tuple(event.event_id for event in events),
        command_result_ids=tuple(result.result_id for result in command_results),
    )


def apply_sync_response(
    store: EdgeStore,
    *,
    node_id: str,
    batch: SyncRequestBatch,
    response: Mapping[str, Any],
    now: datetime | None = None,
) -> SyncApplyResult:
    identity = parse_node_id(node_id)
    if batch.document.get("node_id") != identity.value:
        raise ValueError("sync batch node_id does not match the receiving node")
    normalized = normalize_sync_response(response, node_id=identity.value, batch=batch)
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")

    desired_results = tuple(store.apply_desired_resource(**resource) for resource in normalized["desired_resources"])
    commands = tuple(store.receive_command(**command, now=now) for command in normalized["commands"])
    acknowledged_event_count = store.ack_events(normalized["ack_event_ids"])
    acknowledged_command_result_count = store.ack_command_results(normalized["ack_command_result_ids"])
    store.set_sync_cursor(normalized["next_cursor"])
    return SyncApplyResult(
        acknowledged_event_count=acknowledged_event_count,
        acknowledged_command_result_count=acknowledged_command_result_count,
        desired_results=desired_results,
        commands=commands,
        next_cursor=normalized["next_cursor"],
        next_poll_seconds=normalized["next_poll_seconds"],
    )


def normalize_sync_request(
    request: Mapping[str, Any],
    *,
    authenticated_node_id: str,
    allowed_origin_node_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    identity = parse_node_id(authenticated_node_id)
    allowed_origins = _normalized_node_set(
        allowed_origin_node_ids,
        required_node_id=identity.value,
        field_name="allowed_origin_node_ids",
    )
    document = _exact_mapping(request, required=_REQUEST_FIELDS, allowed=_REQUEST_FIELDS, field_name="sync request")
    if document["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError(f"sync request protocol_version must be {PROTOCOL_VERSION}")
    request_id = validate_uuid_v4(document["request_id"], field_name="request_id")
    if document["node_id"] != identity.value:
        raise ValueError("sync request node_id does not match the authenticated node")
    if document["node_type"] != identity.node_type.value:
        raise ValueError("sync request node_type does not match the authenticated node")
    sent_at = normalize_timestamp(document["sent_at"], field_name="sent_at")
    cursor = _normalize_cursor(document["cursor"], field_name="cursor")
    events = _normalize_events(document["events"], allowed_origins=allowed_origins)
    command_results = _normalize_command_results(document["command_results"], allowed_origins=allowed_origins)
    health = _normalize_request_health(document["health"])
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "node_id": identity.value,
        "node_type": identity.node_type.value,
        "sent_at": sent_at,
        "cursor": cursor,
        "events": events,
        "command_results": command_results,
        "health": health,
    }


def normalize_sync_response(
    response: Mapping[str, Any],
    *,
    node_id: str,
    batch: SyncRequestBatch,
    allowed_target_node_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    identity = parse_node_id(node_id)
    if batch.document.get("node_id") != identity.value:
        raise ValueError("sync batch node_id does not match the receiving node")
    allowed_targets = _normalized_node_set(
        allowed_target_node_ids,
        required_node_id=identity.value,
        field_name="allowed_target_node_ids",
    )
    document = _exact_mapping(response, required=_RESPONSE_FIELDS, allowed=_RESPONSE_FIELDS, field_name="sync response")
    if document["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError(f"sync response protocol_version must be {PROTOCOL_VERSION}")
    correlation_request_id = validate_uuid_v4(document["correlation_request_id"], field_name="correlation_request_id")
    if correlation_request_id != batch.document.get("request_id"):
        raise ValueError("sync response correlation_request_id does not match the request")
    normalize_timestamp(document["server_time"], field_name="server_time")

    next_cursor = _normalize_cursor(document["next_cursor"], field_name="next_cursor")
    ack_event_ids = _acknowledgements(
        document["ack_event_ids"],
        allowed=batch.event_ids,
        field_name="ack_event_ids",
        maximum=_MAX_EVENTS,
    )
    ack_command_result_ids = _acknowledgements(
        document["ack_command_result_ids"],
        allowed=batch.command_result_ids,
        field_name="ack_command_result_ids",
        maximum=_MAX_COMMAND_RESULTS,
    )
    desired_resources = _normalize_desired_resources(document["desired_resources"], allowed_targets=allowed_targets)
    commands = _normalize_commands(document["commands"], allowed_targets=allowed_targets)
    next_poll_seconds = document["next_poll_seconds"]
    if not isinstance(next_poll_seconds, int) or isinstance(next_poll_seconds, bool) or not 1 <= next_poll_seconds <= _MAX_NEXT_POLL_SECONDS:
        raise ValueError("next_poll_seconds must be an integer between 1 and 3600")
    return {
        "next_cursor": next_cursor,
        "ack_event_ids": ack_event_ids,
        "ack_command_result_ids": ack_command_result_ids,
        "desired_resources": desired_resources,
        "commands": commands,
        "next_poll_seconds": next_poll_seconds,
    }


def _normalize_events(value: Any, *, allowed_origins: frozenset[str]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) > _MAX_EVENTS:
        raise ValueError("events must be an array with at most 500 items")
    normalized = []
    event_ids = set()
    origin_sequences = set()
    for index, item in enumerate(value):
        field_name = f"events[{index}]"
        event = _exact_mapping(item, required=_EVENT_REQUIRED_FIELDS, allowed=_EVENT_FIELDS, field_name=field_name)
        event_id = validate_uuid_v4(event["event_id"], field_name=f"{field_name}.event_id")
        origin_node_id = parse_node_id(event["origin_node_id"]).value
        if origin_node_id not in allowed_origins:
            raise ValueError(f"{field_name}.origin_node_id is outside the authenticated node subtree")
        sequence = event["sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError(f"{field_name}.sequence must be a positive integer")
        schema_version = event["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
            raise ValueError(f"{field_name}.schema_version must be a positive integer")
        device_id = event.get("device_id")
        if device_id is not None:
            validate_device_id(device_id)
        payload = event["payload"]
        canonical_json(payload)
        origin_sequence = (origin_node_id, sequence)
        if event_id in event_ids or origin_sequence in origin_sequences:
            raise ValueError("events must not contain duplicate event IDs or origin sequences")
        event_ids.add(event_id)
        origin_sequences.add(origin_sequence)
        normalized_event = {
            "event_id": event_id,
            "origin_node_id": origin_node_id,
            "sequence": sequence,
            "schema_version": schema_version,
            "event_type": validate_event_type(event["event_type"]),
            "occurred_at": normalize_timestamp(event["occurred_at"], field_name=f"{field_name}.occurred_at"),
            "payload": payload,
        }
        if device_id is not None:
            normalized_event["device_id"] = device_id
        normalized.append(normalized_event)
    return tuple(normalized)


def _normalize_command_results(value: Any, *, allowed_origins: frozenset[str]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) > _MAX_COMMAND_RESULTS:
        raise ValueError("command_results must be an array with at most 200 items")
    normalized = []
    result_ids = set()
    for index, item in enumerate(value):
        field_name = f"command_results[{index}]"
        result = _exact_mapping(
            item,
            required=_COMMAND_RESULT_REQUIRED_FIELDS,
            allowed=_COMMAND_RESULT_FIELDS,
            field_name=field_name,
        )
        result_id = validate_uuid_v4(result["result_id"], field_name=f"{field_name}.result_id")
        if result_id in result_ids:
            raise ValueError("command_results must not contain duplicate result IDs")
        result_ids.add(result_id)
        origin_node_id = parse_node_id(result["origin_node_id"]).value
        if origin_node_id not in allowed_origins:
            raise ValueError(f"{field_name}.origin_node_id is outside the authenticated node subtree")
        status = result["status"]
        if status not in RESULT_STATUSES:
            raise ValueError(f"{field_name}.status is unsupported")
        error_code = result.get("error_code")
        if error_code is not None and (not isinstance(error_code, str) or not error_code or len(error_code) > _MAX_ERROR_CODE_LENGTH):
            raise ValueError(f"{field_name}.error_code must be a non-empty string up to 100 characters")
        message = result.get("message")
        if message is not None and (not isinstance(message, str) or len(message) > _MAX_MESSAGE_LENGTH):
            raise ValueError(f"{field_name}.message must be a string up to 1000 characters")
        payload = result.get("payload")
        if "payload" in result:
            canonical_json(payload)
        normalized_result = {
            "result_id": result_id,
            "command_id": validate_uuid_v4(result["command_id"], field_name=f"{field_name}.command_id"),
            "origin_node_id": origin_node_id,
            "status": status,
            "occurred_at": normalize_timestamp(result["occurred_at"], field_name=f"{field_name}.occurred_at"),
        }
        for optional_field, optional_value in (("error_code", error_code), ("message", message)):
            if optional_value is not None:
                normalized_result[optional_field] = optional_value
        if "payload" in result:
            normalized_result["payload"] = payload
        normalized.append(normalized_result)
    return tuple(normalized)


def _acknowledgements(value: Any, *, allowed: tuple[str, ...], field_name: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{field_name} must be an array with at most {maximum} items")
    normalized = tuple(validate_uuid_v4(item, field_name=field_name) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    unexpected = set(normalized) - set(allowed)
    if unexpected:
        raise ValueError(f"{field_name} contains IDs that were not sent in this request")
    return normalized


def _normalize_desired_resources(value: Any, *, allowed_targets: frozenset[str]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) > _MAX_DESIRED_RESOURCES:
        raise ValueError("desired_resources must be an array with at most 500 items")
    normalized = []
    keys = set()
    for index, item in enumerate(value):
        field_name = f"desired_resources[{index}]"
        resource = _exact_mapping(item, required=_DESIRED_FIELDS, allowed=_DESIRED_FIELDS, field_name=field_name)
        resource_type = resource["resource_type"]
        if resource_type not in _DESIRED_RESOURCE_TYPES:
            raise ValueError(f"{field_name}.resource_type is unsupported")
        resource_id = resource["resource_id"]
        if not isinstance(resource_id, str) or not resource_id or len(resource_id) > _MAX_RESOURCE_ID_LENGTH:
            raise ValueError(f"{field_name}.resource_id must be a non-empty string up to 200 characters")
        target_node_id = parse_node_id(resource["target_node_id"]).value
        if target_node_id not in allowed_targets:
            raise ValueError(f"{field_name}.target_node_id is outside this node subtree")
        if resource_type.startswith("device."):
            validate_device_id(resource_id)
        elif parse_node_id(resource_id).value != target_node_id:
            raise ValueError(f"{field_name}.resource_id must equal target_node_id for node.policy")
        revision = resource["revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValueError(f"{field_name}.revision must be a positive integer")
        operation = resource["operation"]
        if operation not in {"upsert", "delete"}:
            raise ValueError(f"{field_name}.operation must be upsert or delete")
        payload = resource["payload"]
        if operation == "upsert" and not isinstance(payload, dict):
            raise ValueError(f"{field_name}.payload must be an object for upsert")
        if operation == "delete" and payload is not None:
            raise ValueError(f"{field_name}.payload must be null for delete")
        canonical_json(payload)
        key = (resource_type, resource_id)
        if key in keys:
            raise ValueError("desired_resources must not contain duplicate resource identities")
        keys.add(key)
        normalized.append(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "target_node_id": target_node_id,
                "revision": revision,
                "operation": operation,
                "content_sha256": validate_sha256(resource["content_sha256"]),
                "updated_at": normalize_timestamp(resource["updated_at"], field_name=f"{field_name}.updated_at"),
                "payload": payload,
            }
        )
    return tuple(normalized)


def _normalize_commands(value: Any, *, allowed_targets: frozenset[str]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or len(value) > _MAX_COMMANDS:
        raise ValueError("commands must be an array with at most 100 items")
    normalized = []
    command_ids = set()
    idempotency_keys = set()
    for index, item in enumerate(value):
        field_name = f"commands[{index}]"
        command = _exact_mapping(item, required=_COMMAND_REQUIRED_FIELDS, allowed=_COMMAND_FIELDS, field_name=field_name)
        command_id = validate_uuid_v4(command["command_id"], field_name=f"{field_name}.command_id")
        idempotency_key = command["idempotency_key"]
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError(f"{field_name}.idempotency_key must be a non-empty string up to 200 characters")
        command_type = validate_event_type(command["command_type"], field_name=f"{field_name}.command_type")
        target_node_id = parse_node_id(command["target_node_id"]).value
        if target_node_id not in allowed_targets:
            raise ValueError(f"{field_name}.target_node_id is outside this node subtree")
        device_id = command.get("device_id")
        if device_id is not None:
            validate_device_id(device_id)
        issued_at = parse_timestamp(command["issued_at"], field_name=f"{field_name}.issued_at")
        expires_at = parse_timestamp(command["expires_at"], field_name=f"{field_name}.expires_at")
        if expires_at <= issued_at:
            raise ValueError(f"{field_name}.expires_at must be later than issued_at")
        payload = command["payload"]
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name}.payload must be an object")
        canonical_json(payload)
        if command_id in command_ids or idempotency_key in idempotency_keys:
            raise ValueError("commands must not contain duplicate command IDs or idempotency keys")
        command_ids.add(command_id)
        idempotency_keys.add(idempotency_key)
        normalized.append(
            {
                "command_id": command_id,
                "idempotency_key": idempotency_key,
                "command_type": command_type,
                "target_node_id": target_node_id,
                "device_id": device_id,
                "issued_at": format_timestamp(issued_at),
                "expires_at": format_timestamp(expires_at),
                "payload": payload,
            }
        )
    return tuple(normalized)


def _exact_mapping(value: Any, *, required: set[str], allowed: set[str], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    fields = set(value)
    missing = required - fields
    if missing:
        raise ValueError(f"{field_name} is missing required fields: {', '.join(sorted(missing))}")
    unknown = fields - allowed
    if unknown:
        raise ValueError(f"{field_name} contains unsupported fields: {', '.join(sorted(unknown))}")
    return dict(value)


def _normalize_health(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("health must be an object")
    fields = set(value)
    missing = _HEALTH_REQUIRED_FIELDS - fields
    if missing:
        raise ValueError(f"health is missing required fields: {', '.join(sorted(missing))}")
    unknown = fields - _HEALTH_REQUIRED_FIELDS - _HEALTH_OPTIONAL_FIELDS
    if unknown:
        raise ValueError(f"health contains unsupported fields: {', '.join(sorted(unknown))}")

    status = value["status"]
    if status not in _HEALTH_STATUSES:
        raise ValueError("health.status must be ok, degraded, or critical")
    software_version = _bounded_string(value["software_version"], field_name="health.software_version")
    mqtt_connected = value["mqtt_connected"]
    if not isinstance(mqtt_connected, bool):
        raise ValueError("health.mqtt_connected must be a boolean")
    storage_free_bytes = _nonnegative_integer(value["storage_free_bytes"], field_name="health.storage_free_bytes")

    result = {
        "status": status,
        "software_version": software_version,
        "mqtt_connected": mqtt_connected,
        "storage_free_bytes": storage_free_bytes,
        "capabilities": _normalize_capabilities(value["capabilities"]),
    }
    _add_optional_health_fields(result, value, storage_free_bytes=storage_free_bytes)
    return result


def _normalize_request_health(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or "outbox_depth" not in value:
        raise ValueError("health must include outbox_depth")
    without_outbox = dict(value)
    outbox_depth = _nonnegative_integer(without_outbox.pop("outbox_depth"), field_name="health.outbox_depth")
    result = _normalize_health(without_outbox)
    result["outbox_depth"] = outbox_depth
    return result


def _normalize_cursor(value: Any, *, field_name: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value or len(value) > _MAX_CURSOR_LENGTH):
        raise ValueError(f"{field_name} must be null or a non-empty string up to 1000 characters")
    return value


def _normalized_node_set(
    values: Iterable[str] | None,
    *,
    required_node_id: str,
    field_name: str,
) -> frozenset[str]:
    if values is None:
        return frozenset({required_node_id})
    normalized = frozenset(parse_node_id(value).value for value in values)
    if required_node_id not in normalized:
        raise ValueError(f"{field_name} must include the receiving node")
    return normalized


def _normalize_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > _MAX_CAPABILITIES:
        raise ValueError("health.capabilities must be an array with at most 50 items")
    capabilities = [validate_event_type(item, field_name="health capability") for item in value]
    if len(set(capabilities)) != len(capabilities):
        raise ValueError("health.capabilities must not contain duplicates")
    return capabilities


def _add_optional_health_fields(result: dict[str, Any], value: Mapping[str, Any], *, storage_free_bytes: int) -> None:
    hardware_profile_id = value.get("hardware_profile_id")
    if hardware_profile_id is not None:
        hardware_profile_id = _bounded_string(hardware_profile_id, field_name="health.hardware_profile_id")
        if _HARDWARE_PROFILE_RE.fullmatch(hardware_profile_id) is None:
            raise ValueError("health.hardware_profile_id has an invalid format")
        result["hardware_profile_id"] = hardware_profile_id
    storage_total_bytes = value.get("storage_total_bytes")
    if storage_total_bytes is not None:
        storage_total_bytes = _nonnegative_integer(storage_total_bytes, field_name="health.storage_total_bytes")
        if storage_free_bytes > storage_total_bytes:
            raise ValueError("health.storage_free_bytes must not exceed storage_total_bytes")
        result["storage_total_bytes"] = storage_total_bytes
    details = value.get("details")
    if details is not None:
        if not isinstance(details, dict) or len(details) > _MAX_HEALTH_DETAILS:
            raise ValueError("health.details must be an object with at most 50 properties")
        canonical_json(details)
        result["details"] = dict(details)


def _bounded_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_HEALTH_STRING_LENGTH:
        raise ValueError(f"{field_name} must be a non-empty string up to 100 characters")
    return value


def _nonnegative_integer(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value
