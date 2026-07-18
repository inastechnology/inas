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
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")
os.environ["HUB_AUTH_MODE"] = "local"

from ina_device_hub import web_server  # noqa: E402


class FakeGrowthMonitoringService:
    def __init__(self):
        self.created = []

    def dashboard(self, field_id):
        return {
            "field": {"id": field_id, "name": "AI監視圃場"},
            "image_ai_configured": True,
            "sources": [
                {
                    "camera_id": "camera-1",
                    "camera_name": "garden",
                    "camera_placement_id": "camera-placement",
                    "camera_placement_name": "庭カメラ",
                    "space_name": "圃場全体",
                    "target_placement_ids": ["ridge-1"],
                    "monitored_areas": [{"id": "ridge-1", "name": "東側の畝", "preset": "ridge"}],
                    "plantings": [{"crop_label": "トマト", "placement_name": "東側の畝"}],
                    "latest_frame": None,
                    "latest_assessment": None,
                    "preview_url": "/camera/camera-1/preview",
                    "images_url": "/camera/camera-1/images",
                    "ready": True,
                    "blocking_reasons": [],
                }
            ],
            "assessments": [],
        }

    def list_assessments(self, field_id, camera_id="", limit=50):
        return [{"id": "assessment-1", "field_id": field_id, "camera_id": camera_id, "limit": limit}]

    def create_assessment(self, field_id, camera_id, created_by="", audience=None):
        self.created.append((field_id, camera_id, created_by, audience))
        return {"id": "assessment-new", "field_id": field_id, "camera_id": camera_id}


class CameraGrowthWebTest(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()
        self.service = FakeGrowthMonitoringService()

    def test_page_explains_image_transfer_and_exposes_camera_workflow(self):
        with patch.object(web_server, "camera_growth_monitoring_service", return_value=self.service):
            response = self.client.get("/fields/field-1/growth-monitoring")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("カメラ生育モニタリング", html)
        self.assertIn("設定済みの画像AIへ送信", html)
        self.assertIn("今の状態を撮影してAI評価", html)
        self.assertIn("garden", html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_list_and_create_assessment_api(self):
        preferences = {"preferences": {"cultivation_experience": "beginner"}}
        with (
            patch.object(web_server, "camera_growth_monitoring_service", return_value=self.service),
            patch.object(web_server, "effective_preferences", return_value=preferences),
            patch.object(web_server, "user_preference_repository", return_value=object()),
        ):
            listed = self.client.get("/local/api/fields/field-1/camera-growth-assessments?camera_id=camera-1&limit=8")
            created = self.client.post(
                "/local/api/fields/field-1/camera-growth-assessments",
                headers={"Cf-Access-Authenticated-User-Email": "worker@example.com"},
                json={"camera_id": "camera-1"},
            )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["items"][0]["limit"], 8)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["id"], "assessment-new")
        self.assertEqual(self.service.created[0][2], "worker@example.com")
        self.assertEqual(self.service.created[0][3]["experience_level"], "beginner")


if __name__ == "__main__":
    unittest.main()
