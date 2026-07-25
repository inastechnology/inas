import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_edge_runtime import NodeType, parse_node_id  # noqa: E402
from ina_edge_runtime.protocol import content_hash  # noqa: E402

from ina_device_hub.device_config_repository import DeviceConfigRepository  # noqa: E402
from ina_device_hub.device_config_service import DeviceConfigService  # noqa: E402
from ina_device_hub.local_edge_runtime import LocalEdgeRuntime  # noqa: E402

DEVICE_ID = "INADS-00000000-0000-4000-8000-000000000031"


class _NotificationService:
    def notify_new_device(self, *_args, **_kwargs):
        return None


class _BrokenRuntimeConfigCache:
    def cache_runtime_config(self, *_args, **_kwargs):
        raise OSError("simulated cache failure")


class _PublishResult:
    rc = 0


class _MQTTClient:
    def __init__(self):
        self.calls = []

    def publish(self, topic, payload, *, qos, retain):
        self.calls.append({"topic": topic, "payload": json.loads(payload), "qos": qos, "retain": retain})
        return _PublishResult()


class LocalEdgeRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.runtime = LocalEdgeRuntime.open(self.temporary_directory.name)

    def tearDown(self):
        self.runtime.close()
        self.temporary_directory.cleanup()

    def test_local_hub_identity_is_generated_once_and_reused(self):
        first_node_id = self.runtime.node_id
        identity = parse_node_id(first_node_id)
        self.assertEqual(identity.node_type, NodeType.LOCAL_HUB)

        self.runtime.close()
        self.runtime = LocalEdgeRuntime.open(self.temporary_directory.name)

        self.assertEqual(self.runtime.node_id, first_node_id)
        identity_path = Path(self.temporary_directory.name) / "edge-runtime" / "identity.json"
        identity_document = json.loads(identity_path.read_text(encoding="utf-8"))
        self.assertEqual(identity_document["node_id"], first_node_id)
        self.assertEqual(identity_document["node_type"], "local_hub")

    def test_runtime_config_cache_is_idempotent_and_revisioned(self):
        first = self.runtime.cache_runtime_config(
            DEVICE_ID,
            {"moisture_threshold": 35},
            updated_at="2026-07-23T04:30:00Z",
        )
        unchanged = self.runtime.cache_runtime_config(
            DEVICE_ID,
            {"moisture_threshold": 35},
            updated_at="2026-07-23T04:31:00Z",
        )
        changed = self.runtime.cache_runtime_config(
            DEVICE_ID,
            {"moisture_threshold": 45},
            updated_at="2026-07-23T04:32:00Z",
        )

        self.assertEqual(first.revision, 1)
        self.assertEqual(unchanged.revision, 1)
        self.assertEqual(changed.revision, 2)
        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID), {"moisture_threshold": 45})

    def test_device_service_caches_the_effective_active_config(self):
        repository = self._repository()
        service = DeviceConfigService(
            repository=repository,
            notification_service=_NotificationService(),
            event_log_dispatcher=lambda callback: callback(),
            runtime_config_cache=self.runtime,
        )
        config = service.default_config()
        config["moisture_threshold"] = 47

        service.update_config(DEVICE_ID, config)
        service.set_state(DEVICE_ID, "active", approved_by="operator")
        reply = service._config_for_reply(DEVICE_ID)

        self.assertEqual(reply["moisture_threshold"], 47)
        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID)["moisture_threshold"], 47)

    def test_event_outbox_survives_restart_until_explicit_acknowledgement(self):
        stored = self.runtime.enqueue_event(
            event_type="device.status",
            occurred_at="2026-07-23T04:33:00Z",
            device_id=DEVICE_ID,
            payload={"direction": "inbound", "status": {"seq": 12}},
        )

        self.runtime.close()
        self.runtime = LocalEdgeRuntime.open(self.temporary_directory.name)

        pending = self.runtime.pending_events()
        self.assertEqual([event.event_id for event in pending], [stored.event_id])
        self.assertEqual(pending[0].origin_node_id, self.runtime.node_id)
        self.assertEqual(pending[0].payload["status"]["seq"], 12)
        self.assertEqual(self.runtime.ack_events([stored.event_id]), 1)
        self.assertEqual(self.runtime.pending_events(), [])

    def test_cache_failure_falls_back_to_the_existing_json_record(self):
        repository = self._repository()
        service = DeviceConfigService(
            repository=repository,
            notification_service=_NotificationService(),
            event_log_dispatcher=lambda callback: callback(),
        )
        config = service.default_config()
        config["moisture_threshold"] = 49
        repository.upsert(DEVICE_ID, config)
        repository.set_state(DEVICE_ID, "active", approved_by="operator")
        service.runtime_config_cache = _BrokenRuntimeConfigCache()

        with self.assertLogs("general", level="ERROR"):
            reply = service._config_for_reply(DEVICE_ID)

        self.assertEqual(reply["moisture_threshold"], 49)

    def test_parent_runtime_config_remains_authoritative_for_reply_and_push(self):
        repository = self._repository()
        service = DeviceConfigService(
            repository=repository,
            notification_service=_NotificationService(),
            event_log_dispatcher=lambda callback: callback(),
            runtime_config_cache=self.runtime,
        )
        local_config = service.default_config()
        local_config["moisture_threshold"] = 40
        service.update_config(DEVICE_ID, local_config)
        service.set_state(DEVICE_ID, "active", approved_by="operator")
        parent_config = service.default_config()
        parent_config["moisture_threshold"] = 62
        self.runtime.apply_parent_runtime_config(
            {
                "resource_type": "device.runtime_config",
                "resource_id": DEVICE_ID,
                "target_node_id": self.runtime.node_id,
                "revision": 1,
                "operation": "upsert",
                "content_sha256": content_hash(parent_config),
                "updated_at": "2026-07-23T04:35:00Z",
                "payload": parent_config,
            }
        )

        later_local_config = service.default_config()
        later_local_config["moisture_threshold"] = 15
        service.update_config(DEVICE_ID, later_local_config)
        mqtt = _MQTTClient()
        service.attach_mqtt_client(mqtt)
        reply = service._config_for_reply(DEVICE_ID)
        pushed = service.publish_push(DEVICE_ID)

        self.assertEqual(reply["moisture_threshold"], 62)
        self.assertEqual(self.runtime.get_runtime_config(DEVICE_ID)["moisture_threshold"], 62)
        self.assertEqual(pushed["payload"]["moisture_threshold"], 62)
        self.assertEqual(mqtt.calls[0]["topic"], f"/{DEVICE_ID}/kinds/config/push")
        self.assertTrue(mqtt.calls[0]["retain"])

    def _repository(self):
        repository = DeviceConfigRepository()
        repository.device_config_path = os.path.join(self.temporary_directory.name, ".device_configs.json")
        repository.device_configs = {}
        repository.save()
        return repository


if __name__ == "__main__":
    unittest.main()
