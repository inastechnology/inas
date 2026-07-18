import os
import tempfile
import unittest
from datetime import datetime

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

from ina_device_hub.camera_growth_assessment_repository import CameraGrowthAssessmentRepository  # noqa: E402
from ina_device_hub.camera_growth_monitoring_service import (  # noqa: E402
    CameraGrowthAIUnavailableError,
    CameraGrowthMonitoringService,
)

JPEG = b"\xff\xd8camera-frame\xff\xd9"


class FakeFieldRepository:
    def get(self, field_id):
        if field_id != "field-1":
            return None
        return {"id": field_id, "name": "果樹園", "location": {"environment_type": "outdoor"}}


class FakeLayoutRepository:
    def get(self, field_id, field_name=""):
        del field_id, field_name
        return {
            "spaces": [
                {
                    "id": "space-root",
                    "name": "圃場全体",
                    "placements": [
                        {
                            "id": "greenhouse-1",
                            "name": "第一ハウス",
                            "preset": "greenhouse",
                            "child_space_id": "space-house",
                            "binding": None,
                        },
                        {
                            "id": "camera-placement",
                            "name": "庭カメラ",
                            "preset": "camera",
                            "binding": {
                                "device_id": "camera-1",
                                "resource_type": "camera",
                                "target_placement_ids": ["greenhouse-1"],
                            },
                        },
                    ],
                },
                {
                    "id": "space-house",
                    "name": "第一ハウス内",
                    "placements": [
                        {"id": "ridge-1", "name": "東側の畝", "preset": "ridge", "binding": None},
                        {
                            "id": "sensor-placement",
                            "name": "環境センサー",
                            "preset": "sensor",
                            "binding": {
                                "device_id": "sensor-1",
                                "resource_type": "sensor",
                                "target_placement_ids": ["ridge-1"],
                            },
                        },
                    ],
                },
            ]
        }


class FakePlantRepository:
    def field_bundle(self, field_id, **kwargs):
        del field_id, kwargs
        return {
            "plantings": [
                {
                    "id": "planting-1",
                    "field_id": "field-1",
                    "space_id": "space-house",
                    "placement_id": "ridge-1",
                    "placement_name": "東側の畝",
                    "crop_name": "トマト",
                    "cultivar": "桃太郎",
                    "crop_category": "vegetable",
                    "tree_age_years": None,
                    "planted_on": "2026-06-01",
                    "plant_count": 6,
                    "cultivation_method": "露地",
                    "conditions": {},
                    "growth_targets": {},
                    "status": "active",
                }
            ]
        }


class FakeCameraService:
    def get(self, camera_id):
        if camera_id != "camera-1":
            return None
        return {
            "id": camera_id,
            "name": "garden",
            "preview_url": f"/camera/{camera_id}/preview",
            "images_url": f"/camera/{camera_id}/images",
        }


class FakeConnector:
    def take_picture(self, camera_id, timeout_seconds=20):
        self.call = (camera_id, timeout_seconds)
        return JPEG


class FakeMediaService:
    def __init__(self, directory):
        self.directory = directory
        self.previous_path = os.path.join(directory, "previous.jpg")
        with open(self.previous_path, "wb") as file:
            file.write(JPEG)
        self.saved = []

    def list_frame_records(self, camera_id, start_at=None, end_at=None, limit=100):
        del limit
        frame = {
            "camera_id": camera_id,
            "captured_at": "2026-07-18T08:00:00",
            "relative_path": "timelapse_frames/camera-1/20260718/20260718_080000.jpg",
            "url": "/local/api/camera-images/timelapse_frames/camera-1/20260718/20260718_080000.jpg",
        }
        return [frame] if start_at is None or end_at is not None else []

    def resolve_frame_path(self, relative_path):
        return self.previous_path if relative_path else None

    def save_frame(self, camera_id, image_bytes, captured_at=None):
        self.saved.append((camera_id, image_bytes, captured_at))
        return os.path.join(self.directory, "current.jpg")

    def get_frame_relative_path(self, camera_id, captured_at):
        return f"timelapse_frames/{camera_id}/{captured_at:%Y%m%d}/{captured_at:%Y%m%d_%H%M%S}.jpg"


class FakeMeasurementRepository:
    def latest_for_device(self, device_id, limit=20):
        del limit
        return [{"device_id": device_id, "metric": "soil_moisture_percent", "value": 42, "unit": "%", "measured_at": "2026-07-19T07:50:00"}]


