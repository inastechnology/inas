import json
import os
import threading
import uuid
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from ina_edge_runtime import EdgeStore, NodeType, generate_node_id, parse_node_id, validate_device_id
from ina_edge_runtime.models import DesiredResource, StoredCommandResult, StoredEvent
from ina_edge_runtime.protocol import canonical_json, content_hash, format_timestamp, utc_now

from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock
from ina_device_hub.setting import setting

IDENTITY_SCHEMA_VERSION = 1
RUNTIME_DIRECTORY_NAME = "edge-runtime"
IDENTITY_FILE_NAME = "identity.json"
STORE_FILE_NAME = "edge.db"
PARENT_RUNTIME_AUTHORITY_PREFIX = "parent_authority:device.runtime_config:"


class LocalEdgeRuntime:
    """Local Hub adapter for the reusable device-facing Edge Runtime."""

    def __init__(self, store: EdgeStore, node_id: str):
        identity = parse_node_id(node_id)
        if identity.node_type != NodeType.LOCAL_HUB:
            raise ValueError("Local Hub Edge Runtime requires an INALH node ID")
        self.store = store
        self.node_id = identity.value
        self._config_lock = threading.RLock()

    @classmethod
    def open(cls, work_dir: str | os.PathLike[str]):
        runtime_dir = Path(work_dir) / RUNTIME_DIRECTORY_NAME
        runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        node_id = _load_or_create_local_node_id(runtime_dir / IDENTITY_FILE_NAME)
        store_path = runtime_dir / STORE_FILE_NAME
        store = EdgeStore(store_path)
        os.chmod(store_path, 0o600)
        return cls(store, node_id)

    def close(self) -> None:
        self.store.close()

    def cache_runtime_config(
        self,
        device_id: str,
        payload: dict[str, Any],
        *,
        updated_at: str | None = None,
    ) -> DesiredResource:
        validate_device_id(device_id)
        if not isinstance(payload, dict):
            raise ValueError("runtime config payload must be an object")

        payload_sha256 = content_hash(payload)
        payload_json = canonical_json(payload)
        timestamp = updated_at or format_timestamp(utc_now())

        with self._config_lock:
            current = self.store.get_desired_resource("device.runtime_config", device_id)
            if self.is_parent_runtime_config_authoritative(device_id):
                if current is not None and current.operation == "upsert" and isinstance(current.payload, dict):
                    return current
                raise RuntimeError(f"runtime config for {device_id} is controlled by the parent Hub")
            if current is not None:
                if current.target_node_id != self.node_id:
                    raise RuntimeError(f"runtime config for {device_id} belongs to another node")
                if current.operation == "upsert" and current.content_sha256 == payload_sha256 and canonical_json(current.payload) == payload_json:
                    return current
                revision = current.revision + 1
            else:
                revision = 1

            result = self.store.apply_desired_resource(
                resource_type="device.runtime_config",
                resource_id=device_id,
                target_node_id=self.node_id,
                revision=revision,
                operation="upsert",
                content_sha256=payload_sha256,
                updated_at=timestamp,
                payload=payload,
            )
            return result.resource

    def apply_parent_runtime_config(self, resource: dict[str, Any]) -> DesiredResource:
        if not isinstance(resource, dict) or resource.get("resource_type") != "device.runtime_config":
            raise ValueError("parent runtime resource must be device.runtime_config")
        device_id = resource.get("resource_id")
        validate_device_id(device_id)
        if resource.get("target_node_id") != self.node_id:
            raise ValueError("parent runtime resource must target this Local Hub")
        operation = resource.get("operation")
        payload = resource.get("payload")
        if operation == "upsert" and not isinstance(payload, dict):
            raise ValueError("parent runtime config payload must be an object")
        if operation == "delete" and payload is not None:
            raise ValueError("deleted parent runtime config payload must be null")
        if operation not in {"upsert", "delete"}:
            raise ValueError("parent runtime config operation must be upsert or delete")
        parent_revision = resource.get("revision")
        if not isinstance(parent_revision, int) or isinstance(parent_revision, bool) or parent_revision < 1:
            raise ValueError("parent runtime config revision must be a positive integer")

        with self._config_lock:
            authority_key = f"{PARENT_RUNTIME_AUTHORITY_PREFIX}{device_id}"
            authority_text = self.store.get_metadata(authority_key)
            if authority_text is not None:
                try:
                    authority = json.loads(authority_text)
                    current_parent_revision = authority["revision"]
                    current_parent_hash = authority["content_sha256"]
                    current_parent_operation = authority["operation"]
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"parent runtime authority metadata is invalid for {device_id}") from exc
                if not isinstance(current_parent_revision, int) or isinstance(current_parent_revision, bool) or current_parent_revision < 1:
                    raise RuntimeError(f"parent runtime authority revision is invalid for {device_id}")
                if parent_revision < current_parent_revision:
                    raise ValueError("parent runtime config revision is stale")
                if parent_revision == current_parent_revision and (
                    current_parent_hash != resource.get("content_sha256") or current_parent_operation != operation
                ):
                    raise ValueError("parent runtime config revision has conflicting content")

            current = self.store.get_desired_resource("device.runtime_config", device_id)
            if (
                current is not None
                and current.target_node_id == self.node_id
                and current.operation == operation
                and current.content_sha256 == resource.get("content_sha256")
                and canonical_json(current.payload) == canonical_json(payload)
            ):
                applied = current
            else:
                result = self.store.apply_desired_resource(
                    resource_type="device.runtime_config",
                    resource_id=device_id,
                    target_node_id=self.node_id,
                    revision=(current.revision + 1) if current is not None else 1,
                    operation=operation,
                    content_sha256=resource["content_sha256"],
                    updated_at=resource["updated_at"],
                    payload=payload,
                )
                applied = result.resource
            self.store.set_metadata(
                authority_key,
                canonical_json(
                    {
                        "revision": parent_revision,
                        "content_sha256": resource["content_sha256"],
                        "operation": operation,
                    }
                ),
            )
            return applied

    def is_parent_runtime_config_authoritative(self, device_id: str) -> bool:
        validate_device_id(device_id)
        return self.store.get_metadata(f"{PARENT_RUNTIME_AUTHORITY_PREFIX}{device_id}") is not None

    def get_runtime_config(self, device_id: str) -> dict[str, Any] | None:
        validate_device_id(device_id)
        resource = self.store.get_desired_resource("device.runtime_config", device_id)
        if resource is None or resource.operation != "upsert":
            return None
        if resource.target_node_id != self.node_id:
            raise RuntimeError(f"runtime config for {device_id} belongs to another node")
        if not isinstance(resource.payload, dict):
            raise RuntimeError(f"runtime config for {device_id} is not an object")
        return resource.payload

    def enqueue_event(
        self,
        *,
        event_type: str,
        occurred_at: str,
        payload: Any,
        device_id: str | None = None,
        event_id: str | None = None,
    ) -> StoredEvent:
        return self.store.enqueue_event(
            event_id=event_id or str(uuid.uuid4()),
            origin_node_id=self.node_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=payload,
            device_id=device_id,
        )

    def pending_events(self, *, limit: int = 500) -> list[StoredEvent]:
        return self.store.pending_events(limit=limit)

    def ack_events(self, event_ids: Iterable[str]) -> int:
        return self.store.ack_events(event_ids)

    def enqueue_forwarded_event(self, event: dict[str, Any]) -> StoredEvent:
        if not isinstance(event, dict):
            raise ValueError("forwarded event must be an object")
        return self.store.enqueue_event(
            event_id=event["event_id"],
            origin_node_id=event["origin_node_id"],
            sequence=event["sequence"],
            schema_version=event["schema_version"],
            event_type=event["event_type"],
            occurred_at=event["occurred_at"],
            device_id=event.get("device_id"),
            payload=event["payload"],
        )

    def enqueue_forwarded_command_result(self, result: dict[str, Any]) -> StoredCommandResult:
        if not isinstance(result, dict):
            raise ValueError("forwarded command result must be an object")
        return self.store.record_command_result(
            result_id=result["result_id"],
            command_id=result["command_id"],
            origin_node_id=result["origin_node_id"],
            status=result["status"],
            occurred_at=result["occurred_at"],
            error_code=result.get("error_code"),
            message=result.get("message"),
            payload=result.get("payload"),
        )


def _load_or_create_local_node_id(path: Path) -> str:
    with repository_file_lock(str(path)):
        if path.exists():
            try:
                with path.open(encoding="utf-8") as file:
                    document = json.load(file)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Local Hub identity file is unreadable: {path}") from exc
            if not isinstance(document, dict) or document.get("schema_version") != IDENTITY_SCHEMA_VERSION:
                raise RuntimeError(f"Local Hub identity file has an unsupported schema: {path}")
            node_id = document.get("node_id")
            try:
                identity = parse_node_id(node_id)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Local Hub identity file contains an invalid node ID: {path}") from exc
            if identity.node_type != NodeType.LOCAL_HUB:
                raise RuntimeError(f"Local Hub identity file contains a non-Local-Hub node ID: {path}")
            return identity.value

        node_id = generate_node_id(NodeType.LOCAL_HUB)
        atomic_write_json(
            str(path),
            {
                "schema_version": IDENTITY_SCHEMA_VERSION,
                "node_id": node_id,
                "node_type": NodeType.LOCAL_HUB.value,
            },
        )
        os.chmod(path, 0o600)
        return node_id


@lru_cache(maxsize=1)
def local_edge_runtime():
    return LocalEdgeRuntime.open(setting().get_work_dir())
