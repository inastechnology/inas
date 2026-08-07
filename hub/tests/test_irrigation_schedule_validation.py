import unittest

from ina_device_hub.device_config_repository import DeviceConfigValidationError, validate_device_config
from ina_device_hub.irrigation_schedule_validation import find_irrigation_schedule_spacing_conflicts


def _schedule(hour, minute, duration_sec, *, enabled=True, frequency=None):
    return {
        "hour": hour,
        "minute": minute,
        "duration_sec": duration_sec,
        "channel_mask": 1,
        "enabled": enabled,
        "frequency": frequency or {"mode": "daily"},
    }


def _base_config(schedules):
    return {
        "ntp_server": "pool.ntp.org",
        "timezone_offset_sec": 32400,
        "moisture_threshold": 40,
        "schedules": schedules,
    }


class IrrigationScheduleValidationTest(unittest.TestCase):
    def test_standard_watering_requires_duration_plus_five_minutes(self):
        too_close = _base_config([_schedule(6, 0, 600), _schedule(6, 14, 60)])
        conflict = find_irrigation_schedule_spacing_conflicts(too_close, "WTR")[0]

        self.assertEqual(conflict["source_time"], "06:00")
        self.assertEqual(conflict["next_time"], "06:14")
        self.assertEqual(conflict["operation_duration_sec"], 600)
        self.assertEqual(conflict["required_gap_sec"], 900)
        self.assertEqual(conflict["shortage_sec"], 60)
        self.assertEqual(conflict["suggested_time"], "06:15")

        exact_minimum = _base_config([_schedule(6, 0, 600), _schedule(6, 15, 60)])
        self.assertEqual(find_irrigation_schedule_spacing_conflicts(exact_minimum, "WTR"), [])

    def test_spacing_check_handles_next_day_and_ignores_disabled_schedules(self):
        config = _base_config(
            [
                _schedule(0, 9, 60),
                _schedule(23, 55, 600),
                _schedule(23, 59, 3600, enabled=False),
            ]
        )

        conflict = find_irrigation_schedule_spacing_conflicts(config, "WRS")[0]

        self.assertEqual(conflict["source_time"], "23:55")
        self.assertEqual(conflict["next_time"], "00:09")
        self.assertEqual(conflict["next_day_offset"], 1)
        self.assertEqual(conflict["suggested_time"], "00:10")
        self.assertEqual(conflict["suggested_day_offset"], 1)

    def test_weekday_schedules_that_do_not_run_together_are_not_rejected(self):
        config = _base_config(
            [
                _schedule(6, 0, 3600, frequency={"mode": "weekdays", "weekdays": [1]}),
                _schedule(6, 30, 60, frequency={"mode": "weekdays", "weekdays": [2]}),
            ]
        )

        self.assertEqual(find_irrigation_schedule_spacing_conflicts(config, "WTR"), [])

    def test_pulse_mode_counts_off_intervals_in_operation_duration(self):
        config = {
            **_base_config([_schedule(6, 0, 1), _schedule(6, 12, 1)]),
            "watering_pattern": {"enabled": True, "on_sec": 120, "off_sec": 60, "repeat_count": 3},
        }

        conflict = find_irrigation_schedule_spacing_conflicts(config, "WTR")[0]

        self.assertEqual(conflict["duration_source"], "watering_pattern")
        self.assertEqual(conflict["operation_duration_sec"], 480)
        self.assertEqual(conflict["required_gap_sec"], 780)
        self.assertEqual(conflict["shortage_sec"], 60)

    def test_fgt_timed_outputs_use_the_full_sequential_program(self):
        config = {
            **_base_config([_schedule(6, 0, 1), _schedule(6, 9, 1)]),
            "fgt": {
                "timed_outputs": {
                    "enabled": True,
                    "water_inlet": {"on_sec": 60, "off_sec": 30, "repeat_count": 2},
                    "irrigation": {"on_sec": 120, "off_sec": 0, "repeat_count": 1},
                }
            },
        }

        conflict = find_irrigation_schedule_spacing_conflicts(config, "FGT")[0]

        self.assertEqual(conflict["duration_source"], "fgt_timed_outputs")
        self.assertEqual(conflict["operation_duration_sec"], 270)
        self.assertEqual(conflict["required_gap_sec"], 570)
        self.assertEqual(conflict["suggested_time"], "06:10")

    def test_validation_blocks_irrigation_config_but_not_non_irrigation_device(self):
        config = _base_config([_schedule(6, 0, 600), _schedule(6, 14, 60)])

        with self.assertRaises(DeviceConfigValidationError) as raised:
            validate_device_config(config, device_kind="WTR")

        self.assertEqual(raised.exception.code, "irrigation_schedule_spacing")
        self.assertEqual(raised.exception.details[0]["shortage_sec"], 60)
        self.assertIn("安全余裕 5分", str(raised.exception))
        validate_device_config(config, device_kind="ENV")


if __name__ == "__main__":
    unittest.main()