class FakeAIService:
    def __init__(self, configured=True):
        self.configured = configured
        self.calls = []

    def image_analysis_available(self):
        return self.configured

    def assess_plant_growth(self, context, images):
        self.calls.append((context, images))
        return {
            "overall_status": "attention",
            "confidence": 0.78,
            "summary": "葉量は増えていますが、一部の葉色を現物で確認してください。",
            "observations": [{"category": "leaf", "finding": "画面右側の葉が淡く見える", "evidence": "右上部", "severity": "watch"}],
            "comparison": {"available": True, "summary": "葉量が増加", "changes": ["株幅が広がった"]},
            "concerns": [],
            "suggested_actions": [
                {
                    "title": "葉の表裏を確認",
                    "action_type": "pest_control",
                    "priority": "recommended",
                    "timing": "本日中",
                    "reason": "葉色差が見えるため",
                    "checks_before_action": [],
                    "instructions": ["葉の表裏を観察する"],
                    "skip_conditions": [],
                }
            ],
            "limitations": ["照明条件の影響を除外できない"],
        }


class CameraGrowthMonitoringServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.assessment_repository = CameraGrowthAssessmentRepository()
        self.assessment_repository.repository_path = os.path.join(self.tmp_dir.name, ".assessments.json")
        self.assessment_repository.data = {"schema_version": 1, "assessments": []}
        self.assessment_repository.save()
        self.media_service = FakeMediaService(self.tmp_dir.name)
        self.ai_service = FakeAIService()
        self.service = CameraGrowthMonitoringService(
            field_repo=FakeFieldRepository(),
            layout_repo=FakeLayoutRepository(),
            plant_repo=FakePlantRepository(),
            camera_service=FakeCameraService(),
            connector=FakeConnector(),
            media_service=self.media_service,
            measurement_repo=FakeMeasurementRepository(),
            ai_service=self.ai_service,
            assessment_repo=self.assessment_repository,
            now_provider=lambda: datetime(2026, 7, 19, 8, 30, 0),
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_dashboard_resolves_planting_inside_monitored_child_space(self):
        dashboard = self.service.dashboard("field-1")

        self.assertTrue(dashboard["sources"][0]["ready"])
        self.assertEqual(dashboard["sources"][0]["plantings"][0]["crop_label"], "トマト / 桃太郎")
        self.assertIn("ridge-1", dashboard["sources"][0]["_expanded_target_ids"])

    def test_capture_compare_analyze_and_persist_evidence_based_suggestions(self):
        result = self.service.create_assessment(
            "field-1",
            "camera-1",
            created_by="worker@example.com",
            audience={"experience_level": "beginner"},
        )

        self.assertEqual(result["result"]["overall_status"], "attention")
        self.assertTrue(result["result"]["comparison"]["available"])
        self.assertTrue(result["result"]["needs_human_review"])
        action = result["result"]["suggested_actions"][0]
        self.assertIn("製品ラベル", " ".join(action["checks_before_action"]))
        self.assertEqual(len(self.media_service.saved), 1)
        context, images = self.ai_service.calls[0]
        self.assertEqual(context["plantings"][0]["crop_name"], "トマト")
        self.assertEqual(context["sensor_readings"][0]["value"], 42)
        self.assertEqual(context["audience"]["experience_level"], "beginner")
        self.assertEqual(len(images), 2)
        self.assertNotIn("bytes", str(result))

    def test_missing_image_ai_is_a_blocking_reason(self):
        self.service.ai_service = FakeAIService(configured=False)

        dashboard = self.service.dashboard("field-1")
        self.assertEqual(dashboard["sources"][0]["blocking_reasons"][-1]["code"], "ai_not_configured")
        with self.assertRaises(CameraGrowthAIUnavailableError):
            self.service.create_assessment("field-1", "camera-1", created_by="worker@example.com")


class CameraGrowthAssessmentRepositoryTest(unittest.TestCase):
    def test_repository_filters_and_does_not_copy_request_image_data(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = CameraGrowthAssessmentRepository()
            repository.repository_path = os.path.join(directory, ".assessments.json")
            repository.data = {"schema_version": 1, "assessments": []}
            repository.save()
            repository.create(
                {
                    "field_id": "field-1",
                    "camera_id": "camera-1",
                    "current_frame": {"relative_path": "timelapse_frames/a.jpg", "captured_at": "2026-07-19T08:00:00"},
                    "context_snapshot": {"field": {"name": "圃場"}, "image_bytes": "secret-image-data"},
                    "result": {"overall_status": "healthy"},
                }
            )

            records = repository.list(field_id="field-1", camera_id="camera-1")

            self.assertEqual(len(records), 1)
            self.assertNotIn("image_bytes", records[0]["context_snapshot"])
            self.assertNotIn("secret-image-data", str(records[0]))


if __name__ == "__main__":
    unittest.main()
