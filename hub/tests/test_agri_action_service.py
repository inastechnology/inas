import unittest

from ina_device_hub.agri_action_service import build_action_candidates


class AgriActionServiceTest(unittest.TestCase):
    def test_low_soil_moisture_builds_watering_candidate(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "crop": "トマト",
                    "stage": "開花",
                    "crop_profile": {"crop_name": "トマト", "growth_stage": "開花"},
                    "cultivation_context": {"cultivation_method": "ハウス"},
                    "areas": [{"id": "ridge-1", "name": "1番畝", "area_type": "ridge"}],
                    "device_placements": [{"device_id": "soi-1", "device_role": "soil", "scope_type": "ridge", "area_id": "ridge-1"}],
                    "growth_targets": {
                        "soil_moisture_percent": {"min": 40, "max": 70},
                    },
                    "control_policy": {
                        "objective": "過湿を避ける",
                        "autonomy_level": "manual_approval",
                        "allowed_actions": ["watering"],
                    },
                },
                "devices": [{"device_id": "wtr-1", "record": {"device_kind": "WTR"}}],
                "latest_sensor_values": [{"device_id": "soi-1", "values": {"soil_moisture_percent": 31.5}}],
            }
        )

        self.assertEqual(candidates[0]["action_type"], "watering")
        self.assertTrue(candidates[0]["can_execute_now"])
        self.assertEqual(candidates[0]["preconditions"]["crop_name"], "トマト")
        self.assertEqual(candidates[0]["preconditions"]["monitoring_units"][0]["name"], "1番畝")
        self.assertEqual(candidates[0]["evidence"]["current_value"], 31.5)

    def test_future_fertigation_candidate_is_not_executable_yet(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "crop_profile": {"crop_name": "イチゴ"},
                    "growth_targets": {
                        "soil_moisture_percent": {"min": 20, "max": 80},
                        "soil_ec_us_cm": {"min": 700, "max": 1200},
                    },
                    "control_policy": {
                        "autonomy_level": "manual_approval",
                        "allowed_actions": ["watering", "fertigation"],
                    },
                },
                "devices": [{"device_id": "env-1", "record": {"device_kind": "ENV"}}],
                "latest_sensor_values": [{"device_id": "env-1", "values": {"soil_ec_us_cm": 420}}],
            }
        )

        fertigation = next(item for item in candidates if item["action_type"] == "fertigation")
        self.assertFalse(fertigation["can_execute_now"])
        self.assertFalse(fertigation["support"]["supported"])
        self.assertIn("今後実装", fertigation["support"]["reason"])

    def test_wrs_device_supports_watering_candidate(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "crop_profile": {"crop_name": "イチゴ"},
                    "growth_targets": {"soil_moisture_percent": {"min": 40, "max": 70}},
                    "control_policy": {"allowed_actions": ["watering"], "autonomy_level": "manual_approval"},
                },
                "devices": [{"device_id": "wrs-1", "record": {"device_kind": "WRS"}}],
                "latest_sensor_values": [{"device_id": "wrs-1", "values": {"soil_moisture_percent": 30}}],
            }
        )

        self.assertEqual(candidates[0]["action_type"], "watering")
        self.assertTrue(candidates[0]["can_execute_now"])
        self.assertIn("WTR/WRS", candidates[0]["support"]["reason"])

    def test_no_gap_builds_observation_candidate(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "crop_profile": {"crop_name": "レタス"},
                    "growth_targets": {"soil_moisture_percent": {"min": 30, "max": 70}},
                    "control_policy": {"allowed_actions": ["watering"]},
                },
                "latest_sensor_values": [{"device_id": "soi-1", "values": {"last_soil_moisture": 50}}],
            }
        )

        self.assertEqual(candidates[0]["action_type"], "observation")


if __name__ == "__main__":
    unittest.main()
