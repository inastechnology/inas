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

from ina_device_hub.health_monitor_task import HealthMonitorTask  # noqa: E402


class FakeDeviceRepository:
    def __init__(self, devices):
        self.devices = devices

    def get_all(self):
        return self.devices


class FakeNotificationService:
    def __init__(self):
        self.alerts = []

    def notify_health_alert(self, alert_type, device_id, record, details):
        self.alerts.append((alert_type, device_id, details))


class HealthMonitorTaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.notification_service = FakeNotificationService()
        self.task = HealthMonitorTask(notification_service=self.notification_service)
        self.task.state_path = os.path.join(self.tmp_dir.name, ".health_monitor_state.json")
        self.task.state = {}
        self.task.settings = {
            "device_offline_after_hours": 12,
            "watering_missing_after_days": 2,
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_offline_alert_is_not_repeated_until_recovered(self):
        self.task.device_repository = FakeDeviceRepository(
            {
                "device-1": {
                    "device_id": "device-1",
                    "state": "active",
                    "last_seen_at": "2026-07-03T00:00:00+00:00",
                    "device_kind": "SNS",
                    "status_history": [],
                }
            }
        )

        self.task.run_once(datetime(2026, 7, 3, 13, 0, tzinfo=UTC))
        self.task.run_once(datetime(2026, 7, 3, 14, 0, tzinfo=UTC))

        self.assertEqual(len(self.notification_service.alerts), 1)
        self.assertEqual(self.notification_service.alerts[0][0], "device_offline")

        self.task.device_repository = FakeDeviceRepository(
            {
                "device-1": {
                    "device_id": "device-1",
                    "state": "active",
                    "last_seen_at": "2026-07-03T13:30:00+00:00",
                    "device_kind": "SNS",
                    "status_history": [],
                }
            }
        )
        self.task.run_once(datetime(2026, 7, 3, 14, 0, tzinfo=UTC))

        self.assertNotIn("device-1", self.task.state)

    def test_watering_missing_uses_last_watering_started_status(self):
        self.task.device_repository = FakeDeviceRepository(
            {
                "device-2": {
                    "device_id": "device-2",
                    "state": "active",
                    "first_seen_at": "2026-07-01T00:00:00+00:00",
                    "last_seen_at": "2026-07-04T00:00:00+00:00",
                    "device_kind": "WTR",
                    "status_history": [
                        {
                            "received_at": "2026-07-01T00:00:00+00:00",
                            "payload": {"watering_started": True},
                        }
                    ],
                }
            }
        )

        self.task.run_once(datetime(2026, 7, 4, 0, 0, tzinfo=UTC))

        self.assertEqual(len(self.notification_service.alerts), 1)
        self.assertEqual(self.notification_service.alerts[0][0], "watering_missing")


if __name__ == "__main__":
    unittest.main()
