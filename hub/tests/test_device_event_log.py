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

from ina_device_hub.device_event_log import append_mqtt_broker_log, append_mqtt_message_event, list_device_events  # noqa: E402


class DeviceEventLogTest(unittest.TestCase):
    def test_broker_log_connected_extracts_device_id(self):
        event = append_mqtt_broker_log(
            "$SYS/broker/log/N",
            b"1782761486: New client connected from 192.168.1.120:51411 as INADS-9f192f0e-5d10-4796-ae5c-b6095a068f3f (p2, c1, k60).",
        )

        self.assertEqual(event["event_type"], "mqtt_client_connected")
        self.assertEqual(event["device_id"], "INADS-9f192f0e-5d10-4796-ae5c-b6095a068f3f")
        self.assertEqual(event["action"], "connect")
        self.assertEqual(event["payload"]["remote_address"], "192.168.1.120:51411")

    def test_mqtt_message_event_records_device_topic(self):
        event = append_mqtt_message_event(
            {
                "message_type": "device_config",
                "topic": "/INADS-00000000-0000-4000-8000-000000000001/kinds/agri/immediate",
                "device_id": "INADS-00000000-0000-4000-8000-000000000001",
                "category": "agri",
                "action": "immediate",
                "payload": b'{"seq":225,"config_received":true}',
            }
        )

        self.assertEqual(event["event_type"], "mqtt_message_received")
        self.assertEqual(event["payload"]["seq"], 225)

    def test_list_connection_events_filters_non_connection_events(self):
        append_mqtt_message_event(
            {
                "message_type": "device_config",
                "topic": "/INADS-00000000-0000-4000-8000-000000000002/kinds/agri/immediate",
                "device_id": "INADS-00000000-0000-4000-8000-000000000002",
                "category": "agri",
                "action": "immediate",
                "payload": b'{"seq":1}',
            }
        )
        append_mqtt_broker_log(
            "$SYS/broker/log/N",
            b"1782761486: Client INADS-00000000-0000-4000-8000-000000000002 disconnected.",
        )

        events = list_device_events(connection_events_only=True, limit=10)

        self.assertTrue(events)
        self.assertTrue(all(event["event_type"].startswith("mqtt_") for event in events))


if __name__ == "__main__":
    unittest.main()
