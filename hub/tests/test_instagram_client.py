import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

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

from ina_device_hub.instagram_client import InstagramClient
from ina_device_hub.instagram_post_task import InstagramPostTask


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class InstagramClientTest(unittest.TestCase):
    def test_account_profile_requests_id_and_username(self):
        client = InstagramClient("1784", "secret-token")
        with patch(
            "ina_device_hub.instagram_client.request.urlopen",
            return_value=FakeResponse({"id": "1784", "username": "garden_account"}),
        ) as urlopen:
            profile = client.get_account_profile()

        self.assertEqual(profile, {"id": "1784", "username": "garden_account"})
        request_url = urlopen.call_args.args[0].full_url
        self.assertIn("fields=id%2Cusername", request_url)

    def test_account_profile_rejects_incomplete_response(self):
        client = InstagramClient("1784", "secret-token")
        with patch(
            "ina_device_hub.instagram_client.request.urlopen",
            return_value=FakeResponse({"id": "1784"}),
        ):
            with self.assertRaises(RuntimeError):
                client.get_account_profile()

    def test_instagram_schedule_is_not_read_from_ai_settings(self):
        task = InstagramPostTask.__new__(InstagramPostTask)
        task.ai_settings = {"agent_schedule_start": "01:02"}
        task.instagram_settings = {"post_schedule_start": "07:45"}

        self.assertEqual(task._parse_schedule(), (7, 45))

    def test_instagram_post_task_is_disabled_while_posting_is_paused(self):
        task = InstagramPostTask.__new__(InstagramPostTask)
        task.ai_settings = {"enabled": True}
        task.instagram_settings = {
            "posting_paused": True,
            "user_id": "1784",
            "access_token": "secret-token",
            "camera_id": "camera-1",
        }
        task.storage_connector = Mock()

        self.assertFalse(task.is_enabled())
        task.storage_connector.is_temporary_storage_configured.assert_not_called()


if __name__ == "__main__":
    unittest.main()
