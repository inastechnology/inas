import os
import tempfile
import unittest
from datetime import UTC, datetime

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

from ina_device_hub.soil_moisture_notification_task import SoilMoistureNotificationTask  # noqa: E402


class FakeMonitorService:
    def __init__(self):
        self.calls = []

    def evaluate_rules(self, devices, *, now):
        self.calls.append((devices, now))
        return True


class FakeDeviceRepository:
    def get_all(self):
        return {"soil-1": {"state": "active", "device_kind": "SOI"}}


class SoilMoistureNotificationTaskTest(unittest.TestCase):
    def test_run_once_evaluates_all_rules_with_registered_devices(self):
        monitor = FakeMonitorService()
        task = SoilMoistureNotificationTask(
            monitor_service=monitor,
            device_repository=FakeDeviceRepository(),
        )
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)

        changed = task.run_once(now)

        self.assertTrue(changed)
        self.assertEqual(monitor.calls, [({"soil-1": {"state": "active", "device_kind": "SOI"}}, now)])


if __name__ == "__main__":
    unittest.main()
