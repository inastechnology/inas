import os
import tempfile
import threading
import unittest
from datetime import datetime

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")

from ina_device_hub.timelapse_media_service import TimelapseMediaService  # noqa: E402


class TimelapseMediaServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.service = TimelapseMediaService.__new__(TimelapseMediaService)
        self.service.local_storage_base_dir = self.tmp_dir.name
        self.service.storage_connector = None
        self.service._video_lock = threading.Lock()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write(self, relative_path, content=b"media"):
        path = os.path.join(self.tmp_dir.name, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file:
            file.write(content)
        return path

    def test_recent_video_reuses_output_for_latest_frame(self):
        camera_id = "INACD-camera"
        self._write(f"timelapse_frames/{camera_id}/20260726/20260726_080000.jpg")
        self._write(f"timelapse_frames/{camera_id}/20260726/20260726_083000.jpg")
        self._write(f"timelapse_videos/{camera_id}/20260726/20260726_083000.mp4")

        record = self.service.ensure_recent_video(
            camera_id,
            start_at=datetime(2026, 7, 26, 0, 0),
            end_at=datetime(2026, 7, 26, 9, 0),
        )

        self.assertEqual(record["frame_count"], 2)
        self.assertEqual(record["captured_at"], "2026-07-26T08:30:00")
        self.assertEqual(
            record["url"],
            f"/local/api/camera-videos/timelapse_videos/{camera_id}/20260726/20260726_083000.mp4",
        )

    def test_video_listing_and_resolution_stay_inside_timelapse_directory(self):
        video_path = self._write("timelapse_videos/INACD-camera/20260726/20260726_083000.mp4")

        records = self.service.list_video_records("INACD-camera", limit=1)

        self.assertEqual(records[0]["captured_at"], "2026-07-26T08:30:00")
        self.assertEqual(self.service.resolve_video_path(records[0]["relative_path"]), video_path)
        self.assertIsNone(self.service.resolve_video_path("../secret.mp4"))
        self.assertIsNone(self.service.resolve_video_path("timelapse_frames/INACD-camera/frame.mp4"))


if __name__ == "__main__":
    unittest.main()
