import unittest
from pathlib import Path

from ina_device_hub.plant_action_catalog import (
    normalize_plant_action_type,
    plant_action_type,
    plant_action_types,
)


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


if __name__ == "__main__":
    unittest.main()
