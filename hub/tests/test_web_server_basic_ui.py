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
from ina_device_hub.field_repository import FieldRepository  # noqa: E402
from ina_device_hub.sensor_device_repository import SensorDeviceRepository  # noqa: E402


class FakeTimelapseMediaService:
    def __init__(self):
        self.calls = []

    def list_frame_records(self, device_id, start_at=None, end_at=None, limit=100):
        self.calls.append((device_id, start_at, end_at, limit))
        return [
            {
                "camera_id": device_id,
                "captured_at": "2026-07-04T06:30:00",
                "relative_path": "timelapse_frames/camera-1/20260704/20260704_063000.jpg",
                "url": "/local/api/camera-images/timelapse_frames/camera-1/20260704/20260704_063000.jpg",
            }
        ]


class WebServerBasicUITest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.sensor_device_repository = SensorDeviceRepository()
        self.sensor_device_repository.device_repo_path = os.path.join(self.tmp_dir.name, ".device_list.json")
        self.sensor_device_repository.device_dict = {}
        self.sensor_device_repository.save()

        self.original_sensor_device_repository = web_server.sensor_device_repository
        web_server.sensor_device_repository = lambda: self.sensor_device_repository
        self.fake_timelapse_media_service = FakeTimelapseMediaService()
        self.original_timelapse_media_service = web_server.timelapse_media_service
        web_server.timelapse_media_service = lambda: self.fake_timelapse_media_service
        self.field_repository = FieldRepository()
        self.field_repository.field_repo_path = os.path.join(self.tmp_dir.name, ".fields.json")
        self.field_repository.fields = {}
        self.field_repository.save()
        self.original_field_repository = web_server.field_repository
        web_server.field_repository = lambda: self.field_repository
        self.client = web_server.app.test_client()

    def tearDown(self):
        web_server.sensor_device_repository = self.original_sensor_device_repository
        web_server.timelapse_media_service = self.original_timelapse_media_service
        web_server.field_repository = self.original_field_repository
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

    def test_camera_images_api_filters_by_date(self):
        response = self.client.get("/local/api/camera/camera-1/images?date=2026-07-04&limit=12")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body[0]["camera_id"], "camera-1")
        self.assertEqual(body[0]["captured_at"], "2026-07-04T06:30:00")
        device_id, start_at, end_at, limit = self.fake_timelapse_media_service.calls[-1]
        self.assertEqual(device_id, "camera-1")
        self.assertEqual(start_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-04 00:00:00")
        self.assertEqual(end_at.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-04 23:59:59")
        self.assertEqual(limit, 12)

    def test_field_create_form_stores_crop_context_and_policy(self):
        response = self.client.post(
            "/fields",
            data={
                "name": "試験ハウス",
                "crop": "トマト",
                "cultivar": "アイコ",
                "stage": "開花",
                "cultivation_method": "ハウス",
                "objective": "土壌水分を安定させる",
                "allowed_actions": ["watering", "fertigation"],
                "target_soil_moisture_min": "35",
                "target_soil_moisture_max": "65",
            },
        )

        self.assertEqual(response.status_code, 302)
        field = self.field_repository.list()[0]
        self.assertEqual(field["crop_profile"]["crop_name"], "トマト")
        self.assertEqual(field["crop_profile"]["cultivar"], "アイコ")
        self.assertEqual(field["cultivation_context"]["cultivation_method"], "ハウス")
        self.assertEqual(field["growth_targets"]["soil_moisture_percent"]["max"], 65.0)
        self.assertEqual(field["control_policy"]["allowed_actions"], ["watering", "fertigation"])

    def test_field_detail_renders_growth_context_and_action_candidates(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "判断テスト圃場",
                "crop": "トマト",
                "stage": "開花",
                "growth_targets": {"soil_moisture_percent": {"min": 35, "max": 65}},
                "control_policy": {"allowed_actions": ["watering"]},
            },
        )

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("生育の前提", html)
        self.assertIn("次の判断候補", html)
        self.assertIn("アクション計画の履歴", html)

    def test_field_list_renders_summary_cards(self):
        self.field_repository.upsert(
            None,
            {
                "name": "一覧テスト圃場",
                "crop": "キュウリ",
                "stage": "育苗",
                "growth_targets": {"soil_moisture_percent": {"min": 45, "max": 75}},
                "control_policy": {"allowed_actions": ["watering", "misting"]},
            },
        )

        response = self.client.get("/fields")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("一覧テスト圃場", html)
        self.assertIn("土壌水分目標 45.0-75.0%", html)
        self.assertIn("噴霧", html)

    def test_field_detail_form_stores_monitoring_units_and_device_placement(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "設置先テスト圃場",
                "crop": "トマト",
                "stage": "開花",
                "device_ids": ["INADS-env"],
            },
        )

        response = self.client.post(
            f"/fields/{field['id']}",
            data={
                "name": "設置先テスト圃場",
                "crop": "トマト",
                "stage": "開花",
                "areas_text": "A区画,section,トマト,南側",
                "device_ids": "INADS-env",
                "camera_device_ids": "",
                "allowed_actions": ["watering"],
                "placement_device_id_0": "INADS-env",
                "placement_device_role_0": "environment",
                "placement_scope_type_0": "field",
                "placement_area_id_0": "",
                "placement_crop_name_0": "トマト",
                "placement_memo_0": "圃場代表値",
            },
        )

        self.assertEqual(response.status_code, 302)
        stored = self.field_repository.get(field["id"])
        self.assertEqual(stored["areas"][0]["name"], "A区画")
        self.assertEqual(stored["device_placements"][0]["device_role"], "environment")
        self.assertEqual(stored["device_placements"][0]["scope_type"], "field")
        self.assertEqual(stored["device_placements"][0]["memo"], "圃場代表値")

    def test_field_detail_renders_monitoring_units_and_device_placements(self):
        field = self.field_repository.upsert(
            None,
            {
                "name": "監視単位表示圃場",
                "crop": "イチゴ",
                "stage": "定植",
                "areas": [{"id": "bed-1", "name": "東ベッド", "area_type": "bed", "crop_name": "イチゴ"}],
                "device_ids": ["INADS-soi"],
                "device_placements": [
                    {"device_id": "INADS-soi", "device_role": "soil", "scope_type": "bed", "area_id": "bed-1"},
                ],
            },
        )

        response = self.client.get(f"/fields/{field['id']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("監視単位", html)
        self.assertIn("東ベッド", html)
        self.assertIn("デバイス設置先", html)
        self.assertIn("土壌センサー", html)


if __name__ == "__main__":
    unittest.main()
