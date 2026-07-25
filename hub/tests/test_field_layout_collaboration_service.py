import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")

from ina_device_hub.field_layout_collaboration_service import (  # noqa: E402
    FieldLayoutCollaborationService,
    FieldLayoutCollaborationValidationError,
)


class MutableClock:
    def __init__(self):
        self.now = datetime(2026, 7, 23, 3, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


class FieldLayoutCollaborationServiceTest(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.service = FieldLayoutCollaborationService(presence_ttl_seconds=10, clock=self.clock)
        self.layout = {"revision": 4, "updated_at": "2026-07-23T02:59:00+00:00", "updated_by": "owner@example.com"}

    def test_room_keeps_tabs_separate_and_marks_current_participant(self):
        self.service.touch(
            "field-1",
            client_id="client-tab-a",
            actor_email="worker@example.com",
            active_space_id="space-a",
            selected_placement_id="ridge-a",
            state="editing",
            layout=self.layout,
        )

        snapshot = self.service.touch(
            "field-1",
            client_id="client-tab-b",
            actor_email="worker@example.com",
            active_space_id="space-b",
            state="viewing",
            layout=self.layout,
        )

        self.assertEqual(snapshot["layout"], self.layout)
        self.assertEqual([item["client_id"] for item in snapshot["participants"]], ["client-tab-a", "client-tab-b"])
        self.assertFalse(snapshot["participants"][0]["is_current"])
        self.assertTrue(snapshot["participants"][1]["is_current"])
        self.assertEqual(snapshot["participants"][0]["selected_placement_id"], "ridge-a")

    def test_presence_is_isolated_by_field_and_expires(self):
        self.service.touch("field-1", client_id="client-one", actor_email="one@example.com", layout=self.layout)
        self.service.touch("field-2", client_id="client-two", actor_email="two@example.com", layout={"revision": 2})

        self.assertEqual(len(self.service.snapshot("field-1")["participants"]), 1)
        self.assertEqual(len(self.service.snapshot("field-2")["participants"]), 1)

        self.clock.now += timedelta(seconds=11)

        self.assertEqual(self.service.snapshot("field-1")["participants"], [])
        self.assertEqual(self.service.snapshot("field-2")["participants"], [])

    def test_newer_layout_metadata_wins_and_leave_removes_tab(self):
        self.service.touch("field-1", client_id="client-one", actor_email="one@example.com", layout=self.layout)
        self.service.publish_layout("field-1", {"revision": 5, "updated_at": "later", "updated_by": "two@example.com"})
        self.service.publish_layout("field-1", {"revision": 3, "updated_at": "older", "updated_by": "old@example.com"})

        forged_snapshot = self.service.leave("field-1", "client-one", actor_email="other@example.com")
        snapshot = self.service.leave("field-1", "client-one", actor_email="one@example.com")

        self.assertEqual(len(forged_snapshot["participants"]), 1)
        self.assertEqual(snapshot["participants"], [])
        self.assertEqual(snapshot["layout"], {"revision": 5, "updated_at": "later", "updated_by": "two@example.com"})

    def test_rejects_invalid_client_and_state(self):
        with self.assertRaises(FieldLayoutCollaborationValidationError):
            self.service.touch("field-1", client_id="short", actor_email="one@example.com")
        with self.assertRaises(FieldLayoutCollaborationValidationError):
            self.service.touch("field-1", client_id="client-valid", actor_email="one@example.com", state="left")


if __name__ == "__main__":
    unittest.main()
