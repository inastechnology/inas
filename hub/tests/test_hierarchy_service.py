import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from ina_edge_runtime import build_sync_request
from ina_edge_runtime.protocol import content_hash

from ina_device_hub.hierarchy_repository import HierarchyRepository
from ina_device_hub.hierarchy_service import HierarchyService
from ina_device_hub.local_edge_runtime import LocalEdgeRuntime

CHILD_HUB_ID = "INALH-223e4567-e89b-42d3-a456-426614174001"
DESCENDANT_EDGE_ID = "INAEG-323e4567-e89b-42d3-a456-426614174001"
OTHER_EDGE_ID = "INAEG-423e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"
NOW = datetime(2026, 7, 23, 2, 15, tzinfo=UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class _MQTT:
    def is_connected(self):
        return True


class _DeviceService:
    def __init__(self):
        self.pushed = []

    def publish_push(self, device_id):
        self.pushed.append(device_id)
        return {
            "topic": f"/{device_id}/kinds/config/push",
            "payload": {},
            "mqtt_rc": 0,
        }


class HierarchyServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.runtime = LocalEdgeRuntime.open(self.root)
        self.repository = HierarchyRepository(
            self.root / "edge-runtime" / "hierarchy.db",
            parent_node_id=self.runtime.node_id,
        )
        self.device_service = _DeviceService()
        self.service = HierarchyService(
            repository=self.repository,
            runtime=self.runtime,
            device_service_provider=lambda: self.device_service,
        )
        self.service.attach_mqtt_client(_MQTT())

    def tearDown(self):
        self.repository.close()
        self.runtime.close()
        self.temporary_directory.cleanup()

    def test_child_exchange_authenticates_subtree_and_preserves_event_identity(self):
        enrolled = self.service.enroll_child(CHILD_HUB_ID, descendant_node_ids=[DESCENDANT_EDGE_ID])
        event = self._child_event()
        request = self._child_request(events=[event])

        response = self.service.exchange_child(CHILD_HUB_ID, enrolled["bearer_token"], request)

        self.assertEqual(response["ack_event_ids"], [event["event_id"]])
        stored = self.repository.list_events()[0]
        self.assertEqual(stored["event_id"], event["event_id"])
        self.assertEqual(stored["origin_node_id"], DESCENDANT_EDGE_ID)
        self.assertEqual(stored["sequence"], 11)

        request["request_id"] = new_id()
        request["events"][0] = {**event, "event_id": new_id(), "origin_node_id": OTHER_EDGE_ID}
        with self.assertRaisesRegex(ValueError, "outside"):
            self.service.exchange_child(CHILD_HUB_ID, enrolled["bearer_token"], request)
        self.assertEqual(len(self.repository.list_events()), 1)

    def test_parent_response_routes_descendant_state_and_only_acks_named_events(self):
        self.service.enroll_child(CHILD_HUB_ID, descendant_node_ids=[DESCENDANT_EDGE_ID])
        first = self.runtime.enqueue_event(
            event_type="device.status",
            occurred_at="2026-07-23T02:14:50Z",
            device_id=DEVICE_ID,
            payload={"value": 1},
        )
        second = self.runtime.enqueue_event(
            event_type="device.status",
            occurred_at="2026-07-23T02:14:51Z",
            device_id=DEVICE_ID,
            payload={"value": 2},
        )
        batch = self._parent_batch()
        command_id = new_id()
        response = self._parent_response(
            batch,
            ack_event_ids=[first.event_id],
            desired_resources=[self._runtime_resource(target_node_id=DESCENDANT_EDGE_ID)],
            commands=[self._command(command_id=command_id, target_node_id=DESCENDANT_EDGE_ID)],
        )

        poll_seconds = self.service.apply_parent_response(batch, response, now=NOW)

        self.assertEqual(poll_seconds, 15)
        self.assertEqual([event.event_id for event in self.runtime.pending_events()], [second.event_id])
        self.assertEqual(self.runtime.store.get_sync_cursor(), "upstream-cursor-1")
        self.assertEqual(
            self.repository.desired_for_child(CHILD_HUB_ID)[0]["target_node_id"],
            DESCENDANT_EDGE_ID,
        )
        self.assertEqual(
            self.repository.commands_for_child(CHILD_HUB_ID, now=NOW)[0]["command_id"],
            command_id,
        )

    def test_first_valid_parent_success_activates_local_events_and_backfills_children(self):
        enrolled = self.service.enroll_child(CHILD_HUB_ID, descendant_node_ids=[DESCENDANT_EDGE_ID])
        event = self._child_event()
        self.service.exchange_child(
            CHILD_HUB_ID,
            enrolled["bearer_token"],
            self._child_request(events=[event]),
        )
        self.service.handle_local_device_event(
            {
                "event_type": "device_status",
                "occurred_at": "2026-07-23T02:14:59Z",
                "device_id": DEVICE_ID,
                "payload": {"before": True},
            }
        )
        self.assertEqual(self.runtime.pending_events(), [])

        batch = self._parent_batch()
        self.service.apply_parent_response(batch, self._parent_response(batch), now=NOW)
        self.service.handle_local_device_event(
            {
                "event_type": "device_status",
                "occurred_at": "2026-07-23T02:15:01Z",
                "device_id": DEVICE_ID,
                "payload": {"after": True},
            }
        )

        pending = self.runtime.pending_events()
        self.assertTrue(self.repository.upstream_active())
        self.assertEqual(pending[0].event_id, event["event_id"])
        self.assertEqual(pending[0].origin_node_id, DESCENDANT_EDGE_ID)
        self.assertEqual(pending[0].sequence, 11)
        self.assertEqual(pending[1].origin_node_id, self.runtime.node_id)

    def test_parent_controls_direct_runtime_config_and_local_command_is_idempotent(self):
        batch = self._parent_batch()
        command_id = new_id()
        resource = self._runtime_resource(target_node_id=self.runtime.node_id)
        response = self._parent_response(
            batch,
            desired_resources=[resource],
            commands=[self._command(command_id=command_id, target_node_id=self.runtime.node_id)],
        )

        self.service.apply_parent_response(batch, response, now=NOW)
        self.service.apply_parent_response(batch, response, now=NOW)

        self.assertTrue(self.runtime.is_parent_runtime_config_authoritative(DEVICE_ID))
        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID), resource["payload"])
        self.assertEqual(self.device_service.pushed, [DEVICE_ID])
        results = self.runtime.store.pending_command_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].command_id, command_id)
        self.assertEqual(results[0].status, "succeeded")

    def test_stale_parent_runtime_revision_cannot_roll_back_direct_device_config(self):
        first_batch = self._parent_batch()
        newer = self._runtime_resource(
            target_node_id=self.runtime.node_id,
            revision=3,
            moisture_threshold=61,
        )
        self.service.apply_parent_response(
            first_batch,
            self._parent_response(first_batch, desired_resources=[newer]),
            now=NOW,
        )
        second_batch = self._parent_batch()
        stale = self._runtime_resource(
            target_node_id=self.runtime.node_id,
            revision=2,
            moisture_threshold=14,
        )

        self.service.apply_parent_response(
            second_batch,
            self._parent_response(second_batch, desired_resources=[stale]),
            now=NOW,
        )

        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID)["moisture_threshold"], 61)
        with self.assertRaisesRegex(ValueError, "revision is stale"):
            self.runtime.apply_parent_runtime_config(stale)
        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID)["moisture_threshold"], 61)

    def test_changed_parent_binding_requires_fresh_handshake_and_cursor(self):
        class ParentClient:
            parent_binding = "https://new-parent.example.test"

            def start(self):
                return None

            def stop(self):
                return None

        self.repository.set_upstream_active(True)
        self.repository.set_metadata("upstream_parent_base_url", "https://old-parent.example.test")
        self.runtime.store.set_sync_cursor("old-parent-cursor")

        with patch(
            "ina_device_hub.parent_sync_client.parent_sync_client_from_environment",
            return_value=ParentClient(),
        ):
            self.service.start()
        try:
            self.assertFalse(self.repository.upstream_active())
            self.assertIsNone(self.runtime.store.get_sync_cursor())
        finally:
            self.service.stop()

    def _parent_batch(self):
        return build_sync_request(
            self.runtime.store,
            node_id=self.runtime.node_id,
            sent_at=NOW,
            health={
                "status": "ok",
                "software_version": "0.1.0",
                "hardware_profile_id": "local-hub",
                "mqtt_connected": True,
                "storage_total_bytes": 1000,
                "storage_free_bytes": 500,
                "capabilities": ["mqtt", "sync_parent"],
            },
        )

    def _parent_response(self, batch, **overrides):
        return {
            "protocol_version": "1.0",
            "correlation_request_id": batch.document["request_id"],
            "server_time": "2026-07-23T02:15:00Z",
            "next_cursor": "upstream-cursor-1",
            "ack_event_ids": [],
            "ack_command_result_ids": [],
            "desired_resources": [],
            "commands": [],
            "next_poll_seconds": 15,
            **overrides,
        }

    def _runtime_resource(self, *, target_node_id, revision=1, moisture_threshold=42):
        payload = {
            "ntp_server": "192.168.50.1",
            "timezone_offset_sec": 32400,
            "moisture_threshold": moisture_threshold,
            "schedules": [],
        }
        return {
            "resource_type": "device.runtime_config",
            "resource_id": DEVICE_ID,
            "target_node_id": target_node_id,
            "revision": revision,
            "operation": "upsert",
            "content_sha256": content_hash(payload),
            "updated_at": "2026-07-23T02:14:00Z",
            "payload": payload,
        }

    def _command(self, *, command_id, target_node_id):
        return {
            "command_id": command_id,
            "idempotency_key": f"command-{command_id}",
            "command_type": "device.runtime_config_push",
            "target_node_id": target_node_id,
            "device_id": DEVICE_ID,
            "issued_at": "2026-07-23T02:14:00Z",
            "expires_at": "2026-07-23T02:20:00Z",
            "payload": {},
        }

    def _child_request(self, *, events=None):
        return {
            "protocol_version": "1.0",
            "request_id": new_id(),
            "node_id": CHILD_HUB_ID,
            "node_type": "local_hub",
            "sent_at": "2026-07-23T02:15:00Z",
            "cursor": None,
            "events": events or [],
            "command_results": [],
            "health": {
                "status": "ok",
                "software_version": "0.1.0",
                "outbox_depth": len(events or []),
                "mqtt_connected": True,
                "storage_free_bytes": 500,
                "capabilities": ["mqtt", "sync_parent"],
            },
        }

    def _child_event(self):
        return {
            "event_id": new_id(),
            "origin_node_id": DESCENDANT_EDGE_ID,
            "sequence": 11,
            "schema_version": 1,
            "event_type": "device.telemetry",
            "occurred_at": "2026-07-23T02:14:58Z",
            "device_id": DEVICE_ID,
            "payload": {"soil_moisture": 41},
        }


if __name__ == "__main__":
    unittest.main()
