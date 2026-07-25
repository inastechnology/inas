import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_MAX_CONFIG_BYTES = 64 * 1024
_MAX_PARENT_RESPONSE_BYTES = 1024 * 1024
_MAX_CAPABILITIES = 50
_MAX_TEXT_LENGTH = 200
_CONFIG_FIELDS = {
    "schema_version",
    "data_directory",
    "identity_file",
    "hardware_profile_id",
    "software_version",
    "capabilities",
    "mqtt",
    "parent",
    "health",
}
_MQTT_FIELDS = {"host", "port", "username_file", "password_file", "keepalive_seconds"}
_PARENT_FIELDS = {
    "base_url",
    "bearer_token_file",
    "ca_file",
    "client_certificate_file",
    "client_key_file",
    "timeout_seconds",
    "max_response_bytes",
    "allow_insecure_http",
}
_HEALTH_FIELDS = {"bind_host", "port"}


@dataclass(frozen=True)
class MQTTConfig:
    host: str
    port: int
    username_file: Path | None
    password_file: Path | None
    keepalive_seconds: int


@dataclass(frozen=True)
class ParentConfig:
    base_url: str
    bearer_token_file: Path | None
    ca_file: Path | None
    client_certificate_file: Path | None
    client_key_file: Path | None
    timeout_seconds: int
    max_response_bytes: int

    def exchange_url(self, node_id: str) -> str:
        return f"{self.base_url.rstrip('/')}/sync/v1/nodes/{node_id}/exchange"


@dataclass(frozen=True)
class HealthConfig:
    bind_host: str
    port: int


@dataclass(frozen=True)
class GatewayConfig:
    data_directory: Path
    identity_file: Path
    hardware_profile_id: str
    software_version: str
    capabilities: tuple[str, ...]
    mqtt: MQTTConfig
    parent: ParentConfig | None
    health: HealthConfig

    @property
    def store_path(self) -> Path:
        return self.data_directory / "edge.db"


def load_gateway_config(path: str | os.PathLike[str]) -> GatewayConfig:
    config_path = Path(path)
    raw = config_path.read_bytes()
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ValueError("gateway config exceeds 64 KiB")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("gateway config must be valid JSON") from exc
    values = _exact_object(document, required=_CONFIG_FIELDS, allowed=_CONFIG_FIELDS, field_name="gateway config")
    if values["schema_version"] != 1:
        raise ValueError("gateway config schema_version must be 1")

    data_directory = _absolute_path(values["data_directory"], field_name="data_directory")
    identity_file = _absolute_path(values["identity_file"], field_name="identity_file")
    hardware_profile_id = _bounded_text(values["hardware_profile_id"], field_name="hardware_profile_id")
    software_version = _bounded_text(values["software_version"], field_name="software_version")
    capabilities = _capabilities(values["capabilities"])
    mqtt = _mqtt_config(values["mqtt"])
    parent = _parent_config(values["parent"])
    health = _health_config(values["health"])
    return GatewayConfig(
        data_directory=data_directory,
        identity_file=identity_file,
        hardware_profile_id=hardware_profile_id,
        software_version=software_version,
        capabilities=capabilities,
        mqtt=mqtt,
        parent=parent,
        health=health,
    )


def _mqtt_config(value: Any) -> MQTTConfig:
    values = _exact_object(value, required=_MQTT_FIELDS, allowed=_MQTT_FIELDS, field_name="mqtt")
    host = _bounded_text(values["host"], field_name="mqtt.host")
    port = _bounded_integer(values["port"], field_name="mqtt.port", minimum=1, maximum=65535)
    keepalive = _bounded_integer(values["keepalive_seconds"], field_name="mqtt.keepalive_seconds", minimum=10, maximum=3600)
    username_file = _optional_absolute_path(values["username_file"], field_name="mqtt.username_file")
    password_file = _optional_absolute_path(values["password_file"], field_name="mqtt.password_file")
    if (username_file is None) != (password_file is None):
        raise ValueError("mqtt.username_file and mqtt.password_file must be configured together")
    return MQTTConfig(
        host=host,
        port=port,
        username_file=username_file,
        password_file=password_file,
        keepalive_seconds=keepalive,
    )


