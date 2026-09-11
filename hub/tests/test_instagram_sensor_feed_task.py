import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

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

from PIL import Image  # noqa: E402

from ina_device_hub.instagram_sensor_feed_task import InstagramSensorFeedTask  # noqa: E402
from ina_device_hub.sensor_trend_card_service import SensorTrendCardService  # noqa: E402


class FakeStorageConnector:
    def __init__(self):
        self.saved = None

    def is_temporary_storage_configured(self):
        return True

    def save_bytes_to_temporary_cloud(self, key, image_bytes, content_type):
        self.saved = {"key": key, "bytes": image_bytes, "content_type": content_type}
        return key

    @staticmethod
    def get_temporary_public_url(key):
        return f"https://media.example/{key}"


class FakeMeasurementRepository:
    def __init__(self, measurements):
        self.measurements = measurements
        self.query = None

    def between_for_devices(self, device_ids, start_at, end_at, limit):
        self.query = {"device_ids": device_ids, "start_at": start_at, "end_at": end_at, "limit": limit}
        return self.measurements


class FakeInstagramClient:
    def __init__(self):
        self.post = None

    def post_photo(self, image_url, caption):
        self.post = {"image_url": image_url, "caption": caption}
        return "media-123"


class InstagramSensorFeedTaskTest(unittest.TestCase):
    def test_feed_schedule_is_independent_from_reel_schedule(self):
        task = InstagramSensorFeedTask.__new__(InstagramSensorFeedTask)
        task.instagram_settings = {"post_schedule_start": "09:01", "sensor_feed_schedule_start": "20:15"}

        self.assertEqual(task._parse_schedule(), (20, 15))

    def test_publish_creates_portrait_feed_image_from_three_day_measurements(self):
        timezone = ZoneInfo("Asia/Tokyo")
        end_at = datetime(2026, 9, 5, 20, 0, tzinfo=timezone)
        measurements = [
            {"device_id": "fgt-1", "metric": "soil_moisture_percent", "measured_at": "2026-09-03T10:00:00+09:00", "value": 41, "quality": "ok"},
            {"device_id": "fgt-1", "metric": "soil_moisture_percent", "measured_at": "2026-09-05T10:00:00+09:00", "value": 47, "quality": "ok"},
            {"device_id": "fgt-1", "metric": "par_umol_m2_s", "measured_at": "2026-09-03T12:00:00+09:00", "value": 650, "quality": "ok"},
            {"device_id": "fgt-1", "metric": "par_umol_m2_s", "measured_at": "2026-09-05T12:00:00+09:00", "value": 850, "quality": "ok"},
            {"device_id": "fgt-1", "metric": "soil_temperature_c", "measured_at": "2026-09-03T12:00:00+09:00", "value": 20, "quality": "ok"},
            {"device_id": "fgt-1", "metric": "soil_temperature_c", "measured_at": "2026-09-05T12:00:00+09:00", "value": 22, "quality": "ok"},
        ]
        task = InstagramSensorFeedTask.__new__(InstagramSensorFeedTask)
        task.timezone = timezone
        task.instagram_settings = {"user_id": "account", "access_token": "secret", "sensor_id": ""}
        task.storage_connector = FakeStorageConnector()
        task.measurement_repository = FakeMeasurementRepository(measurements)
        task.device_service = Mock()
        task.device_service.get_all_records.return_value = {"fgt-1": {"name": "鉢センサー", "device_kind": "FGT", "state": "active"}}
        task.ai_content_service = Mock()
        task.ai_content_service.generate_sensor_trend_impression.return_value = "そっと見守ろう"
        task.card_service = SensorTrendCardService()
        with tempfile.TemporaryDirectory() as temporary_directory:
            task.state_file_path = os.path.join(temporary_directory, "state.json")
            with open(task.state_file_path, "w", encoding="utf-8") as state_file:
                json.dump(
                    {
                        "last_post_at": "2026-09-04T20:00:00+09:00",
                        "last_impression": "そっと見守ろう",
                        "last_focus_metric": "soil_moisture_percent",
                    },
                    state_file,
                )
            client = FakeInstagramClient()

            result = task.publish_for_window(end_at, instagram_client=client)

        self.assertEqual(result["last_media_id"], "media-123")
        self.assertNotEqual(result["last_impression"], "そっと見守ろう")
        self.assertEqual(result["last_focus_metric"], "par_umol_m2_s")
        self.assertEqual(len(result["recent_posts"]), 2)
        self.assertEqual(task.measurement_repository.query["limit"], 20000)
        self.assertIn("2026-09-02T20:00:00+09:00", task.measurement_repository.query["start_at"])
        self.assertEqual(task.storage_connector.saved["content_type"], "image/jpeg")
        with Image.open(io.BytesIO(task.storage_connector.saved["bytes"])) as image:
            self.assertEqual(image.size, (1080, 1350))
        self.assertIn("#センサー記録", client.post["caption"])
        self.assertIn("#PAR", client.post["caption"])
        self.assertTrue(client.post["image_url"].startswith("https://media.example/"))
        generation_call = task.ai_content_service.generate_sensor_trend_impression.call_args
        self.assertEqual(generation_call.kwargs["recent_impressions"], ["そっと見守ろう"])
        self.assertEqual(generation_call.kwargs["editorial_context"]["focus_metric"], "par_umol_m2_s")


if __name__ == "__main__":
    unittest.main()
