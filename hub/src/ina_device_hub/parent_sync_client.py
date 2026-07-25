import gzip
import io
import json
import os
import re
import ssl
import stat
import threading
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from ina_edge_runtime import SyncRequestBatch, build_sync_request
from ina_edge_runtime.protocol import canonical_json

from ina_device_hub.general_log import logger
from ina_device_hub.hierarchy_repository import UPSTREAM_PARENT_BINDING_KEY

_MAX_SYNC_BYTES = 1024 * 1024
_GZIP_THRESHOLD_BYTES = 1024
_NODE_BEARER_TOKEN = re.compile(r"^inas_sync_v1_[A-Za-z0-9_-]{43}$")
_INITIAL_RETRY_SECONDS = 2
_MAX_RETRY_SECONDS = 300


class ParentSyncTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParentSyncConfig:
    base_url: str
    bearer_token_file: Path | None
    ca_file: Path | None
    client_certificate_file: Path | None
    client_key_file: Path | None
    timeout_seconds: int = 20

    @classmethod
    def from_environment(cls):
        base_url = os.environ.get("HUB_SYNC_PARENT_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            return None
        parsed = urlsplit(base_url)
        allow_insecure_loopback = _boolean_environment("HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK", False)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("HUB_SYNC_PARENT_BASE_URL must be an HTTP(S) URL without query or fragment")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("HUB_SYNC_PARENT_BASE_URL must not embed credentials")
        if parsed.scheme != "https" and not (allow_insecure_loopback and parsed.hostname in {"127.0.0.1", "::1", "localhost"}):
            raise ValueError("HUB_SYNC_PARENT_BASE_URL must use HTTPS outside explicit loopback development")
        token_file = _optional_absolute_environment_path("HUB_SYNC_PARENT_TOKEN_FILE")
        ca_file = _optional_absolute_environment_path("HUB_SYNC_PARENT_CA_FILE")
        certificate_file = _optional_absolute_environment_path("HUB_SYNC_PARENT_CLIENT_CERT_FILE")
        key_file = _optional_absolute_environment_path("HUB_SYNC_PARENT_CLIENT_KEY_FILE")
        if (certificate_file is None) != (key_file is None):
            raise ValueError("HUB_SYNC_PARENT_CLIENT_CERT_FILE and HUB_SYNC_PARENT_CLIENT_KEY_FILE must be configured together")
        if token_file is None:
            raise ValueError("upstream Sync requires a node bearer token file")
        timeout_seconds = _integer_environment("HUB_SYNC_PARENT_TIMEOUT_SECONDS", 20, minimum=1, maximum=25)
        return cls(
            base_url=base_url,
            bearer_token_file=token_file,
            ca_file=ca_file,
            client_certificate_file=certificate_file,
            client_key_file=key_file,
            timeout_seconds=timeout_seconds,
        )

    def exchange_url(self, node_id: str) -> str:
        return f"{self.base_url}/sync/v1/nodes/{node_id}/exchange"


class ParentSyncTransport:
    def __init__(self, config: ParentSyncConfig):
        self.config = config
        context = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file is not None else None)
        if config.client_certificate_file is not None:
            _require_private_file(config.client_key_file, field_name="upstream client key")
            context.load_cert_chain(str(config.client_certificate_file), str(config.client_key_file))
        self._opener = build_opener(_NoRedirectHandler(), HTTPHandler(), HTTPSHandler(context=context))

    def exchange(self, node_id: str, document: dict) -> dict:
        body = canonical_json(document).encode("utf-8")
        if len(body) > _MAX_SYNC_BYTES:
            raise ParentSyncTransportError("upstream Sync request exceeds 1 MiB")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ina-local-hub/0.1",
        }
        if len(body) >= _GZIP_THRESHOLD_BYTES:
            body = gzip.compress(body, compresslevel=6)
            if len(body) > _MAX_SYNC_BYTES:
                raise ParentSyncTransportError("compressed upstream Sync request exceeds 1 MiB")
            headers["Content-Encoding"] = "gzip"
        if self.config.bearer_token_file is not None:
            headers["Authorization"] = f"Bearer {_read_secret(self.config.bearer_token_file)}"
        request = Request(
            self.config.exchange_url(node_id),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.config.timeout_seconds) as response:
                if response.status != HTTPStatus.OK:
                    raise ParentSyncTransportError(f"upstream parent returned HTTP {response.status}")
                media_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
                if media_type != "application/json":
                    raise ParentSyncTransportError("upstream response Content-Type must be application/json")
                raw = _read_bounded_response(response)
        except HTTPError as exc:
            raise ParentSyncTransportError(f"upstream parent returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise ParentSyncTransportError("upstream parent connection failed") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ParentSyncTransportError("upstream response is not valid JSON") from exc
        if not isinstance(value, dict):
            raise ParentSyncTransportError("upstream response must be a JSON object")
        return value


class ParentSyncClient:
    def __init__(self, *, service, transport):
        self.service = service
        self.transport = transport
        config = getattr(transport, "config", None)
        self.parent_binding = getattr(config, "base_url", None)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="local-hub-parent-sync", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=30)

    def exchange_once(self) -> int:
        upstream_active = self.service.repository.upstream_active()
        if upstream_active:
            self.service.forward_pending_child_records()
        batch = _build_bounded_request(self.service)
        if not upstream_active:
            batch = SyncRequestBatch(
                document={
                    **batch.document,
                    "events": [],
                    "command_results": [],
                },
                event_ids=(),
                command_result_ids=(),
            )
        response = self.transport.exchange(self.service.node_id, batch.document)
        next_poll_seconds = self.service.apply_parent_response(batch, response)
        if self.parent_binding is not None:
            self.service.repository.set_metadata(UPSTREAM_PARENT_BINDING_KEY, self.parent_binding)
        return next_poll_seconds

    def _run(self) -> None:
        retry_seconds = _INITIAL_RETRY_SECONDS
        while not self._stop_event.is_set():
            try:
                wait_seconds = self.exchange_once()
                retry_seconds = _INITIAL_RETRY_SECONDS
            except Exception:
                logger.exception("Local Hub upstream Sync exchange failed")
                wait_seconds = retry_seconds
                retry_seconds = min(retry_seconds * 2, _MAX_RETRY_SECONDS)
            self._stop_event.wait(wait_seconds)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        del request, file_pointer, code, message, headers, new_url


