import gzip
import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ina_edge_runtime.protocol import content_hash

from ina_device_hub.hierarchy_repository import HierarchyRepository
from ina_device_hub.hierarchy_service import HierarchyService
from ina_device_hub.local_edge_runtime import LocalEdgeRuntime
from ina_device_hub.parent_sync_client import (
    ParentSyncClient,
    ParentSyncConfig,
    ParentSyncTransport,
    ParentSyncTransportError,
    _read_bounded_response,
    _read_secret,
)

GRANDCHILD_EDGE_ID = "INAEG-323e4567-e89b-42d3-a456-426614174001"
UNREGISTERED_EDGE_ID = "INAEG-423e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


def new_id() -> str:
    return str(uuid.uuid4())


class _MQTT:
    def is_connected(self):
        return True


class _ServiceTransport:
    def __init__(self, *, parent_service, bearer_token):
        self.parent_service = parent_service
        self.bearer_token = bearer_token
        self.documents = []

    def exchange(self, node_id, document):
        self.documents.append(document)
        return self.parent_service.exchange_child(node_id, self.bearer_token, document)


class _ResponseTransport:
    def __init__(self, response_factory, *, base_url=None):
        self.response_factory = response_factory
        self.config = SimpleNamespace(base_url=base_url) if base_url is not None else None
        self.documents = []

    def exchange(self, node_id, document):
        del node_id
        self.documents.append(document)
        return self.response_factory(document)


class ParentSyncClientTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.parent_runtime = LocalEdgeRuntime.open(root / "parent")
        self.child_runtime = LocalEdgeRuntime.open(root / "child")
        self.parent_repository = HierarchyRepository(
            root / "parent" / "edge-runtime" / "hierarchy.db",
            parent_node_id=self.parent_runtime.node_id,
        )
        self.child_repository = HierarchyRepository(
            root / "child" / "edge-runtime" / "hierarchy.db",
            parent_node_id=self.child_runtime.node_id,
        )
        self.parent_service = HierarchyService(
            repository=self.parent_repository,
            runtime=self.parent_runtime,
        )
        self.child_service = HierarchyService(
            repository=self.child_repository,
            runtime=self.child_runtime,
        )
        self.parent_service.attach_mqtt_client(_MQTT())
        self.child_service.attach_mqtt_client(_MQTT())

    def tearDown(self):
        self.parent_repository.close()
        self.child_repository.close()
        self.parent_runtime.close()
        self.child_runtime.close()
        self.temporary_directory.cleanup()

    def test_two_local_hubs_forward_original_child_event_and_route_downstream_state(self):
        grandchild = self.child_service.enroll_child(GRANDCHILD_EDGE_ID)
        parent_enrollment = self.parent_service.enroll_child(
            self.child_runtime.node_id,
            descendant_node_ids=[GRANDCHILD_EDGE_ID],
        )
        resource = self.parent_repository.set_downstream_desired(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=GRANDCHILD_EDGE_ID,
            operation="upsert",
            payload={"moisture_threshold": 43},
        )
        command = self.parent_service.create_downstream_command(
            target_node_id=GRANDCHILD_EDGE_ID,
            command_type="device.runtime_config_push",
            device_id=DEVICE_ID,
            payload={},
            expires_in_seconds=300,
        )
        event = self._grandchild_event()
        self.child_service.exchange_child(
            GRANDCHILD_EDGE_ID,
            grandchild["bearer_token"],
            self._grandchild_request(events=[event]),
        )
        transport = _ServiceTransport(
            parent_service=self.parent_service,
            bearer_token=parent_enrollment["bearer_token"],
        )
        client = ParentSyncClient(service=self.child_service, transport=transport)

        client.exchange_once()
        self.assertTrue(self.child_repository.upstream_active())
        self.assertEqual(transport.documents[0]["events"], [])
        self.assertEqual(self.child_runtime.pending_events()[0].event_id, event["event_id"])

        client.exchange_once()

        self.assertEqual(transport.documents[1]["events"][0]["event_id"], event["event_id"])
        self.assertEqual(transport.documents[1]["events"][0]["origin_node_id"], GRANDCHILD_EDGE_ID)
        self.assertEqual(transport.documents[1]["events"][0]["sequence"], 17)
        self.assertEqual(self.child_runtime.pending_events(), [])
        parent_event = self.parent_repository.list_events()[0]
        self.assertEqual(parent_event["event_id"], event["event_id"])
        self.assertEqual(parent_event["origin_node_id"], GRANDCHILD_EDGE_ID)

        downstream = self.child_service.exchange_child(
            GRANDCHILD_EDGE_ID,
            grandchild["bearer_token"],
            self._grandchild_request(),
        )
        self.assertEqual(downstream["desired_resources"], [resource])
        self.assertEqual(downstream["commands"][0]["command_id"], command["command_id"])
        self.assertEqual(downstream["commands"][0]["target_node_id"], GRANDCHILD_EDGE_ID)

    def test_invalid_parent_target_does_not_ack_or_advance_cursor(self):
        event = self.child_runtime.enqueue_event(
            event_type="device.status",
            occurred_at="2026-07-23T02:14:50Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        self.child_runtime.store.set_sync_cursor("cursor-before")

        def response(document):
            payload = {"mode": "managed"}
            return {
                "protocol_version": "1.0",
                "correlation_request_id": document["request_id"],
                "server_time": "2026-07-23T02:15:00Z",
                "next_cursor": "cursor-after",
                "ack_event_ids": [],
                "ack_command_result_ids": [],
                "desired_resources": [
                    {
                        "resource_type": "node.policy",
                        "resource_id": UNREGISTERED_EDGE_ID,
                        "target_node_id": UNREGISTERED_EDGE_ID,
                        "revision": 1,
                        "operation": "upsert",
                        "content_sha256": content_hash(payload),
                        "updated_at": "2026-07-23T02:14:00Z",
                        "payload": payload,
                    }
                ],
                "commands": [],
                "next_poll_seconds": 15,
            }

        client = ParentSyncClient(
            service=self.child_service,
            transport=_ResponseTransport(response),
        )

        with self.assertRaisesRegex(ValueError, "outside this node subtree"):
            client.exchange_once()

        self.assertEqual([item.event_id for item in self.child_runtime.pending_events()], [event.event_id])
        self.assertEqual(self.child_runtime.store.get_sync_cursor(), "cursor-before")
        self.assertFalse(self.child_repository.upstream_active())

    def test_first_parent_exchange_is_empty_and_binds_parent_before_backlog_upload(self):
        event = self.child_runtime.enqueue_event(
            event_type="device.status",
            occurred_at="2026-07-23T02:14:50Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )

        def response(document):
            return {
                "protocol_version": "1.0",
                "correlation_request_id": document["request_id"],
                "server_time": "2026-07-23T02:15:00Z",
                "next_cursor": "cursor-after",
                "ack_event_ids": [item["event_id"] for item in document["events"]],
                "ack_command_result_ids": [],
                "desired_resources": [],
                "commands": [],
                "next_poll_seconds": 15,
            }

        transport = _ResponseTransport(
            response,
            base_url="https://parent.example.test",
        )
        client = ParentSyncClient(service=self.child_service, transport=transport)

        client.exchange_once()

        self.assertEqual(transport.documents[0]["events"], [])
        self.assertEqual(transport.documents[0]["command_results"], [])
        self.assertTrue(self.child_repository.upstream_active())
        self.assertEqual(
            self.child_repository.get_metadata("upstream_parent_base_url"),
            "https://parent.example.test",
        )
        self.assertEqual([item.event_id for item in self.child_runtime.pending_events()], [event.event_id])

        client.exchange_once()

        self.assertEqual([item["event_id"] for item in transport.documents[1]["events"]], [event.event_id])
        self.assertEqual(self.child_runtime.pending_events(), [])

    def _grandchild_request(self, *, events=None):
        return {
            "protocol_version": "1.0",
            "request_id": new_id(),
            "node_id": GRANDCHILD_EDGE_ID,
            "node_type": "edge_gateway",
            "sent_at": "2026-07-23T02:15:00Z",
            "cursor": None,
            "events": events or [],
            "command_results": [],
            "health": {
                "status": "ok",
                "software_version": "0.1.0",
                "outbox_depth": len(events or []),
                "mqtt_connected": True,
                "storage_free_bytes": 1000,
                "capabilities": ["mqtt"],
            },
        }

    def _grandchild_event(self):
        payload = {"soil_moisture": 41}
        return {
            "event_id": new_id(),
            "origin_node_id": GRANDCHILD_EDGE_ID,
            "sequence": 17,
            "schema_version": 1,
            "event_type": "device.telemetry",
            "occurred_at": "2026-07-23T02:14:58Z",
            "device_id": DEVICE_ID,
            "payload": payload,
        }


class ParentSyncConfigTest(unittest.TestCase):
    def test_parent_url_requires_https_except_explicit_loopback_development(self):
        with patch.dict(
            os.environ,
            {"HUB_SYNC_PARENT_BASE_URL": "http://parent.example.test"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                ParentSyncConfig.from_environment()

        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "parent.token"
            token_file.write_text(f"inas_sync_v1_{'A' * 43}", encoding="utf-8")
            token_file.chmod(0o600)
            with patch.dict(
                os.environ,
                {
                    "HUB_SYNC_PARENT_BASE_URL": "http://127.0.0.1:39151/",
                    "HUB_SYNC_PARENT_TOKEN_FILE": str(token_file),
                    "HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK": "true",
                },
                clear=True,
            ):
                config = ParentSyncConfig.from_environment()

        self.assertIsNotNone(config)
        self.assertEqual(config.base_url, "http://127.0.0.1:39151")

    def test_parent_url_rejects_embedded_credentials_and_requires_node_bearer(self):
        with patch.dict(
            os.environ,
            {
                "HUB_SYNC_PARENT_BASE_URL": "http://node:secret@localhost:39151",
                "HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK": "true",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must not embed credentials"):
                ParentSyncConfig.from_environment()

        with patch.dict(
            os.environ,
            {"HUB_SYNC_PARENT_BASE_URL": "https://parent.example.test"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "node bearer token file"):
                ParentSyncConfig.from_environment()

    def test_transport_rejects_group_readable_bearer_file_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "parent.token"
            token_file.write_text(f"inas_sync_v1_{'A' * 43}", encoding="utf-8")
            token_file.chmod(0o640)
            config = ParentSyncConfig(
                base_url="http://127.0.0.1:39151",
                bearer_token_file=token_file,
                ca_file=None,
                client_certificate_file=None,
                client_key_file=None,
            )
            transport = ParentSyncTransport(config)

            with self.assertRaisesRegex(PermissionError, "must not be readable"):
                transport.exchange("INALH-223e4567-e89b-42d3-a456-426614174001", {})

    def test_upstream_credential_rejects_malformed_and_symbolic_link_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "parent.token"
            token_file.write_text("short-token", encoding="utf-8")
            token_file.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "canonical"):
                _read_secret(token_file)

            token_file.write_text(f"inas_sync_v1_{'A' * 43}", encoding="utf-8")
            token_link = root / "parent-link.token"
            token_link.symlink_to(token_file)
            with self.assertRaises(OSError):
                _read_secret(token_link)

    def test_transport_bounds_compressed_and_decompressed_response(self):
        decoded = os.urandom(1024 * 1024)
        encoded = gzip.compress(decoded)
        self.assertGreater(len(encoded), 1024 * 1024)
        response = io.BytesIO(encoded)
        response.headers = {"Content-Encoding": "gzip"}

        with self.assertRaisesRegex(ParentSyncTransportError, "encoded limit"):
            _read_bounded_response(response)


if __name__ == "__main__":
    unittest.main()
