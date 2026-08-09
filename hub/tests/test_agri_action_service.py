import unittest
from copy import deepcopy

from ina_device_hub.agri_action_service import build_action_candidates, build_operation_readiness


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
                "devices": [
                    {
                        "device_id": "wtr-1",
                        "record": {"device_kind": "WTR"},
                        "placement": {"target_placement_ids": ["ridge-1"]},
                    }
                ],
                "latest_sensor_values": [{"device_id": "soi-1", "values": {"soil_moisture_percent": 31.5}}],
            }
        )

        self.assertEqual(candidates[0]["action_type"], "watering")
        self.assertFalse(candidates[0]["can_execute_now"])
        self.assertTrue(candidates[0]["support"]["supported"])
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
                "devices": [
                    {
                        "device_id": "wrs-1",
                        "record": {"device_kind": "WRS"},
                        "placement": {"target_placement_ids": ["ridge-a"]},
                    }
                ],
                "latest_sensor_values": [{"device_id": "wrs-1", "values": {"soil_moisture_percent": 30}}],
            }
        )

        self.assertEqual(candidates[0]["action_type"], "watering")
        self.assertFalse(candidates[0]["can_execute_now"])
        self.assertIn("WTR/WRS", candidates[0]["support"]["reason"])

    def test_unrouted_watering_device_is_not_reported_as_controllable(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "growth_targets": {"soil_moisture_percent": {"min": 40, "max": 70}},
                    "control_policy": {"allowed_actions": ["watering"], "autonomy_level": "manual_approval"},
                },
                "devices": [{"device_id": "wtr-1", "record": {"device_kind": "WTR"}}],
                "latest_sensor_values": [{"device_id": "soi-1", "values": {"soil_moisture_percent": 30}}],
            }
        )

        self.assertFalse(candidates[0]["support"]["supported"])
        self.assertIn("水やりルート", candidates[0]["support"]["reason"])

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

    def test_field_action_candidates_use_dashboard_median(self):
        candidates = build_action_candidates(
            {
                "field": {
                    "growth_targets": {"soil_moisture_percent": {"min": 30, "max": 70}},
                    "control_policy": {"allowed_actions": ["watering"]},
                },
                "latest_sensor_values": [
                    {"device_id": "soi-1", "values": {"soil_moisture_percent": 80}},
                    {"device_id": "soi-2", "values": {"soil_moisture_percent": 20}},
                ],
                "dashboard": {
                    "metrics": [
                        {
                            "metric": "soil_moisture_percent",
                            "value": 50,
                            "source_count": 2,
                        }
                    ]
                },
            }
        )

        self.assertEqual(candidates[0]["action_type"], "observation")
        self.assertEqual(candidates[0]["evidence"]["latest_values"]["soil_moisture_percent"], 50)

    def test_watering_readiness_requires_layout_route_to_planting(self):
        action = {
            "action_type": "watering",
            "title": "根域へ水やり",
            "work_plan": {"start_conditions": ["土が乾いた"], "skip_conditions": [], "completion_criteria": []},
        }
        planting = {"placement_id": "ridge-a"}
        field = {"id": "field-a", "control_policy": {"allowed_actions": ["watering"], "autonomy_level": "manual_approval"}}
        devices = {"WTR-001": {"name": "潅水機A", "device_kind": "WTR", "state": "active"}}
        unrelated_layout = {
            "spaces": [
                {
                    "placements": [
                        {
                            "id": "watering-a",
                            "name": "点滴制御盤",
                            "binding": {"device_id": "WTR-001", "resource_id": "irr1", "target_placement_ids": ["ridge-b"]},
                        }
                    ]
                }
            ]
        }

        unrelated = build_operation_readiness(action, planting, field, unrelated_layout, devices)
        self.assertEqual(unrelated["executor_mode"], "human")
        self.assertEqual(unrelated["executor_candidates"], [])
        self.assertIn("水やりルート", unrelated["dispatch_reason"])

        related_layout = deepcopy(unrelated_layout)
        related_layout["spaces"][0]["placements"][0]["binding"]["target_placement_ids"] = ["ridge-a"]
        related = build_operation_readiness(action, planting, field, related_layout, devices)
        self.assertEqual(related["executor_mode"], "device_assisted")
        self.assertEqual(related["executor_candidates"][0]["resource_id"], "irr1")
        self.assertEqual(related["executor_candidates"][0]["channel_mask"], 1)
        self.assertFalse(related["can_dispatch"])
        self.assertIn("実行プロトコル", related["dispatch_reason"])

    def test_pruning_and_harvest_stay_human_guided(self):
        for action_type in ("pruning", "harvest", "repotting"):
            with self.subTest(action_type=action_type):
                readiness = build_operation_readiness(
                    {"action_type": action_type, "title": action_type, "work_plan": {}},
                    {"placement_id": "ridge-a"},
                    {"id": "field-a"},
                    {"spaces": []},
                    {},
                )
                self.assertEqual(readiness["executor_mode"], "human")
                self.assertEqual(readiness["automation_stage"], "guidance_only")
                self.assertFalse(readiness["can_dispatch"])
                self.assertTrue(readiness["decision_checks"])


if __name__ == "__main__":
    unittest.main()