def parent_sync_client_from_environment(service) -> ParentSyncClient | None:
    config = ParentSyncConfig.from_environment()
    if config is None:
        return None
    return ParentSyncClient(service=service, transport=ParentSyncTransport(config))


def _build_bounded_request(service):
    event_limit = 500
    command_result_limit = 200
    while True:
        batch = build_sync_request(
            service.runtime.store,
            node_id=service.node_id,
            health=service.health_document(),
            event_limit=event_limit,
            command_result_limit=command_result_limit,
        )
        if len(canonical_json(batch.document).encode("utf-8")) <= _MAX_SYNC_BYTES:
            return batch
        if event_limit == 1 and command_result_limit == 1:
            raise ParentSyncTransportError("one pending upstream Sync item exceeds 1 MiB")
        event_limit = max(1, event_limit // 2)
        command_result_limit = max(1, command_result_limit // 2)


def _read_bounded_response(response) -> bytes:
    content_encoding = response.headers.get("Content-Encoding", "").lower()
    encoded = response.read(_MAX_SYNC_BYTES + 1)
    if len(encoded) > _MAX_SYNC_BYTES:
        raise ParentSyncTransportError("upstream response exceeds the 1 MiB encoded limit")
    if content_encoding == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
                raw = stream.read(_MAX_SYNC_BYTES + 1)
        except (EOFError, OSError) as exc:
            raise ParentSyncTransportError("upstream response contains invalid gzip data") from exc
    elif not content_encoding:
        raw = encoded
    else:
        raise ParentSyncTransportError("upstream response uses unsupported Content-Encoding")
    if len(raw) > _MAX_SYNC_BYTES:
        raise ParentSyncTransportError("upstream response exceeds 1 MiB")
    return raw


def _read_secret(path: Path) -> str:
    value = _read_private_text_file(path, field_name="upstream credential").strip()
    if _NODE_BEARER_TOKEN.fullmatch(value) is None:
        raise ValueError("upstream credential must contain one canonical inas_sync_v1_ node token")
    return value


def _require_private_file(path: Path | None, *, field_name: str) -> None:
    if path is None:
        raise ValueError(f"{field_name} file is not configured")
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{field_name} file must be a regular file and not a symbolic link: {path}")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o077:
        raise PermissionError(f"{field_name} file must not be readable by group or other users: {path}")


def _read_private_text_file(path: Path, *, field_name: str) -> str:
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
            value = stream.read(129)
            if stream.read(1):
                raise ValueError(f"{field_name} file is too large")
            return value
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _optional_absolute_environment_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path


def _integer_environment(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = os.environ.get(name, "").strip()
    parsed = int(value) if value else default
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _boolean_environment(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise ValueError(f"{name} must be a boolean")
    return value in {"1", "true", "yes", "on"}
