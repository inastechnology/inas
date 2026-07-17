import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")

from ina_device_hub.plant_task_notification_task import PlantTaskNotificationTask  # noqa: E402


class _PlantRepository:
    def __init__(self, inventory):
        self.inventory = inventory

    def list_notification_actions(self, today=None, lead_days=7):
        del today, lead_days
        return list(self.inventory)


class _FieldRepository:
    def list(self):
        return [{"id": "field-1", "name": "西条圃場1"}]


class _NotificationService:
    def __init__(self):
        self.digests = []
        self.succeeds = True

    def notify_plant_task_digest(self, digest):
        self.digests.append(digest)
        return self.succeeds


def _item(action_id, timing_state, start="2026-07-18"):
    return {
        "field_id": "field-1",
        "planting_id": "plant-1",
        "crop_name": "ライチ",
        "cultivar": "ジャカパット",
        "placement_name": "植木鉢1",
        "timing_state": timing_state,
        "action": {
            "id": action_id,
            "title": f"作業 {action_id}",
            "window_start": start,
            "window_end": "2026-07-25",
            "priority": "recommended",
        },
    }


class PlantTaskNotificationTaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.plants = _PlantRepository([_item("existing", "due")])
        self.notifications = _NotificationService()
        self.task = PlantTaskNotificationTask(
            plant_repository=self.plants,
            field_repo=_FieldRepository(),
            notification_service=self.notifications,
            state_path=os.path.join(self.tmp_dir.name, "state.json"),
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_existing_actions_are_seeded_then_new_and_due_actions_are_grouped(self):
        jst = ZoneInfo("Asia/Tokyo")

        self.assertTrue(self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst)))
        first = self.notifications.digests[-1]
        self.assertEqual([item["action"]["id"] for item in first["due"]], ["existing"])
        self.assertFalse(first["due"][0]["is_new"])
        self.assertFalse(self.task.run_once(datetime(2026, 7, 18, 5, tzinfo=jst)))

        self.plants.inventory.append(_item("winter", None, start="2026-11-01"))
        self.assertTrue(self.task.run_once(datetime(2026, 7, 19, 4, tzinfo=jst)))
        second = self.notifications.digests[-1]
        self.assertEqual([item["action"]["id"] for item in second["new"]], ["winter"])
        self.assertTrue(second["new"][0]["is_new"])

        self.assertTrue(self.task.run_once(datetime(2026, 7, 20, 4, tzinfo=jst)))
        third = self.notifications.digests[-1]
        self.assertEqual([item["action"]["id"] for item in third["due"]], ["existing"])
        self.assertEqual(third["new"], [])

    def test_failed_delivery_keeps_new_action_pending(self):
        jst = ZoneInfo("Asia/Tokyo")
        self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst))
        self.plants.inventory.append(_item("new", None, start="2026-11-01"))
        self.notifications.succeeds = False

        self.assertFalse(self.task.run_once(datetime(2026, 7, 19, 4, tzinfo=jst)))
        self.notifications.succeeds = True
        self.assertTrue(self.task.run_once(datetime(2026, 7, 20, 4, tzinfo=jst)))
        self.assertEqual(self.notifications.digests[-1]["new"][0]["action"]["id"], "new")

    def test_start_registers_four_am_tokyo_cron_job(self):
        with patch("ina_device_hub.plant_task_notification_task.threading.Thread") as thread:
            self.task.start()

        jobs = self.task.scheduler.get_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertIn("hour='4'", str(jobs[0].trigger))
        self.assertIn("Asia/Tokyo", str(jobs[0].trigger.timezone))
        thread.return_value.start.assert_called_once_with()
