import json
import logging
import threading
from datetime import UTC, datetime

from ina_edge_runtime.models import StoredCommand
from ina_edge_runtime.store import CommandExpiredError, EdgeStore

LOGGER = logging.getLogger(__name__)
MAX_RUNTIME_CONFIG_BYTES = 4095


class GatewayCommandExecutor:
    def __init__(self, *, store: EdgeStore, node_id: str, publisher):
        self.store = store
        self.node_id = node_id
        self.publisher = publisher
        self._lock = threading.RLock()

    def recover_interrupted_commands(self) -> None:
        with self._lock:
            for command in self.store.commands_with_status(["running"]):
                self.store.complete_command(
                    command.command_id,
                    "failed",
                    origin_node_id=self.node_id,
                    error_code="execution_interrupted",
                    message="Gateway restarted after command activation; command was not replayed",
                )
            self._complete_expired_commands()

    def process(self) -> int:
        with self._lock:
            self._complete_expired_commands()
            is_connected = getattr(self.publisher, "is_connected", None)
            if callable(is_connected) and not is_connected():
                return 0
            processed = 0
            for command in self.store.pending_commands():
                self._execute(command)
                processed += 1
            self._complete_expired_commands()
            return processed

    def record_received_terminal_commands(self, commands: tuple[StoredCommand, ...]) -> None:
        with self._lock:
            for command in commands:
                if command.status == "expired":
                    self.store.complete_command(
                        command.command_id,
                        "expired",
                        origin_node_id=self.node_id,
                        error_code="expired_before_receipt",
                        message="Command expired before it could be activated",
                    )

    def _execute(self, command: StoredCommand) -> None:
        if command.command_type != "device.runtime_config_push":
            self.store.complete_command(
                command.command_id,
                "rejected",
                origin_node_id=self.node_id,
                error_code="unsupported_command",
                message=f"Unsupported command type: {command.command_type}",
            )
            return
        try:
            if command.status == "pending":
                self.store.set_command_status(command.command_id, "accepted")
            self.store.set_command_status(command.command_id, "running")
        except CommandExpiredError:
            self.store.complete_command(
                command.command_id,
                "expired",
                origin_node_id=self.node_id,
                error_code="expired_before_activation",
                message="Command expired before MQTT publication",
            )
            return

        try:
            result_payload = self._publish_runtime_config(command)
        except Exception as exc:
            LOGGER.exception("Command execution failed command_id=%s", command.command_id)
            self.store.complete_command(
                command.command_id,
                "failed",
                origin_node_id=self.node_id,
                error_code="execution_failed",
                message=str(exc)[:1000],
            )
            return
        self.store.complete_command(
            command.command_id,
            "succeeded",
            origin_node_id=self.node_id,
            payload=result_payload,
        )

    def _publish_runtime_config(self, command: StoredCommand) -> dict:
        if command.device_id is None:
            raise ValueError("device.runtime_config_push requires device_id")
        resource = self.store.get_desired_resource("device.runtime_config", command.device_id)
        if resource is None or resource.operation != "upsert" or not isinstance(resource.payload, dict):
            raise ValueError("runtime config is not cached for the target device")
        encoded = json.dumps(resource.payload, ensure_ascii=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_RUNTIME_CONFIG_BYTES:
            raise ValueError("runtime config exceeds the device MQTT payload limit")
        topic = f"/{command.device_id}/kinds/config/push"
        publish_result = self.publisher.publish(topic, encoded, qos=0, retain=True)
        mqtt_rc = int(publish_result.rc)
        if mqtt_rc != 0:
            raise RuntimeError(f"MQTT publish failed with rc={mqtt_rc}")
        return {
            "topic": topic,
            "mqtt_rc": mqtt_rc,
            "revision": resource.revision,
            "completed_at": datetime.now(UTC).isoformat(),
        }

    def _complete_expired_commands(self) -> None:
        self.store.pending_commands()
        for command in self.store.commands_with_status(["expired"]):
            self.store.complete_command(
                command.command_id,
                "expired",
                origin_node_id=self.node_id,
                error_code="expired_before_activation",
                message="Command expired before MQTT publication",
            )
