import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from paho.mqtt import client as mqtt_client_module

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "local")
os.environ.setdefault("TURSO_AUTH_TOKEN", "local")
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

from ina_device_hub.hub_mqtt_client import (  # noqa: E402
    DEFAULT_SUBSCRIPTION_TOPICS,
    MQTT_KEEPALIVE_SECONDS,
    MQTT_PROTOCOL,
    MQTT_TRANSPORT,
    HubMQTTClient,
    client_id,
)


class _ReasonCode:
    def __init__(self, failure=False, value=0):
        self.is_failure = failure
        self.value = value


class HubMQTTClientTest(unittest.TestCase):
    @patch("ina_device_hub.hub_mqtt_client.append_mqtt_hub_event")
    @patch("ina_device_hub.hub_mqtt_client.mqtt_client.Client")
    def test_connect_is_async_and_resubscribes_after_connection(self, client_factory, _append_event):
        mqtt_client = MagicMock()
        client_factory.return_value = mqtt_client
        current = HubMQTTClient(MagicMock())
        current.discord_notification_service = MagicMock()
        current.subscribe("farm/+/telemetry")

        current.connect_mqtt()
        current.start()
        mqtt_client.on_connect(mqtt_client, None, None, _ReasonCode(), None)

        client_factory.assert_called_once_with(
            mqtt_client_module.CallbackAPIVersion.VERSION2,
            client_id,
            protocol=MQTT_PROTOCOL,
            transport=MQTT_TRANSPORT,
        )
        mqtt_client.connect_async.assert_called_once_with("localhost", 1883, keepalive=MQTT_KEEPALIVE_SECONDS)
        mqtt_client.username_pw_set.assert_not_called()
        mqtt_client.tls_set.assert_not_called()
        mqtt_client.loop_start.assert_called_once()
        mqtt_client.subscribe.assert_called_once_with("farm/+/telemetry", qos=0)
        self.assertTrue(current.is_connected())

        mqtt_client.on_disconnect(mqtt_client, None, None, _ReasonCode(failure=True, value=1), None)
        self.assertFalse(current.is_connected())

    def test_subscription_topics_match_the_existing_device_contract(self):
        self.assertEqual(
            DEFAULT_SUBSCRIPTION_TOPICS,
            (
                "farm/+/telemetry",
                "sensor/+/#",
                "/+/kinds/config/request",
                "/+/kinds/agri/immediate",
                "/+/kinds/debug/log",
                "/+/kinds/ota/request",
                "/+/kinds/ota/status",
                "$SYS/broker/log/#",
            ),
        )

    @patch("ina_device_hub.hub_mqtt_client.setting")
    @patch("ina_device_hub.hub_mqtt_client.mqtt_client.Client")
    def test_existing_username_password_are_forwarded_without_transport_changes(self, client_factory, setting_factory):
        mqtt_client = MagicMock()
        client_factory.return_value = mqtt_client
        setting_factory.return_value.get.return_value = {
            "mqtt_broker": "broker.example",
            "mqtt_port": 1883,
            "mqtt_username": "existing-user",
            "mqtt_password": "existing-password",
        }
        current = HubMQTTClient(MagicMock())

        current.connect_mqtt()

        mqtt_client.username_pw_set.assert_called_once_with("existing-user", "existing-password")
        mqtt_client.connect_async.assert_called_once_with("broker.example", 1883, keepalive=60)
        mqtt_client.tls_set.assert_not_called()

    def test_publish_defaults_remain_qos_one_and_not_retained(self):
        current = HubMQTTClient(MagicMock())
        current.discord_notification_service = MagicMock()
        current.client = MagicMock()
        current.client.publish.return_value.rc = 0

        current.publish("/device/kinds/test/reply", "{}")

        current.client.publish.assert_called_once_with("/device/kinds/test/reply", "{}", qos=1, retain=False)


if __name__ == "__main__":
    unittest.main()
