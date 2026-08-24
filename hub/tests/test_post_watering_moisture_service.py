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
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.post_watering_moisture_service import (  # noqa: E402
    PostWateringMoistureService,
    PostWateringMoistureValidationError,
    post_watering_device_options,
    soil_moisture_sensor_options,
)


class FakeSettings:
    def __init__(self):
        self.values = {"post_watering_moisture": {"rules": []}}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class FakeNotificationService:
    def __init__(self):
        self.alerts = []

    def notify_health_alert(self, alert_type, device_id, record, details):
        self.alerts.append((alert_type, device_id, record, details))


class PostWateringMoistureServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.settings = FakeSettings()
        self.notifications = FakeNotificationService()
        self.service = PostWateringMoistureService(
            settings_store=self.settings,
            notification_service=self.notifications,
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
                "watering_device_id": "watering-1",
                "sensor_device_id": "soil-1",
                "minimum_percent": 50,
                "enabled": True,
            },
            self.devices,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_selected_sensor_below_minimum_notifies_once_per_watering(self):
        self.service.process_status(
            "watering-1",
            {**self.devices["watering-1"], "last_status_at": "2026-08-24T01:00:00+00:00"},
            {"seq": 1, "watering_started": True, "last_soil_moisture": 31},
        )
        sensor_record = {**self.devices["soil-1"], "last_status_at": "2026-08-24T01:05:00+00:00"}

        first_changed = self.service.process_status("soil-1", sensor_record, {"soil_moisture_percent": 42})
        second_changed = self.service.process_status(
            "soil-1",
            {**sensor_record, "last_status_at": "2026-08-24T01:10:00+00:00"},
            {"soil_moisture_percent": 40},
        )

        self.assertTrue(first_changed)
        self.assertFalse(second_changed)
        self.assertEqual(len(self.notifications.alerts), 1)
        alert_type, watering_device_id, _record, details = self.notifications.alerts[0]
        self.assertEqual(alert_type, "post_watering_moisture_low")
        self.assertEqual(watering_device_id, "watering-1")
        self.assertEqual(details["sensor_device_id"], "soil-1")
        self.assertEqual(details["measured_percent"], 42)
        self.assertEqual(details["minimum_percent"], 50)

    def test_value_at_or_above_minimum_completes_without_notification(self):
        self.service.process_status(
            "watering-1",
            {**self.devices["watering-1"], "last_status_at": "2026-08-24T02:00:00+00:00"},
            {"seq": 2, "watering_started": True},
        )

        changed = self.service.process_status(
            "soil-1",
            {**self.devices["soil-1"], "last_status_at": "2026-08-24T02:05:00+00:00"},
            {"soil_moisture_percent": 50},
        )

        self.assertTrue(changed)
        self.assertEqual(self.notifications.alerts, [])
        self.assertEqual(self.service.state["watering-1"]["status"], "ok")

    def test_watering_device_pre_watering_value_is_not_used_as_post_value(self):
        self.service.save_rule(
            {
                "watering_device_id": "watering-1",
                "sensor_device_id": "watering-1",
                "minimum_percent": 50,
                "enabled": True,
            },
            self.devices,
        )

        self.service.process_status(
            "watering-1",
            {**self.devices["watering-1"], "last_status_at": "2026-08-24T03:00:00+00:00"},
            {"seq": 3, "watering_started": True, "last_soil_moisture": 20},
        )

        self.assertEqual(self.notifications.alerts, [])
        self.assertEqual(self.service.state["watering-1"]["status"], "pending")

        self.service.process_status(
            "watering-1",
            {**self.devices["watering-1"], "last_status_at": "2026-08-24T03:05:00+00:00"},
            {
                "seq": 4,
                "watering_started": False,
                "soil_rs485_ok": False,
                "soil_moisture_percent": 0,
                "last_soil_moisture": 44,
            },
        )

        self.assertEqual(len(self.notifications.alerts), 1)
        self.assertEqual(self.notifications.alerts[0][3]["measured_percent"], 44)

    def test_wrs_explicit_after_value_is_checked_in_same_status(self):
        wrs = {
            "name": "RS485潅水機",
            "location": "2号ハウス",
            "state": "active",
            "device_kind": "WRS",
        }
        self.devices["wrs-1"] = wrs
        self.service.save_rule(
            {
                "watering_device_id": "wrs-1",
                "sensor_device_id": "wrs-1",
                "minimum_percent": 55,
                "enabled": True,
            },
            self.devices,
        )

        self.service.process_status(
            "wrs-1",
            {**wrs, "last_status_at": "2026-08-24T04:00:00+00:00"},
            {
                "seq": 1,
                "watering_started": True,
                "watering_completed": True,
                "soil_moisture_after_watering": 49.5,
                "soil_moisture_percent": 49.5,
            },
        )

        self.assertEqual(len(self.notifications.alerts), 1)
        self.assertEqual(self.notifications.alerts[0][1], "wrs-1")
        self.assertEqual(self.notifications.alerts[0][3]["measured_percent"], 49.5)

    def test_rule_validation_requires_active_capable_devices(self):
        with self.assertRaises(PostWateringMoistureValidationError):
            self.service.save_rule(
                {
                    "watering_device_id": "watering-1",
                    "sensor_device_id": "missing",
                    "minimum_percent": 50,
                    "enabled": True,
                },
                self.devices,
            )
        with self.assertRaises(PostWateringMoistureValidationError):
            self.service.save_rule(
                {
                    "watering_device_id": "watering-1",
                    "sensor_device_id": "soil-1",
                    "minimum_percent": 101,
                    "enabled": True,
                },
                self.devices,
            )

    def test_sensor_options_keep_multiple_sensors_and_latest_values(self):
        options = soil_moisture_sensor_options(self.devices)

        by_id = {option["id"]: option for option in options}
        self.assertIn("soil-1", by_id)
        self.assertIn("soil-2", by_id)
        self.assertEqual(by_id["soil-1"]["latest_percent"], 42)
        self.assertEqual(by_id["soil-2"]["latest_percent"], 63)

    def test_watering_options_exclude_non_watering_devices_with_schedules(self):
        devices = {
            **self.devices,
            "camera-1": {
                "name": "定点カメラ",
                "state": "active",
                "device_kind": "CAM",
                "config": {"schedules": [{"hour": 6}]},
            },
        }

        option_ids = {item["id"] for item in post_watering_device_options(devices)}

        self.assertEqual(option_ids, {"watering-1"})


if __name__ == "__main__":
    unittest.main()
