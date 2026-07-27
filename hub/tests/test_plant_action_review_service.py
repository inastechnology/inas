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

from ina_device_hub.plant_action_review_service import (  # noqa: E402
    PlantActionAuthorizationError,
    PlantActionReviewService,
)
from ina_device_hub.plant_management_repository import PlantManagementRepository  # noqa: E402


class FakeMediaService:
    def __init__(self):
        self.calls = []

    def upload_images(self, field_id, occurred_on, images):
        self.calls.append((field_id, occurred_on, list(images)))
        return []


class FakeFieldRepository:
    def __init__(self):
        self.events = []

    def get(self, field_id):
        return {"id": field_id, "location": {"prefecture": "山梨県"}}

    def add_event(self, field_id, value):
        event = {"id": f"event-{len(self.events) + 1}", "field_id": field_id, **value}
        self.events.append(event)
        return event


class FakeAIContentService:
    def __init__(self):
        self.contexts = []

    def generate_follow_up_tasks(self, context):
        self.contexts.append(context)
        return {"source": "test", "decision_summary": "承認後に生成", "actions": []}


class PlantActionReviewServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = PlantManagementRepository()
        self.repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.repository.data = {
            "schema_version": 2,
            "plantings": {},
            "calendars": {},
            "generation_tasks": [],
            "feedback": [],
            "work_logs": [],
            "questions": [],
            "fertilizer_applications": [],
            "fertilizer_materials": [],
        }
        self.repository.save()
        self.field_repository = FakeFieldRepository()
        self.media_service = FakeMediaService()
        self.ai_service = FakeAIContentService()
        self.service = PlantActionReviewService(
            plant_repository=self.repository,
            field_repository=self.field_repository,
            media_service=self.media_service,
            ai_content_service=self.ai_service,
        )
        self.planting = self.repository.create_planting(
            "field-1",
            {
                "space_id": "root",
                "placement_id": "ridge-1",
                "placement_name": "畝1",
                "crop_name": "トマト",
                "planted_on": "2026-06-01",
                "plant_count": 10,
            },
        )
        self.calendar = self.repository.create_calendar(
            self.planting["id"],
            [
                {
                    "action_type": "watering",
                    "title": "株元を潅水",
                    "window_start": "2026-07-20",
                    "window_end": "2026-07-21",
                    "rule_id": "watering-rule",
                    "assigned_to": "worker@example.com",
                }
            ],
            task_rules=[
                {
                    "rule_id": "watering-rule",
                    "action_type": "watering",
                    "title": "株元を潅水",
                    "recurrence_type": "interval_after_completion",
                    "anchor": "completion_date",
                }
            ],
        )
        self.action_id = self.calendar["actions"][0]["id"]
        self.repository.update_action(self.planting["id"], self.action_id, {"status": "in_progress"})

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_operator_cannot_submit_another_workers_assignment(self):
        with self.assertRaises(PlantActionAuthorizationError):
            self.service.submit_completion(
                self.planting["id"],
                self.action_id,
                {"performed_on": "2026-07-20", "rating": 4, "work_details": {}},
                [],
                actor_email="other@example.com",
                actor_role="operator",
            )

        self.assertEqual(self.repository.get_calendar(self.planting["id"])["actions"][0]["status"], "in_progress")
        self.assertEqual(self.media_service.calls, [])

    def test_approval_is_the_boundary_for_history_and_follow_up(self):
        submitted = self.service.submit_completion(
            self.planting["id"],
            self.action_id,
            {"performed_on": "2026-07-20", "rating": 4, "note": "2L", "work_details": {}},
            [],
            actor_email="worker@example.com",
            actor_role="operator",
        )

        self.assertEqual(submitted["action"]["status"], "awaiting_review")
        self.assertEqual(self.field_repository.events, [])
        self.assertEqual(self.ai_service.contexts, [])
        with self.assertRaises(PlantActionAuthorizationError):
            self.service.review_completion(
                self.planting["id"],
                self.action_id,
                {"decision": "approved", "note": ""},
                reviewer_email="worker@example.com",
                reviewer_role="operator",
            )

        reviewed = self.service.review_completion(
            self.planting["id"],
            self.action_id,
            {"decision": "approved", "note": "写真と量を確認"},
            reviewer_email="manager@example.com",
            reviewer_role="admin",
            audience={"experience_level": "standard"},
        )

        self.assertEqual(reviewed["action"]["status"], "completed")
        self.assertEqual(reviewed["work_log"]["reviewed_by"], "manager@example.com")
        self.assertEqual(len(self.field_repository.events), 1)
        self.assertEqual(self.field_repository.events[0]["source_work_log_id"], submitted["work_log"]["id"])
        self.assertEqual(len(self.ai_service.contexts), 1)
        self.assertEqual(self.ai_service.contexts[0]["recent_work_logs"][0]["review_status"], "approved")

    def test_rejection_returns_work_without_creating_official_history(self):
        submitted = self.service.submit_completion(
            self.planting["id"],
            self.action_id,
            {"performed_on": "2026-07-20", "rating": 3, "note": "作業後写真なし", "work_details": {}},
            [],
            actor_email="worker@example.com",
            actor_role="operator",
        )

        reviewed = self.service.review_completion(
            self.planting["id"],
            self.action_id,
            {"decision": "rejected", "note": "作業後の写真を追加してください"},
            reviewer_email="manager@example.com",
            reviewer_role="admin",
        )

        self.assertEqual(reviewed["action"]["status"], "in_progress")
        self.assertEqual(reviewed["work_log"]["id"], submitted["work_log"]["id"])
        self.assertEqual(reviewed["work_log"]["review_status"], "rejected")
        self.assertEqual(reviewed["work_log"]["review_note"], "作業後の写真を追加してください")
        self.assertEqual(reviewed["event"], None)
        self.assertEqual(reviewed["follow_up"]["actions"], [])
        self.assertEqual(self.repository.recent_work_logs(self.planting["id"]), [])
        self.assertEqual(self.field_repository.events, [])
        self.assertEqual(self.ai_service.contexts, [])


if __name__ == "__main__":
    unittest.main()
