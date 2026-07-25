from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StoredEvent:
    local_order: int
    event_id: str
    origin_node_id: str
    sequence: int
    schema_version: int
    event_type: str
    occurred_at: str
    device_id: str | None
    payload: Any

    def to_sync_dict(self) -> dict[str, Any]:
        value = {
            "event_id": self.event_id,
            "origin_node_id": self.origin_node_id,
            "sequence": self.sequence,
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
        if self.device_id is not None:
            value["device_id"] = self.device_id
        return value


@dataclass(frozen=True)
class DesiredResource:
    resource_type: str
    resource_id: str
    target_node_id: str
    revision: int
    operation: str
    content_sha256: str
    updated_at: str
    payload: Any

    def to_sync_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "target_node_id": self.target_node_id,
            "revision": self.revision,
            "operation": self.operation,
            "content_sha256": self.content_sha256,
            "updated_at": self.updated_at,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class ApplyDesiredResult:
    status: str
    resource: DesiredResource


@dataclass(frozen=True)
class StoredCommand:
    command_id: str
    idempotency_key: str
    command_type: str
    target_node_id: str
    device_id: str | None
    issued_at: str
    expires_at: str
    payload: dict[str, Any]
    status: str
    error: str | None

    def to_sync_dict(self) -> dict[str, Any]:
        value = {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "command_type": self.command_type,
            "target_node_id": self.target_node_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "payload": self.payload,
        }
        if self.device_id is not None:
            value["device_id"] = self.device_id
        return value


@dataclass(frozen=True)
class StoredCommandResult:
    local_order: int
    result_id: str
    command_id: str
    origin_node_id: str
    status: str
    occurred_at: str
    error_code: str | None
    message: str | None
    payload: Any

    def to_sync_dict(self) -> dict[str, Any]:
        value = {
            "result_id": self.result_id,
            "command_id": self.command_id,
            "origin_node_id": self.origin_node_id,
            "status": self.status,
            "occurred_at": self.occurred_at,
        }
        if self.error_code is not None:
            value["error_code"] = self.error_code
        if self.message is not None:
            value["message"] = self.message
        if self.payload is not None:
            value["payload"] = self.payload
        return value
