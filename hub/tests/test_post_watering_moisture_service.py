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
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.post_watering_moisture_service import (  # noqa: E402
    PostWateringMoistureService,
    PostWateringMoistureValidationError,
    analyze_moisture_window,
    post_watering_device_options,
    soil_moisture_sensor_options,
)


class FakeSettings:
    def __init__(self, rules=None):
        self.values = {"post_watering_moisture": {"rules": list(rules or [])}}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class FakeNotificationService:
    def __init__(self):
        self.alerts = []

    def notify_health_alert(self, alert_type, device_id, record, details):
        self.alerts.append((alert_type, device_id, record, details))


class FakeMeasurementRepository:
    def __init__(self):
        self.measurements = []

    def between_for_devices(self, device_ids, start_at, end_at, limit=5000, metric=None):
        start = datetime.fromisoformat(start_at)
        end = datetime.fromisoformat(end_at)
        return [
            item
            for item in self.measurements
            if item.get("device_id") in device_ids
            and (not metric or item.get("metric") == metric)
            and start <= datetime.fromisoformat(item["measured_at"]) < end
        ][:limit]


class PostWateringMoistureServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.settings = FakeSettings()
        self.notifications = FakeNotificationService()
        self.measurements = FakeMeasurementRepository()
        self.service = PostWateringMoistureService(
            settings_store=self.settings,
            notification_service=self.notifications,
            measurement_repository=self.measurements,
            state_path=os.path.join(self.tmp_dir.name, "state.json"),
        )
        self.devices = {
            "watering-1": {
                "name": "北畝の潅水機",
                "location": "1号ハウス",
                "state": "active",
                "device_kind": "WTR",
                "last_status": {"last_soil_moisture": 31},
            },
            "soil-1": {
                "name": "北畝の水分計",
                "location": "1号ハウス 北畝",
                "state": "active",
                "device_kind": "SOI",
                "last_status": {"soil_moisture_percent": 42},
            },
            "soil-2": {
                "name": "南畝の水分計",
                "location": "1号ハウス 南畝",
                "state": "active",
                "device_kind": "SOI",
                "last_status": {"soil_moisture_percent": 63},
            },
        }
        self.service.save_rule(
            {
                "sensor_device_id": "soil-1",
                "minimum_percent": 50,
                "window_days": 3,
                "enabled": True,
            },
            self.devices,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _set_points(self, now, values, *, first_offset_hours=1):
        window_start = now - timedelta(days=3) + timedelta(hours=first_offset_hours)
        step = (now - timedelta(hours=1) - window_start) / max(1, len(values) - 1)
        self.measurements.measurements = [
            {
                "device_id": "soil-1",
                "device_kind": "SOI",
                "measured_at": (window_start + step * index).isoformat(),
                "metric": "soil_moisture_percent",
                "value": value,
            }
            for index, value in enumerate(values)
        ]

    def test_complete_window_without_three_consecutive_reaches_notifies(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [38, 42, 51, 43, 41])

        changed = self.service.evaluate_rules(self.devices, now=now)

        self.assertTrue(changed)
        self.assertEqual(len(self.notifications.alerts), 1)
        alert_type, sensor_device_id, _record, details = self.notifications.alerts[0]
        self.assertEqual(alert_type, "post_watering_moisture_low")
        self.assertEqual(sensor_device_id, "soil-1")
        self.assertEqual(details["window_days"], 3)
        self.assertEqual(details["minimum_percent"], 50)
        self.assertEqual(self.service.state["soil-1"]["status"], "not_reached")

    def test_three_consecutive_values_at_threshold_complete_without_notification(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [40, 50, 52, 51, 45])

        self.service.evaluate_rules(self.devices, now=now)

        self.assertEqual(self.notifications.alerts, [])
        self.assertEqual(self.service.state["soil-1"]["status"], "reached")
        self.assertIsNotNone(self.service.state["soil-1"]["last_reached_at"])

    def test_incomplete_history_does_not_notify(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [35, 36, 37], first_offset_hours=60)

        self.service.evaluate_rules(self.devices, now=now)

        self.assertEqual(self.notifications.alerts, [])
        self.assertEqual(self.service.state["soil-1"]["status"], "insufficient_data")

    def test_unreached_state_renotifies_after_24_hours_only(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [35, 36, 37, 38])
        self.service.evaluate_rules(self.devices, now=now)
        self.service.evaluate_rules(self.devices, now=now + timedelta(hours=12))
        self.assertEqual(len(self.notifications.alerts), 1)

        later = now + timedelta(hours=24)
        self._set_points(later, [34, 35, 36, 37])
        self.service.evaluate_rules(self.devices, now=later)

        self.assertEqual(len(self.notifications.alerts), 2)

    def test_reaching_threshold_clears_notification_cycle(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [35, 36, 37, 38])
        self.service.evaluate_rules(self.devices, now=now)

        reached_at = now + timedelta(hours=1)
        self._set_points(reached_at, [40, 50, 51, 52])
        self.service.evaluate_rules(self.devices, now=reached_at)
        self.assertEqual(self.service.state["soil-1"]["status"], "reached")
        self.assertNotIn("last_notified_at", self.service.state["soil-1"])

        dry_again_at = reached_at + timedelta(days=3, hours=1)
        self._set_points(dry_again_at, [39, 40, 41, 42])
        self.service.evaluate_rules(self.devices, now=dry_again_at)
        self.assertEqual(len(self.notifications.alerts), 2)

    def test_process_status_evaluates_only_selected_sensor(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [35, 36, 37, 38])

        ignored = self.service.process_status(
            "soil-2",
            {**self.devices["soil-2"], "last_status_at": now.isoformat()},
            {"soil_moisture_percent": 63},
        )
        evaluated = self.service.process_status(
            "soil-1",
            {**self.devices["soil-1"], "last_status_at": now.isoformat()},
            {"soil_moisture_percent": 38},
        )

        self.assertFalse(ignored)
        self.assertTrue(evaluated)
        self.assertEqual(len(self.notifications.alerts), 1)

    def test_legacy_watering_rule_migrates_to_three_day_sensor_rule(self):
        settings = FakeSettings(
            [
                {
                    "watering_device_id": "watering-1",
                    "sensor_device_id": "soil-1",
                    "minimum_percent": 47,
                    "enabled": True,
                }
            ]
        )

        service = PostWateringMoistureService(
            settings_store=settings,
            notification_service=self.notifications,
            measurement_repository=self.measurements,
            state_path=os.path.join(self.tmp_dir.name, "legacy-state.json"),
        )

        self.assertEqual(
            service.list_rules(),
            [{"sensor_device_id": "soil-1", "minimum_percent": 47.0, "window_days": 3, "enabled": True}],
        )

    def test_rule_validation_requires_active_sensor_and_one_to_fourteen_days(self):
        with self.assertRaises(PostWateringMoistureValidationError):
            self.service.save_rule(
                {"sensor_device_id": "missing", "minimum_percent": 50, "window_days": 3, "enabled": True},
                self.devices,
            )
        with self.assertRaises(PostWateringMoistureValidationError):
            self.service.save_rule(
                {"sensor_device_id": "soil-1", "minimum_percent": 50, "window_days": 15, "enabled": True},
                self.devices,
            )

    def test_delete_rule_removes_saved_rule_and_monitor_state(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        self._set_points(now, [35, 36, 37, 38])
        self.service.evaluate_rules(self.devices, now=now)

        deleted = self.service.delete_rule("soil-1")

        self.assertEqual(deleted["sensor_device_id"], "soil-1")
        self.assertEqual(self.service.list_rules(), [])
        self.assertNotIn("soil-1", self.service.state)

    def test_delete_rule_rejects_missing_rule(self):
        with self.assertRaises(PostWateringMoistureValidationError):
            self.service.delete_rule("missing")

    def test_sensor_options_keep_multiple_sensors_and_latest_values(self):
        options = soil_moisture_sensor_options(self.devices)

        by_id = {option["id"]: option for option in options}
        self.assertIn("soil-1", by_id)
        self.assertIn("soil-2", by_id)
        self.assertEqual(by_id["soil-1"]["latest_percent"], 42)
        self.assertEqual(by_id["soil-2"]["latest_percent"], 63)

    def test_watering_options_remain_available_for_legacy_callers(self):
        option_ids = {item["id"] for item in post_watering_device_options(self.devices)}
        self.assertEqual(option_ids, {"watering-1"})

    def test_analyzer_ignores_invalid_values(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
        result = analyze_moisture_window(
            [{"metric": "soil_moisture_percent", "measured_at": now.isoformat(), "value": 101}],
            {"minimum_percent": 50, "window_days": 3},
            now=now,
        )
        self.assertEqual(result["status"], "insufficient_data")


if __name__ == "__main__":
    unittest.main()
