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

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.sensor_device_repository import SensorDeviceRepository  # noqa: E402


class WebServerBasicUITest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sensor_device_repository = SensorDeviceRepository()
        self.sensor_device_repository.device_repo_path = os.path.join(self.tmp_dir.name, ".device_list.json")
        self.sensor_device_repository.device_dict = {}
        self.sensor_device_repository.save()

        self.original_sensor_device_repository = web_server.sensor_device_repository
        web_server.sensor_device_repository = lambda: self.sensor_device_repository
        self.client = web_server.app.test_client()

    def tearDown(self):
        web_server.sensor_device_repository = self.original_sensor_device_repository
        self.tmp_dir.cleanup()

    def test_device_edit_form_updates_existing_device(self):
        device_id = "sensor-1"
        self.sensor_device_repository.add(device_id, {"name": "old", "location": "north", "info": "before"})

        response = self.client.post(
            f"/devices/{device_id}/edit",
            data={"name": "new name", "location": "south", "info": "after"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/devices/{device_id}")
        self.assertEqual(
            self.sensor_device_repository.get(device_id),
            {"id": device_id, "name": "new name", "location": "south", "info": "after"},
        )

    def test_device_edit_form_exposes_all_editable_fields(self):
        device_id = "sensor-2"
        self.sensor_device_repository.add(device_id, {"name": "sensor", "location": "east", "info": "memo"})

        response = self.client.get(f"/devices/{device_id}/edit")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('name="name"', html)
        self.assertIn('name="location"', html)
        self.assertIn('name="info"', html)

    def test_location_add_form_supports_file_upload(self):
        response = self.client.get("/locations/add")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('name="location_image"', html)


if __name__ == "__main__":
    unittest.main()
