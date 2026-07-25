import gzip
import io
import json
import os
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ina_edge_runtime.protocol import canonical_json
from ina_edge_runtime.store import EdgeStore

from ina_edge_gateway.config import GatewayConfig, HealthConfig, MQTTConfig, ParentConfig
from ina_edge_gateway.health import GatewayHealth, MaintenanceHTTPServer
from ina_edge_gateway.runtime_status import RuntimeStatus
from ina_edge_gateway.sync_client import (
    GatewaySyncClient,
    ParentSyncTransport,
    SyncTransportError,
    _read_bounded_response,
)

EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


class _MQTT:
    def __init__(self, connected=False):
        self.connected = connected

    def is_connected(self):
        return self.connected


class _CommandExecutor:
    def __init__(self):
        self.received = []
        self.process_count = 0

    def record_received_terminal_commands(self, commands):
        self.received.extend(commands)

    def process(self):
        self.process_count += 1
        return 0


class _Transport:
    def __init__(self):
        self.fail = False
        self.documents = []

    def exchange(self, _node_id, document):
        self.documents.append(document)
        if self.fail:
            raise SyncTransportError("offline")
        return {
            "protocol_version": "1.0",
            "correlation_request_id": document["request_id"],
            "server_time": "2026-07-23T02:15:01Z",
            "next_cursor": "cursor-1",
            "ack_event_ids": [event["event_id"] for event in document["events"]],
            "ack_command_result_ids": [],
            "desired_resources": [],
            "commands": [],
            "next_poll_seconds": 15,
        }


class SyncAndHealthTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.store = EdgeStore(self.root / "edge.db")
        self.status = RuntimeStatus(node_id=EDGE_ID, parent_configured=True)
        self.mqtt = _MQTT()
        self.config = GatewayConfig(
            data_directory=self.root,
            identity_file=self.root / "identity.json",
            hardware_profile_id="egw-rpi5-development-r0",
            software_version="0.1.0",
            capabilities=("mqtt", "wifi_ap", "ntp"),
            mqtt=MQTTConfig(host="127.0.0.1", port=1883, username_file=None, password_file=None, keepalive_seconds=60),
            parent=None,
            health=HealthConfig(bind_host="127.0.0.1", port=0),
        )

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_sync_failure_keeps_event_and_success_acknowledges_it(self):
        event_id = str(uuid.uuid4())
        self.store.enqueue_event(
            event_id=event_id,
            origin_node_id=EDGE_ID,
            event_type="device.status",
            occurred_at="2026-07-23T02:14:58Z",
            device_id=DEVICE_ID,
            payload={"seq": 1},
        )
        transport = _Transport()
        executor = _CommandExecutor()
        health = GatewayHealth(config=self.config, store=self.store, status=self.status, mqtt_client=self.mqtt)
        client = GatewaySyncClient(
            store=self.store,
            node_id=EDGE_ID,
            transport=transport,
            health_provider=health.sync_document,
            command_executor=executor,
            status=self.status,
        )
        transport.fail = True
        with self.assertRaises(SyncTransportError):
            client.exchange_once()
        self.assertEqual([event.event_id for event in self.store.pending_events()], [event_id])

        transport.fail = False
        self.assertEqual(client.exchange_once(), 15)
        self.assertEqual(self.store.pending_events(), [])
        self.assertEqual(self.store.get_sync_cursor(), "cursor-1")
        self.assertEqual(executor.process_count, 1)

    def test_maintenance_endpoint_is_read_only_sanitized_and_wan_independent(self):
        health = GatewayHealth(config=self.config, store=self.store, status=self.status, mqtt_client=self.mqtt)
        server = MaintenanceHTTPServer(host="127.0.0.1", port=0, health=health)
        server.start()
        host, port = server.address
        try:
            with self.assertRaises(HTTPError) as not_ready:
                urlopen(f"http://{host}:{port}/readyz", timeout=2)
            self.assertEqual(not_ready.exception.code, 503)

            self.mqtt.connected = True
            with urlopen(f"http://{host}:{port}/readyz", timeout=2) as response:
                self.assertEqual(response.status, 200)
            with urlopen(f"http://{host}:{port}/maintenance/v1/status", timeout=2) as response:
                document = json.load(response)
            self.assertEqual(document["node_id"], EDGE_ID)
            self.assertTrue(document["mqtt_connected"])
            serialized = json.dumps(document)
            self.assertNotIn("token", serialized.lower())
            self.assertNotIn("credential", serialized.lower())

            request = Request(f"http://{host}:{port}/maintenance/v1/status", data=b"{}", method="POST")
            with self.assertRaises(HTTPError) as read_only:
                urlopen(request, timeout=2)
            self.assertEqual(read_only.exception.code, 405)
        finally:
            server.stop()

    def test_parent_transport_rejects_oversized_response(self):
        class OversizedHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = b'{"padding":"' + (b"x" * 2048) + b'"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format_string, *args):
                del format_string, args

        server = HTTPServer(("127.0.0.1", 0), OversizedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            transport = ParentSyncTransport(
                ParentConfig(
                    base_url=f"http://{host}:{port}",
                    bearer_token_file=None,
                    ca_file=None,
                    client_certificate_file=None,
                    client_key_file=None,
                    timeout_seconds=2,
                    max_response_bytes=1024,
                )
            )
            with self.assertRaisesRegex(SyncTransportError, "size limit"):
                transport.exchange(EDGE_ID, {"small": True})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_parent_transport_bounds_compressed_and_decompressed_response(self):
        maximum = 1024
        decoded = os.urandom(maximum)
        encoded = gzip.compress(decoded)
        self.assertGreater(len(encoded), maximum)
        response = io.BytesIO(encoded)
        response.headers = {"Content-Encoding": "gzip"}

        with self.assertRaisesRegex(SyncTransportError, "encoded size limit"):
            _read_bounded_response(response, maximum)

    def test_parent_transport_rejects_group_readable_mtls_key(self):
        certificate = self.root / "client.crt"
        private_key = self.root / "client.key"
        certificate.write_text("not needed for the permission check", encoding="utf-8")
        private_key.write_text("private", encoding="utf-8")
        os.chmod(private_key, 0o640)

        with self.assertRaisesRegex(PermissionError, "parent client key"):
            ParentSyncTransport(
                ParentConfig(
                    base_url="https://parent.example",
                    bearer_token_file=None,
                    ca_file=None,
                    client_certificate_file=certificate,
                    client_key_file=private_key,
                    timeout_seconds=2,
                    max_response_bytes=1024,
                )
            )

    def test_sync_batch_is_reduced_to_parent_decompressed_limit(self):
        for _ in range(5):
            self.store.enqueue_event(
                event_id=str(uuid.uuid4()),
                origin_node_id=EDGE_ID,
                event_type="device.telemetry",
                occurred_at="2026-07-23T02:14:58Z",
                device_id=DEVICE_ID,
                payload={"blob": "x" * 250_000},
            )
        transport = _Transport()
        executor = _CommandExecutor()
        health = GatewayHealth(config=self.config, store=self.store, status=self.status, mqtt_client=self.mqtt)
        client = GatewaySyncClient(
            store=self.store,
            node_id=EDGE_ID,
            transport=transport,
            health_provider=health.sync_document,
            command_executor=executor,
            status=self.status,
        )

        client.exchange_once()

        sent = transport.documents[0]
        self.assertLessEqual(len(canonical_json(sent).encode("utf-8")), 1024 * 1024)
        self.assertGreater(len(self.store.pending_events()), 0)


if __name__ == "__main__":
    unittest.main()
