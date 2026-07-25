import unittest

from ina_edge_runtime.mqtt_topics import parse_mqtt_message


class MqttTopicParserTest(unittest.TestCase):
    def test_parses_farm_telemetry(self):
        payload = b'{"temperature":25}'
        self.assertEqual(
            parse_mqtt_message("farm/device-1/telemetry", payload),
            {
                "message_type": "sensor_data",
                "topic": "farm/device-1/telemetry",
                "device_id": "device-1",
                "kind": "telemetry",
                "payload": payload,
                "seqId": None,
            },
        )

    def test_parses_legacy_sensor_topic_with_sequence(self):
        self.assertEqual(
            parse_mqtt_message("sensor/device-1/status/42", b"{}"),
            {
                "message_type": "sensor_data",
                "topic": "sensor/device-1/status/42",
                "device_id": "device-1",
                "kind": "status",
                "payload": b"{}",
                "seqId": "42",
            },
        )

    def test_parses_existing_device_runtime_topic(self):
        device_id = "INADS-123e4567-e89b-42d3-a456-426614174000"
        topic = f"/{device_id}/kinds/config/request"
        self.assertEqual(
            parse_mqtt_message(topic, b'{"request":"runtime_config"}'),
            {
                "message_type": "device_config",
                "topic": topic,
                "device_id": device_id,
                "category": "config",
                "action": "request",
                "payload": b'{"request":"runtime_config"}',
            },
        )

    def test_parses_broker_log_and_preserves_unknown(self):
        self.assertEqual(
            parse_mqtt_message("$SYS/broker/log/N", b"connected"),
            {
                "message_type": "mqtt_broker_log",
                "topic": "$SYS/broker/log/N",
                "kind": "N",
                "payload": b"connected",
            },
        )
        self.assertEqual(
            parse_mqtt_message("unrecognized/topic", b"raw"),
            {"message_type": "unknown", "topic": "unrecognized/topic", "payload": b"raw"},
        )


if __name__ == "__main__":
    unittest.main()
