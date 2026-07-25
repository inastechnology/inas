import gzip
import io
import json
import logging
import os
import re
import ssl
import stat
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from ina_edge_runtime.protocol import canonical_json
from ina_edge_runtime.store import EdgeStore
from ina_edge_runtime.sync import apply_sync_response, build_sync_request

from ina_edge_gateway.commands import GatewayCommandExecutor
from ina_edge_gateway.config import ParentConfig
from ina_edge_gateway.runtime_status import RuntimeStatus

LOGGER = logging.getLogger(__name__)
_GZIP_THRESHOLD_BYTES = 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_INITIAL_RETRY_SECONDS = 2
_MAX_RETRY_SECONDS = 300
_NODE_BEARER_TOKEN = re.compile(r"^(?:[A-Za-z0-9_-]{43}|inas_sync_v1_[A-Za-z0-9_-]{43})$")


class SyncTransportError(RuntimeError):
    pass


class ParentSyncTransport:
    def __init__(self, config: ParentConfig):
        self.config = config
        context = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file is not None else None)
        if config.client_certificate_file is not None:
            _require_private_file(config.client_key_file, field_name="parent client key")
            context.load_cert_chain(str(config.client_certificate_file), str(config.client_key_file))
        self._opener = build_opener(_NoRedirectHandler(), HTTPHandler(), HTTPSHandler(context=context))

    def exchange(self, node_id: str, document: dict) -> dict:
        body = canonical_json(document).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise SyncTransportError("sync request exceeds the 1 MiB decompressed limit")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ina-edge-gateway/0.1",
        }
        if len(body) >= _GZIP_THRESHOLD_BYTES:
            body = gzip.compress(body, compresslevel=6)
            if len(body) > _MAX_REQUEST_BYTES:
                raise SyncTransportError("compressed sync request exceeds the 1 MiB limit")
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
                    raise SyncTransportError(f"parent returned HTTP {response.status}")
                content_type = response.headers.get("Content-Type", "")
                if content_type.partition(";")[0].strip().lower() != "application/json":
                    raise SyncTransportError("parent response Content-Type must be application/json")
                raw = _read_bounded_response(response, self.config.max_response_bytes)
        except HTTPError as exc:
            raise SyncTransportError(f"parent returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise SyncTransportError("parent connection failed") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SyncTransportError("parent response is not valid JSON") from exc
        if not isinstance(value, dict):
            raise SyncTransportError("parent response must be a JSON object")
        return value


class GatewaySyncClient:
    def __init__(
        self,
        *,
        store: EdgeStore,
        node_id: str,
        transport: ParentSyncTransport,
        health_provider,
        command_executor: GatewayCommandExecutor,
        status: RuntimeStatus,
    ):
        self.store = store
        self.node_id = node_id
        self.transport = transport
        self.health_provider = health_provider
        self.command_executor = command_executor
        self.status = status

    def exchange_once(self) -> int:
        self.status.record_sync_attempt()
        batch = _build_bounded_sync_request(self.store, node_id=self.node_id, health=self.health_provider())
        response = self.transport.exchange(self.node_id, batch.document)
        applied = apply_sync_response(self.store, node_id=self.node_id, batch=batch, response=response)
        self.command_executor.record_received_terminal_commands(applied.commands)
        self.command_executor.process()
        self.status.record_sync_success(applied.next_poll_seconds)
        return applied.next_poll_seconds

    def run(self, stop_event: threading.Event) -> None:
        retry_seconds = _INITIAL_RETRY_SECONDS
        while not stop_event.is_set():
            try:
                wait_seconds = self.exchange_once()
                retry_seconds = _INITIAL_RETRY_SECONDS
            except Exception as exc:
                self.status.record_sync_failure(exc)
                LOGGER.exception("Parent Sync exchange failed")
                wait_seconds = retry_seconds
                retry_seconds = min(retry_seconds * 2, _MAX_RETRY_SECONDS)
            stop_event.wait(wait_seconds)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        del request, file_pointer, code, message, headers, new_url


def _read_bounded_response(response, maximum: int) -> bytes:
    content_encoding = response.headers.get("Content-Encoding", "").lower()
    encoded = response.read(maximum + 1)
    if len(encoded) > maximum:
        raise SyncTransportError("parent response exceeds configured encoded size limit")
    if content_encoding == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
                raw = stream.read(maximum + 1)
        except (EOFError, OSError) as exc:
            raise SyncTransportError("parent response contains invalid gzip data") from exc
    elif not content_encoding:
        raw = encoded
    else:
        raise SyncTransportError("parent response uses an unsupported Content-Encoding")
    if len(raw) > maximum:
        raise SyncTransportError("parent response exceeds configured size limit")
    return raw


def _read_secret(path: Path) -> str:
    value = _read_private_text_file(path, field_name="credential").strip()
    if _NODE_BEARER_TOKEN.fullmatch(value) is None:
        raise ValueError("credential file must contain one 43-character Cloud token or one inas_sync_v1_ Local Hub token")
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


def _build_bounded_sync_request(store: EdgeStore, *, node_id: str, health: dict):
    event_limit = 500
    command_result_limit = 200
    while True:
        batch = build_sync_request(
            store,
            node_id=node_id,
            health=health,
            event_limit=event_limit,
            command_result_limit=command_result_limit,
        )
        if len(canonical_json(batch.document).encode("utf-8")) <= _MAX_REQUEST_BYTES:
            return batch
        if event_limit == 1 and command_result_limit == 1:
            raise SyncTransportError("one pending Sync item exceeds the 1 MiB request limit")
        event_limit = max(1, event_limit // 2)
        command_result_limit = max(1, command_result_limit // 2)
