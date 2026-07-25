import logging
import os
import stat
import threading
from pathlib import Path

from paho.mqtt import client as mqtt_client

from ina_edge_gateway.config import MQTTConfig
from ina_edge_gateway.runtime_status import RuntimeStatus

LOGGER = logging.getLogger(__name__)
_MAX_CREDENTIAL_LENGTH = 4096
DEFAULT_SUBSCRIPTIONS = (
    "farm/+/telemetry",
    "sensor/+/#",
    "/+/kinds/config/request",
    "/+/kinds/agri/immediate",
    "/+/kinds/debug/log",
    "/+/kinds/ota/request",
    "/+/kinds/ota/status",
    "$SYS/broker/log/#",
)


class GatewayMQTTClient:
    def __init__(self, *, config: MQTTConfig, node_id: str, status: RuntimeStatus):
        self.config = config
        self.node_id = node_id
        self.status = status
        self._connected = threading.Event()
        self._message_handler = None
        self._client = self._build_client()

    def set_message_handler(self, handler) -> None:
        self._message_handler = handler

    def start(self) -> None:
        self._client.connect_async(self.config.host, self.config.port, keepalive=self.config.keepalive_seconds)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()
        self.status.set_mqtt_connected(False)

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def publish(self, topic: str, payload: str, *, qos: int, retain: bool):
        return self._client.publish(topic, payload, qos=qos, retain=retain)

    def _build_client(self):
        client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2,
            client_id=self.node_id,
            protocol=mqtt_client.MQTTv311,
            transport="tcp",
        )
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        if self.config.username_file is not None:
            username = _read_credential_file(self.config.username_file, field_name="MQTT username")
            password = _read_credential_file(self.config.password_file, field_name="MQTT password")
            client.username_pw_set(username, password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code.is_failure:
            self._connected.clear()
            self.status.set_mqtt_connected(False)
            LOGGER.warning("Local MQTT connection failed: %s", reason_code)
            return
        self._connected.set()
        self.status.set_mqtt_connected(True)
        for topic in DEFAULT_SUBSCRIPTIONS:
            client.subscribe(topic, qos=0)
        LOGGER.info("Connected to local MQTT broker at %s:%s", self.config.host, self.config.port)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties) -> None:
        self._connected.clear()
        self.status.set_mqtt_connected(False)
        if reason_code.is_failure:
            LOGGER.warning("Local MQTT connection lost: %s", reason_code)

    def _on_message(self, _client, _userdata, message) -> None:
        if self._message_handler is None:
            LOGGER.error("MQTT message received before a controller was attached")
            return
        try:
            self._message_handler(message.topic, message.payload)
        except Exception:
            LOGGER.exception("MQTT controller failed for topic=%s", message.topic)


def _read_credential_file(path: Path | None, *, field_name: str) -> str:
    if path is None:
        raise ValueError(f"{field_name} file is not configured")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{field_name} file must be a regular file and not a symbolic link: {path}")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PermissionError(f"{field_name} file must not be readable by group or other users: {path}")
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            value = stream.read(_MAX_CREDENTIAL_LENGTH + 2).strip()
            if stream.read(1):
                raise ValueError(f"{field_name} file is too large")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not value or len(value) > _MAX_CREDENTIAL_LENGTH or "\x00" in value:
        raise ValueError(f"{field_name} must contain 1 to 4096 characters")
    return value
