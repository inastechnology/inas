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
        self.calls = []

    def list_notification_actions(self, today=None, lead_days=7):
        self.calls.append({"today": today, "lead_days": lead_days})
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


def _item(action_id, timing_state=None, start="2026-07-18", end="2026-07-25"):
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
            "window_end": end,
            "priority": "recommended",
        },
    }


class PlantTaskNotificationTaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.plants = _PlantRepository([_item("existing", "due")])
        self.notifications = _NotificationService()
        self.preferences = {
            "plant_task_notify_new": True,
            "plant_task_reminder_days_before": 7,
            "plant_task_notify_on_start_day": True,
            "plant_task_notify_during_window": True,
        }
        self.task = PlantTaskNotificationTask(
            plant_repository=self.plants,
            field_repo=_FieldRepository(),
            notification_service=self.notifications,
            state_path=os.path.join(self.tmp_dir.name, "state.json"),
            settings_provider=lambda: self.preferences,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_existing_actions_are_seeded_then_new_and_due_actions_are_grouped(self):
        jst = ZoneInfo("Asia/Tokyo")

        self.assertTrue(self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst)))
        first = self.notifications.digests[-1]
        self.assertEqual([item["action"]["id"] for item in first["due"]], ["existing"])
        self.assertFalse(first["due"][0]["is_new"])
        self.assertEqual(first["reminder"]["days_before"], 7)
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

    def test_advance_reminder_is_sent_once_on_the_exact_configured_day(self):
        jst = ZoneInfo("Asia/Tokyo")
        self.plants.inventory = [_item("future", start="2026-07-25", end="2026-07-30")]

        self.assertTrue(self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst)))
        self.assertEqual([item["action"]["id"] for item in self.notifications.digests[-1]["upcoming"]], ["future"])
        digest_count = len(self.notifications.digests)

        self.assertFalse(self.task.run_once(datetime(2026, 7, 19, 4, tzinfo=jst)))
        self.assertEqual(len(self.notifications.digests), digest_count)
        self.assertEqual(self.plants.calls[-1]["lead_days"], 7)

    def test_start_day_and_during_window_can_be_controlled_separately(self):
        jst = ZoneInfo("Asia/Tokyo")
        self.preferences["plant_task_notify_on_start_day"] = False
        self.preferences["plant_task_notify_during_window"] = True

        self.assertFalse(self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst)))
        self.assertTrue(self.task.run_once(datetime(2026, 7, 19, 4, tzinfo=jst)))
        self.assertEqual([item["action"]["id"] for item in self.notifications.digests[-1]["due"]], ["existing"])

    def test_zero_days_disables_only_the_advance_reminder(self):
        jst = ZoneInfo("Asia/Tokyo")
        self.preferences["plant_task_reminder_days_before"] = 0
        self.plants.inventory = [_item("future", start="2026-07-25", end="2026-07-30")]

        self.assertFalse(self.task.run_once(datetime(2026, 7, 18, 4, tzinfo=jst)))
        self.assertEqual(self.plants.calls[-1]["lead_days"], 0)

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
