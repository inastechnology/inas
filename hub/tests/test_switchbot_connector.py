import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest.mock import patch

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
os.environ.setdefault("MQTT_BROKER_USERNAME", "x")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "x")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.switchbot_api_client import SwitchBotAPIClient, SwitchBotAPIError  # noqa: E402
from ina_device_hub.switchbot_plug_mini_connector import SwitchBotPlugMiniConnector  # noqa: E402


class _Response:
    def __init__(self, body: dict):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


class _FakeClient:
    def __init__(self, status=None):
        self.status = status or {"power": "OFF"}
        self.commands = []

    def get_device_status(self, device_id):
        self.last_status_device_id = device_id
        return self.status

    def send_device_command(self, device_id, command, parameter="default", command_type="command"):
        self.commands.append({"device_id": device_id, "command": command, "parameter": parameter, "command_type": command_type})
        return {"commandId": f"cmd-{command}"}


class SwitchBotAPIClientTest(unittest.TestCase):
    def test_build_headers_uses_v1_1_signature(self):
        client = SwitchBotAPIClient(
            token="token",
            secret="secret",
            nonce_factory=lambda: "nonce",
            clock=lambda: 1.234,
        )

        headers = client._build_headers()

        expected_sign = base64.b64encode(hmac.new(b"secret", msg=b"token1234nonce", digestmod=hashlib.sha256).digest()).decode("utf-8")
        self.assertEqual(headers["Authorization"], "token")
        self.assertEqual(headers["t"], "1234")
        self.assertEqual(headers["nonce"], "nonce")
        self.assertEqual(headers["sign"], expected_sign)

    def test_send_device_command_posts_switchbot_payload(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = dict(req.header_items())
            captured["data"] = req.data
            captured["timeout"] = timeout
            return _Response({"statusCode": 100, "body": {"commandId": "CMD1"}, "message": "success"})

        client = SwitchBotAPIClient(
            token="token",
            secret="secret",
            base_url="https://api.example.test",
            timeout_seconds=7,
            nonce_factory=lambda: "nonce",
            clock=lambda: 1,
        )

        with patch("ina_device_hub.switchbot_api_client.request.urlopen", fake_urlopen):
            result = client.send_device_command("plug/1", "turnOn")

        self.assertEqual(result, {"commandId": "CMD1"})
        self.assertEqual(captured["url"], "https://api.example.test/v1.1/devices/plug%2F1/commands")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(json.loads(captured["data"].decode("utf-8")), {"commandType": "command", "command": "turnOn", "parameter": "default"})
        self.assertIn("application/json", captured["headers"]["Content-type"])

    def test_non_success_api_status_raises(self):
        client = SwitchBotAPIClient(token="token", secret="secret")

        with patch("ina_device_hub.switchbot_api_client.request.urlopen", return_value=_Response({"statusCode": 190, "message": "invalid"})):
            with self.assertRaises(SwitchBotAPIError) as context:
                client.get_device_status("plug-id")

        self.assertEqual(context.exception.api_status, 190)


class SwitchBotPlugMiniConnectorTest(unittest.TestCase):
    def test_turn_commands_are_mapped_to_plug_mini_commands(self):
        fake_client = _FakeClient()
        connector = SwitchBotPlugMiniConnector(device_id="plug-id", client=fake_client)

        self.assertEqual(connector.turn_on(), {"commandId": "cmd-turnOn"})
        self.assertEqual(connector.turn_off(), {"commandId": "cmd-turnOff"})
        self.assertEqual(connector.toggle(), {"commandId": "cmd-toggle"})
        self.assertEqual(
            fake_client.commands,
            [
                {"device_id": "plug-id", "command": "turnOn", "parameter": "default", "command_type": "command"},
                {"device_id": "plug-id", "command": "turnOff", "parameter": "default", "command_type": "command"},
                {"device_id": "plug-id", "command": "toggle", "parameter": "default", "command_type": "command"},
            ],
        )

    def test_is_on_accepts_power_and_switch_status_shapes(self):
        self.assertTrue(SwitchBotPlugMiniConnector(device_id="plug-id", client=_FakeClient({"power": "ON"})).is_on())
        self.assertFalse(SwitchBotPlugMiniConnector(device_id="plug-id", client=_FakeClient({"powerState": "OFF"})).is_on())
        self.assertTrue(SwitchBotPlugMiniConnector(device_id="plug-id", client=_FakeClient({"switchStatus": 1})).is_on())
        self.assertIsNone(SwitchBotPlugMiniConnector(device_id="plug-id", client=_FakeClient({"voltage": 101.0})).is_on())


if __name__ == "__main__":
    unittest.main()
