import unittest
from pathlib import Path

from ina_device_hub.plant_action_catalog import (
    normalize_plant_action_type,
    plant_action_type,
    plant_action_types,
)
from ina_device_hub.plant_work_catalog import ACTION_WORK_PLAN_DEFAULTS, default_action_work_plan


class PlantActionCatalogTest(unittest.TestCase):
    def test_codes_are_unique_and_major_illustrations_exist(self):
        action_types = plant_action_types()
        codes = [item["code"] for item in action_types]
        self.assertEqual(len(codes), len(set(codes)))

        package_root = Path(__file__).resolve().parents[1] / "src" / "ina_device_hub"
        illustrated = {item["code"]: item["illustration_url"] for item in action_types if item["illustration_url"]}
        self.assertEqual(
            set(illustrated),
            {"fertilization", "pest_control", "pruning", "pollination", "gibberellin_treatment", "harvest", "watering"},
        )
        for url in illustrated.values():
            self.assertTrue((package_root / url.lstrip("/")).is_file(), url)

    def test_aliases_normalize_to_canonical_codes(self):
        self.assertEqual(normalize_plant_action_type("追肥"), "fertilization")
        self.assertEqual(normalize_plant_action_type("灌水"), "watering")
        self.assertEqual(normalize_plant_action_type("gibberellin-application"), "gibberellin_treatment")
        self.assertEqual(normalize_plant_action_type("ジベ処理"), "gibberellin_treatment")
        self.assertEqual(plant_action_type("ジベレリン")["illustration_url"], "/static/plant-actions/gibberellin-treatment.webp")

    def test_every_action_type_has_a_concrete_default_work_plan(self):
        codes = {item["code"] for item in plant_action_types()}

        self.assertEqual(codes, set(ACTION_WORK_PLAN_DEFAULTS))
        for code in codes:
            plan = default_action_work_plan(code)
            self.assertTrue(plan["targets"], code)
            self.assertTrue(plan["start_conditions"], code)
            self.assertTrue(plan["skip_conditions"], code)
            self.assertTrue(plan["checkpoints"], code)
            self.assertTrue(plan["method_options"], code)
            self.assertTrue(plan["completion_criteria"], code)
            for method in plan["method_options"]:
                self.assertTrue(method["purpose"], f"{code}:{method['id']}")
                self.assertTrue(method["application_method"], f"{code}:{method['id']}")
                self.assertTrue(method["procedure_steps"], f"{code}:{method['id']}")
                self.assertTrue(method["completion_checks"], f"{code}:{method['id']}")
                self.assertTrue(method["precautions"], f"{code}:{method['id']}")
                self.assertIn(method["frequency"]["mode"], {"one_time", "as_needed", "interval", "seasonal", "continuous"})
                self.assertTrue(method["frequency"]["basis"], f"{code}:{method['id']}")


if __name__ == "__main__":
    unittest.main()
