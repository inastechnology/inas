import json
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ina_edge_runtime.store import EdgeStore

from ina_edge_gateway.config import GatewayConfig
from ina_edge_gateway.runtime_status import RuntimeStatus

_CRITICAL_FREE_BYTES = 64 * 1024 * 1024


class GatewayHealth:
    def __init__(self, *, config: GatewayConfig, store: EdgeStore, status: RuntimeStatus, mqtt_client):
        self.config = config
        self.store = store
        self.status = status
        self.mqtt_client = mqtt_client

    def sync_document(self) -> dict[str, Any]:
        disk = shutil.disk_usage(self.config.data_directory)
        mqtt_connected = self.mqtt_client.is_connected()
        health_status = "critical" if disk.free < _CRITICAL_FREE_BYTES else ("ok" if mqtt_connected else "degraded")
        runtime = self.status.snapshot()
        return {
            "status": health_status,
            "software_version": self.config.software_version,
            "hardware_profile_id": self.config.hardware_profile_id,
            "mqtt_connected": mqtt_connected,
            "storage_total_bytes": disk.total,
            "storage_free_bytes": disk.free,
            "capabilities": list(self.config.capabilities),
            "details": {
                "parent_configured": runtime["parent_configured"],
                "last_sync_success_at": runtime["last_sync_success_at"],
                "last_sync_error": runtime["last_sync_error"],
            },
        }

    def maintenance_document(self) -> dict[str, Any]:
        sync_health = self.sync_document()
        return {
            "node_id": self.status.snapshot()["node_id"],
            "status": sync_health["status"],
            "software_version": sync_health["software_version"],
            "hardware_profile_id": sync_health["hardware_profile_id"],
            "mqtt_connected": sync_health["mqtt_connected"],
            "storage_total_bytes": sync_health["storage_total_bytes"],
            "storage_free_bytes": sync_health["storage_free_bytes"],
            "outbox_depth": self.store.sync_outbox_depth(),
            "runtime": self.status.snapshot(),
        }

    def ready(self) -> bool:
        return self.mqtt_client.is_connected()


class MaintenanceHTTPServer:
    def __init__(self, *, host: str, port: int, health: GatewayHealth):
        self.health = health
        handler = _handler_for(health)
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="edge-maintenance-http", daemon=True)

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _handler_for(health: GatewayHealth):
    class Handler(BaseHTTPRequestHandler):
        server_version = "INAS"
        sys_version = ""

        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if self.path == "/readyz":
                ready = health.ready()
                self._send_json(HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE, {"status": "ready" if ready else "not_ready"})
                return
            if self.path == "/maintenance/v1/status":
                self._send_json(HTTPStatus.OK, health.maintenance_document())
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self):  # noqa: N802
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read_only_endpoint"})

        def log_message(self, format_string, *args):
            del format_string, args

        def _send_json(self, status: HTTPStatus, document: dict[str, Any]) -> None:
            body = json.dumps(document, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler
