import json
import tempfile
import unittest
import uuid
from pathlib import Path

from ina_edge_runtime.protocol import content_hash
from ina_edge_runtime.store import EdgeStore

from ina_edge_gateway.commands import GatewayCommandExecutor
from ina_edge_gateway.controller import DeviceMessageController

EDGE_ID = "INAEG-123e4567-e89b-42d3-a456-426614174001"
DEVICE_ID = "INADS-123e4567-e89b-42d3-a456-426614174000"


class _PublishResult:
    def __init__(self, rc=0):
        self.rc = rc


class _Publisher:
    def __init__(self):
        self.calls = []
        self.rc = 0

    def publish(self, topic, payload, *, qos, retain):
        self.calls.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})
        return _PublishResult(self.rc)


class ControllerAndCommandTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temporary_directory.name) / "edge.db"
        self.store = EdgeStore(self.store_path)
        self.publisher = _Publisher()

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def test_cached_config_reply_is_local_and_uses_existing_wire_behavior(self):
        config = {"moisture_threshold": 42, "schedules": []}
        self._cache_config(config)
        controller = DeviceMessageController(store=self.store, node_id=EDGE_ID, publisher=self.publisher)

        handled = controller.handle_message(
            f"/{DEVICE_ID}/kinds/config/request",
            b'{"request":"runtime_config"}',
        )

        self.assertTrue(handled)
        self.assertEqual(len(self.publisher.calls), 1)
        published = self.publisher.calls[0]
        self.assertEqual(published["topic"], f"/{DEVICE_ID}/kinds/config/reply")
        self.assertEqual(json.loads(published["payload"]), config)
        self.assertEqual(published["qos"], 0)
        self.assertFalse(published["retain"])
        self.assertEqual(self.store.pending_events()[0].event_type, "device.config_reply")

    def test_telemetry_survives_restart_and_config_miss_does_not_invent_defaults(self):
        controller = DeviceMessageController(store=self.store, node_id=EDGE_ID, publisher=self.publisher)
        controller.handle_message("farm/INADS-123e4567-e89b-42d3-a456-426614174000/telemetry", b'{"soil_moisture":41.2}')
        controller.handle_message(f"/{DEVICE_ID}/kinds/config/request", b"")
        self.store.close()
        self.store = EdgeStore(self.store_path)

        events = self.store.pending_events()
        self.assertEqual([event.event_type for event in events], ["device.telemetry", "device.config_cache_miss"])
        self.assertEqual(events[0].payload["body"]["soil_moisture"], 41.2)
        self.assertEqual(self.publisher.calls, [])

    def test_oversized_mqtt_payload_is_rejected_before_parsing(self):
        controller = DeviceMessageController(store=self.store, node_id=EDGE_ID, publisher=self.publisher)

        handled = controller.handle_message(
            f"/{DEVICE_ID}/kinds/config/request",
            b"x" * ((256 * 1024) + 1),
        )

        self.assertFalse(handled)
        self.assertEqual(self.publisher.calls, [])
        event = self.store.pending_events()[0]
        self.assertEqual(event.event_type, "mqtt.payload_rejected")
        self.assertEqual(event.payload["reason"], "payload_too_large")
        self.assertEqual(event.payload["size_bytes"], (256 * 1024) + 1)

    def test_runtime_config_push_is_executed_once_and_records_terminal_result(self):
        self._cache_config({"moisture_threshold": 44, "schedules": []})
        command_id = str(uuid.uuid4())
        self.store.receive_command(
            command_id=command_id,
            idempotency_key="push-once",
            command_type="device.runtime_config_push",
            target_node_id=EDGE_ID,
            device_id=DEVICE_ID,
            issued_at="2099-01-01T00:00:00Z",
            expires_at="2099-01-01T00:05:00Z",
            payload={},
        )
        executor = GatewayCommandExecutor(store=self.store, node_id=EDGE_ID, publisher=self.publisher)

        self.assertEqual(executor.process(), 1)
        self.assertEqual(executor.process(), 0)

        self.assertEqual(len(self.publisher.calls), 1)
        self.assertEqual(self.publisher.calls[0]["topic"], f"/{DEVICE_ID}/kinds/config/push")
        self.assertTrue(self.publisher.calls[0]["retain"])
        self.assertEqual(self.store.get_command(command_id).status, "succeeded")
        results = self.store.pending_command_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "succeeded")

    def test_expired_and_unsupported_commands_are_never_published(self):
        expired_id = str(uuid.uuid4())
        unsupported_id = str(uuid.uuid4())
        expired = self.store.receive_command(
            command_id=expired_id,
            idempotency_key="expired",
            command_type="device.runtime_config_push",
            target_node_id=EDGE_ID,
            device_id=DEVICE_ID,
            issued_at="2020-01-01T00:00:00Z",
            expires_at="2020-01-01T00:01:00Z",
            payload={},
        )
        self.store.receive_command(
            command_id=unsupported_id,
            idempotency_key="unsupported",
            command_type="device.water_now",
            target_node_id=EDGE_ID,
            device_id=DEVICE_ID,
            issued_at="2099-01-01T00:00:00Z",
            expires_at="2099-01-01T00:05:00Z",
            payload={},
        )
        executor = GatewayCommandExecutor(store=self.store, node_id=EDGE_ID, publisher=self.publisher)
        executor.record_received_terminal_commands((expired,))
        executor.process()

        self.assertEqual(self.publisher.calls, [])
        statuses = {result.command_id: result.status for result in self.store.pending_command_results()}
        self.assertEqual(statuses[expired_id], "expired")
        self.assertEqual(statuses[unsupported_id], "rejected")

    def _cache_config(self, config):
        self.store.apply_desired_resource(
            resource_type="device.runtime_config",
            resource_id=DEVICE_ID,
            target_node_id=EDGE_ID,
            revision=1,
            operation="upsert",
            content_sha256=content_hash(config),
            updated_at="2026-07-23T02:14:00Z",
            payload=config,
        )


if __name__ == "__main__":
    unittest.main()