def _parent_config(value: Any) -> ParentConfig | None:
    if value is None:
        return None
    values = _exact_object(value, required=_PARENT_FIELDS, allowed=_PARENT_FIELDS, field_name="parent")
    base_url = _bounded_text(values["base_url"], field_name="parent.base_url").rstrip("/")
    parsed = urlsplit(base_url)
    allow_insecure_http = values["allow_insecure_http"]
    if not isinstance(allow_insecure_http, bool):
        raise ValueError("parent.allow_insecure_http must be a boolean")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("parent.base_url must be an HTTP(S) URL without query or fragment")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("parent.base_url must not embed credentials")
    if parsed.scheme != "https" and not (allow_insecure_http and parsed.hostname in {"127.0.0.1", "::1", "localhost"}):
        raise ValueError("parent.base_url must use HTTPS outside an explicit loopback development configuration")

    token_file = _optional_absolute_path(values["bearer_token_file"], field_name="parent.bearer_token_file")
    ca_file = _optional_absolute_path(values["ca_file"], field_name="parent.ca_file")
    certificate_file = _optional_absolute_path(values["client_certificate_file"], field_name="parent.client_certificate_file")
    key_file = _optional_absolute_path(values["client_key_file"], field_name="parent.client_key_file")
    if (certificate_file is None) != (key_file is None):
        raise ValueError("parent client certificate and key files must be configured together")
    if token_file is None:
        raise ValueError("parent authentication requires a node bearer token file")
    timeout_seconds = _bounded_integer(values["timeout_seconds"], field_name="parent.timeout_seconds", minimum=1, maximum=25)
    max_response_bytes = _bounded_integer(
        values["max_response_bytes"],
        field_name="parent.max_response_bytes",
        minimum=1024,
        maximum=_MAX_PARENT_RESPONSE_BYTES,
    )
    return ParentConfig(
        base_url=base_url,
        bearer_token_file=token_file,
        ca_file=ca_file,
        client_certificate_file=certificate_file,
        client_key_file=key_file,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )


def _health_config(value: Any) -> HealthConfig:
    values = _exact_object(value, required=_HEALTH_FIELDS, allowed=_HEALTH_FIELDS, field_name="health")
    return HealthConfig(
        bind_host=_bounded_text(values["bind_host"], field_name="health.bind_host"),
        port=_bounded_integer(values["port"], field_name="health.port", minimum=0, maximum=65535),
    )


def _capabilities(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > _MAX_CAPABILITIES:
        raise ValueError("capabilities must be a non-empty array with at most 50 items")
    result = []
    for item in value:
        text = _bounded_text(item, field_name="capability")
        if not text[0].islower() or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for character in text):
            raise ValueError("capabilities must use lowercase identifier characters")
        result.append(text)
    if len(set(result)) != len(result):
        raise ValueError("capabilities must not contain duplicates")
    return tuple(result)


def _absolute_path(value: Any, *, field_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be an absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return path


def _optional_absolute_path(value: Any, *, field_name: str) -> Path | None:
    return None if value is None else _absolute_path(value, field_name=field_name)


def _bounded_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_LENGTH:
        raise ValueError(f"{field_name} must be a non-empty string up to 200 characters")
    return value


def _bounded_integer(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{field_name} must be an integer between {minimum} and {maximum}")
    return value


def _exact_object(value: Any, *, required: set[str], allowed: set[str], field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    fields = set(value)
    missing = required - fields
    if missing:
        raise ValueError(f"{field_name} is missing fields: {', '.join(sorted(missing))}")
    unknown = fields - allowed
    if unknown:
        raise ValueError(f"{field_name} contains unsupported fields: {', '.join(sorted(unknown))}")
    return dict(value)
