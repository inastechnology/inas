import shutil
import threading
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from ina_edge_runtime import (
    CommandExpiredError,
    normalize_sync_request,
    normalize_sync_response,
    validate_device_id,
)
from ina_edge_runtime.protocol import canonical_json, format_timestamp, utc_now

from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.device_event_log import register_device_event_sink, unregister_device_event_sink
from ina_device_hub.general_log import logger
from ina_device_hub.hierarchy_repository import UPSTREAM_PARENT_BINDING_KEY, HierarchyRepository
from ina_device_hub.local_edge_runtime import LocalEdgeRuntime, local_edge_runtime
from ina_device_hub.setting import setting

HIERARCHY_DATABASE_NAME = "hierarchy.db"
DEFAULT_SYNC_POLL_SECONDS = 15
SOFTWARE_VERSION = "0.1.0"


class HierarchyService:
    def __init__(
        self,
        *,
        repository: HierarchyRepository,
        runtime: LocalEdgeRuntime,
        device_service_provider=device_config_service,
    ):
        if repository.parent_node_id != runtime.node_id:
            raise ValueError("hierarchy repository and Local Edge Runtime identities must match")
        self.repository = repository
        self.runtime = runtime
        self.device_service_provider = device_service_provider
        self.mqtt_client = None
        self.parent_client = None
        self._started = False
        self._start_lock = threading.RLock()

    @property
    def node_id(self) -> str:
        return self.runtime.node_id

    def attach_mqtt_client(self, mqtt_client) -> None:
        self.mqtt_client = mqtt_client

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._recover_interrupted_local_commands()
            from ina_device_hub.parent_sync_client import parent_sync_client_from_environment

            self.parent_client = parent_sync_client_from_environment(self)
            if self.parent_client is None:
                self.repository.set_upstream_active(False)
            elif (
                self.parent_client.parent_binding is not None and self.repository.get_metadata(UPSTREAM_PARENT_BINDING_KEY) != self.parent_client.parent_binding
            ):
                self.repository.set_upstream_active(False)
                self.runtime.store.set_sync_cursor(None)
            register_device_event_sink(self.handle_local_device_event)
            self._started = True
            if self.parent_client is not None:
                self.parent_client.start()

    def stop(self) -> None:
        with self._start_lock:
            if not self._started:
                return
            self._started = False
            unregister_device_event_sink(self.handle_local_device_event)
            if self.parent_client is not None:
                self.parent_client.stop()

    def enroll_child(
        self,
        node_id: str,
        *,
        display_name: str | None = None,
        descendant_node_ids=(),
    ) -> dict[str, Any]:
        return self.repository.enroll_child(
            node_id,
            display_name=display_name,
            descendant_node_ids=descendant_node_ids,
        )

    def exchange_child(self, node_id: str, bearer_token: str, document: dict[str, Any]) -> dict[str, Any]:
        self.repository.authenticate_child(node_id, bearer_token)
        allowed_origins = self.repository.allowed_origins(node_id)
        normalized = normalize_sync_request(
            document,
            authenticated_node_id=node_id,
            allowed_origin_node_ids=allowed_origins,
        )
        ingested = self.repository.ingest_exchange(node_id, normalized)
        if self.repository.upstream_active():
            try:
                self.forward_pending_child_records()
            except Exception:
                logger.exception("Failed to stage child records for upstream Sync")
        response = {
            "protocol_version": "1.0",
            "correlation_request_id": normalized["request_id"],
            "server_time": format_timestamp(utc_now()),
            "next_cursor": ingested["next_cursor"],
            "ack_event_ids": ingested["ack_event_ids"],
            "ack_command_result_ids": ingested["ack_command_result_ids"],
            "desired_resources": self.repository.desired_for_child(node_id),
            "commands": self.repository.commands_for_child(node_id),
            "next_poll_seconds": DEFAULT_SYNC_POLL_SECONDS,
        }
        canonical_json(response)
        return response

    def apply_parent_response(self, batch, response: dict[str, Any], *, now: datetime | None = None) -> int:
        now = now or utc_now()
        normalized = normalize_sync_response(
            response,
            node_id=self.node_id,
            batch=batch,
            allowed_target_node_ids=self.repository.managed_node_ids(),
        )
        for resource in normalized["desired_resources"]:
            apply_status = self.repository.apply_upstream_desired(resource)
            if apply_status != "stale" and resource["target_node_id"] == self.node_id and resource["resource_type"] == "device.runtime_config":
                self.runtime.apply_parent_runtime_config(resource)
        for command in normalized["commands"]:
            if command["target_node_id"] == self.node_id:
                stored = self.runtime.store.receive_command(**command, now=now)
                if stored.status == "expired":
                    self.runtime.store.complete_command(
                        stored.command_id,
                        "expired",
                        origin_node_id=self.node_id,
                        error_code="expired_before_receipt",
                        message="Command expired before it reached the Local Hub control loop",
                        now=now,
                    )
            else:
                self.repository.queue_command(command)
        self._process_local_commands(now=now)
        self.runtime.store.ack_events(normalized["ack_event_ids"])
        self.runtime.store.ack_command_results(normalized["ack_command_result_ids"])
        self.runtime.store.set_sync_cursor(normalized["next_cursor"])
        self.repository.set_upstream_active(True)
        self.forward_pending_child_records()
        return normalized["next_poll_seconds"]

    def _process_local_commands(self, *, now: datetime | None = None) -> int:
        now = now or utc_now()
        processed = 0
        for command in self.runtime.store.pending_commands(now=now):
            if command.target_node_id != self.node_id:
                continue
            if not self._mqtt_ready():
                break
            self._execute_local_command(command, now=now)
            processed += 1
        self._complete_expired_local_commands(now=now)
        return processed

    def _execute_local_command(self, command, *, now: datetime) -> None:
        if command.command_type != "device.runtime_config_push":
            self.runtime.store.complete_command(
                command.command_id,
                "rejected",
                origin_node_id=self.node_id,
                error_code="unsupported_command",
                message=f"Unsupported Local Hub command type: {command.command_type}",
                now=now,
            )
            return
        try:
            if command.status == "pending":
                self.runtime.store.set_command_status(command.command_id, "accepted", now=now)
            self.runtime.store.set_command_status(command.command_id, "running", now=now)
        except CommandExpiredError:
            self.runtime.store.complete_command(
                command.command_id,
                "expired",
                origin_node_id=self.node_id,
                error_code="expired_before_activation",
                message="Command expired before local MQTT publication",
                now=now,
            )
            return
        try:
            if command.device_id is None:
                raise ValueError("device.runtime_config_push requires device_id")
            published = self.device_service_provider().publish_push(command.device_id)
            if int(published["mqtt_rc"]) != 0:
                raise RuntimeError(f"MQTT publish failed with rc={published['mqtt_rc']}")
        except Exception as exc:
            logger.exception("Local Hub parent command failed command_id=%s", command.command_id)
            self.runtime.store.complete_command(
                command.command_id,
                "failed",
                origin_node_id=self.node_id,
                error_code="execution_failed",
                message=str(exc)[:1000],
                now=now,
            )
            return
        self.runtime.store.complete_command(
            command.command_id,
            "succeeded",
            origin_node_id=self.node_id,
            payload={
                "topic": published["topic"],
                "mqtt_rc": int(published["mqtt_rc"]),
                "completed_at": format_timestamp(now),
            },
            now=now,
        )

    def _complete_expired_local_commands(self, *, now: datetime) -> None:
        self.runtime.store.pending_commands(now=now)
        for command in self.runtime.store.commands_with_status(["expired"]):
            if command.target_node_id != self.node_id:
                continue
            self.runtime.store.complete_command(
                command.command_id,
                "expired",
                origin_node_id=self.node_id,
                error_code="expired_before_activation",
                message="Command expired before local MQTT publication",
                now=now,
            )

    def _recover_interrupted_local_commands(self) -> None:
        for command in self.runtime.store.commands_with_status(["running"]):
            if command.target_node_id != self.node_id:
                continue
            self.runtime.store.complete_command(
                command.command_id,
                "failed",
                origin_node_id=self.node_id,
                error_code="execution_interrupted",
                message="Local Hub restarted after command activation; command was not replayed",
            )

    def _mqtt_ready(self) -> bool:
        if self.mqtt_client is None:
            return False
        readiness = getattr(self.mqtt_client, "is_connected", None)
        return bool(readiness()) if callable(readiness) else True

    def forward_pending_child_records(self) -> dict[str, int]:
        forwarded_event_ids = []
        for event in self.repository.unforwarded_events(limit=500):
            self.runtime.enqueue_forwarded_event(event)
            forwarded_event_ids.append(event["event_id"])
        forwarded_result_ids = []
        for result in self.repository.unforwarded_command_results(limit=200):
            self.runtime.enqueue_forwarded_command_result(result)
            forwarded_result_ids.append(result["result_id"])
        return {
            "events": self.repository.mark_events_forwarded(forwarded_event_ids),
            "command_results": self.repository.mark_command_results_forwarded(forwarded_result_ids),
        }

    def handle_local_device_event(self, event: dict[str, Any]) -> None:
        if not self.repository.upstream_active():
            return
        occurred_at = event.get("occurred_at") or format_timestamp(utc_now())
        event_type = str(event.get("event_type") or "device.event")
        source_device_id = event.get("device_id")
        device_id = None
        if source_device_id is not None:
            try:
                device_id = validate_device_id(source_device_id)
            except (TypeError, ValueError):
                device_id = None
        payload = {key: value for key, value in event.items() if key not in {"occurred_at", "event_type", "device_id"}}
        if source_device_id is not None and device_id is None:
            payload["source_device_id"] = str(source_device_id)[:200]
        self.runtime.enqueue_event(
            event_type=event_type,
            occurred_at=occurred_at,
            device_id=device_id,
            payload=payload,
        )

    def create_downstream_command(
        self,
        *,
        target_node_id: str,
        command_type: str,
        payload: dict[str, Any],
        expires_in_seconds: int,
        device_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(expires_in_seconds, int) or isinstance(expires_in_seconds, bool) or not 1 <= expires_in_seconds <= 86400:
            raise ValueError("expires_in_seconds must be between 1 and 86400")
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return self.repository.create_command(
            target_node_id=target_node_id,
            command_type=command_type,
            payload=payload,
            expires_at=format_timestamp(expires_at),
            device_id=device_id,
            idempotency_key=idempotency_key,
        )

    def health_document(self) -> dict[str, Any]:
        disk = shutil.disk_usage(Path(self.repository.path).parent)
        mqtt_connected = self._mqtt_ready()
        return {
            "status": "ok" if mqtt_connected else "degraded",
            "software_version": SOFTWARE_VERSION,
            "hardware_profile_id": "local-hub",
            "mqtt_connected": mqtt_connected,
            "storage_total_bytes": disk.total,
            "storage_free_bytes": disk.free,
            "capabilities": ["mqtt", "sync_child", "sync_parent"],
            "details": {
                "child_count": len(self.repository.list_children()),
                "upstream_active": self.repository.upstream_active(),
            },
        }


@lru_cache(maxsize=1)
def hierarchy_service() -> HierarchyService:
    runtime = local_edge_runtime()
    runtime_directory = Path(setting().get_work_dir()) / "edge-runtime"
    repository = HierarchyRepository(
        runtime_directory / HIERARCHY_DATABASE_NAME,
        parent_node_id=runtime.node_id,
    )
    return HierarchyService(repository=repository, runtime=runtime)
