import json
import os
import tempfile
import unittest

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

from ina_device_hub.device_config_repository import DeviceConfigRepository, DeviceConfigValidationError, validate_device_config  # noqa: E402
from ina_device_hub.device_event_log import _event_log_path  # noqa: E402
from ina_device_hub.device_config_service import DeviceConfigService  # noqa: E402


class _Result:
    rc = 0


class _MqttClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})
        return _Result()


class MqttDeviceConfigServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = DeviceConfigRepository()
        self.repository.device_config_path = os.path.join(self.tmp_dir.name, ".device_configs.json")
        self.repository.device_configs = {}
        self.repository.save()
        self.service = DeviceConfigService(repository=self.repository)
        self.mqtt_client = _MqttClient()
        self.service.attach_mqtt_client(self.mqtt_client)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_config_request_registers_pending_device_and_replies_default_threshold(self):
        handled = self.service.handle_mqtt_message(
            None,
            {
                "message_type": "device_config",
                "device_id": "INADS-00000000-0000-4000-8000-000000000001",
                "category": "config",
                "action": "request",
                "payload": b'{"request":"runtime_config"}',
            },
        )

        self.assertTrue(handled)
        record = self.repository.get("INADS-00000000-0000-4000-8000-000000000001")
        self.assertEqual(record["state"], "pending")
        self.assertEqual(record["config"]["moisture_threshold"], 35)
        self.assertEqual(record["config"]["schedules"][0]["hour"], 6)
        self.assertEqual(record["config"]["schedules"][0]["minute"], 30)
        self.assertTrue(record["config"]["force_watering"])
        self.assertIsNotNone(record["last_config_request_at"])
        self.assertIsNotNone(record["last_config_reply_at"])
        self.assertEqual(self.mqtt_client.published[0]["topic"], "/INADS-00000000-0000-4000-8000-000000000001/kinds/config/reply")
        self.assertIn('"moisture_threshold":35', self.mqtt_client.published[0]["payload"])
        self.assertIn('"force_watering":true', self.mqtt_client.published[0]["payload"])
        self.assertFalse(self.mqtt_client.published[0]["retain"])
        self.assertEqual(self.mqtt_client.published[0]["qos"], 0)

    def test_active_device_replies_saved_runtime_config(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000002"
        config = {
            "ntp_server": "pool.ntp.org",
            "timezone_offset_sec": 32400,
            "moisture_threshold": 45,
            "force_watering": True,
            "schedules": [{"hour": 8, "minute": 15, "duration_sec": 30, "channel_mask": 3}],
        }
        self.service.update_config(device_id, config)
        self.service.set_state(device_id, "active", approved_by="operator")

        self.service.handle_mqtt_message(
            None,
            {
                "message_type": "device_config",
                "device_id": device_id,
                "category": "config",
                "action": "request",
                "payload": '{"request":"runtime_config"}',
            },
        )

        self.assertIn('"moisture_threshold":45', self.mqtt_client.published[0]["payload"])
        self.assertIn('"force_watering":true', self.mqtt_client.published[0]["payload"])
        event = _read_last_device_event()
        self.assertEqual(event["event_type"], "device_config_publish")
        self.assertEqual(event["direction"], "outbound")
        self.assertEqual(event["device_id"], device_id)
        self.assertEqual(event["payload"]["moisture_threshold"], 45)

    def test_config_request_replies_even_when_payload_is_empty_or_invalid(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000004"
        for payload in (b"", b"not-json"):
            with self.subTest(payload=payload):
                self.mqtt_client.published = []
                handled = self.service.handle_mqtt_message(
                    None,
                    {
                        "message_type": "device_config",
                        "device_id": device_id,
                        "category": "config",
                        "action": "request",
                        "payload": payload,
                    },
                )

                self.assertTrue(handled)
                self.assertEqual(self.mqtt_client.published[0]["topic"], f"/{device_id}/kinds/config/reply")

    def test_status_publish_updates_last_status_and_history(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000003"
        handled = self.service.handle_mqtt_message(
            None,
            {
                "message_type": "device_config",
                "device_id": device_id,
                "category": "agri",
                "action": "immediate",
                "payload": b'{"seq":123,"config_received":true,"time_synced":true,"next_sleep_sec":60}',
            },
        )

        self.assertTrue(handled)
        record = self.repository.get(device_id)
        self.assertEqual(record["last_status"]["seq"], 123)
        self.assertEqual(self.service.list_statuses(device_id)[0]["payload"]["seq"], 123)
        event = _read_last_device_event()
        self.assertEqual(event["event_type"], "device_status")
        self.assertEqual(event["direction"], "inbound")
        self.assertEqual(event["device_id"], device_id)
        self.assertEqual(event["payload"]["seq"], 123)
        self.assertEqual(event["next_sleep_sec"], 60)
        self.assertIn("next_wake_at", event)

    def test_config_validation_requires_schedule_and_payload_under_512_bytes(self):
        with self.assertRaises(DeviceConfigValidationError):
            validate_device_config(
                {
                    "ntp_server": "pool.ntp.org",
                    "timezone_offset_sec": 32400,
                    "moisture_threshold": 40,
                    "schedules": [],
                }
            )

        with self.assertRaises(DeviceConfigValidationError):
            validate_device_config(
                {
                    "ntp_server": "x" * 480,
                    "timezone_offset_sec": 32400,
                    "moisture_threshold": 40,
                    "schedules": [{"hour": 7, "minute": 0, "duration_sec": 1, "channel_mask": 1}],
                }
            )

        with self.assertRaises(DeviceConfigValidationError):
            validate_device_config(
                {
                    "ntp_server": "pool.ntp.org",
                    "timezone_offset_sec": 32400,
                    "moisture_threshold": 40,
                    "force_watering": "true",
                    "schedules": [{"hour": 7, "minute": 0, "duration_sec": 1, "channel_mask": 1}],
                }
            )


def _read_last_device_event():
    with open(_event_log_path(), encoding="utf-8") as file:
        lines = [line for line in file.readlines() if line.strip()]
    return json.loads(lines[-1])


if __name__ == "__main__":
    unittest.main()
