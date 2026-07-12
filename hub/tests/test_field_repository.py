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
os.environ.setdefault("MQTT_BROKER_USERNAME", "x")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "x")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.field_repository import FieldRepository  # noqa: E402


class FieldRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = FieldRepository()
        self.repository.field_repo_path = os.path.join(self.tmp_dir.name, ".fields.json")
        self.repository.fields = {}
        self.repository.save()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_upsert_stores_crop_context_targets_and_policy(self):
        field = self.repository.upsert(
            None,
            {
                "name": "南ハウス",
                "crop_profile": {
                    "crop_name": "トマト",
                    "cultivar": "アイコ",
                    "growth_stage": "開花",
                    "transplant_date": "2026-06-01",
                },
                "growth_targets": {
                    "soil_moisture_percent": {"min": "42", "max": "68"},
                    "soil_ec_us_cm": {"min": "700", "max": "1400"},
                },
                "cultivation_context": {
                    "cultivation_method": "ハウス",
                    "soil_type": "培養土",
                    "plant_count": "18",
                },
                "areas": [{"id": "ridge-1", "name": "1番畝", "area_type": "ridge", "crop_name": "トマト"}],
                "device_ids": ["INADS-env", "INADS-soi"],
                "device_placements": [
                    {"device_id": "INADS-env", "device_role": "environment", "scope_type": "field"},
                    {"device_id": "INADS-soi", "device_role": "soil", "scope_type": "ridge", "area_id": "ridge-1"},
                ],
                "control_policy": {
                    "objective": "過湿を避けつつ水分を安定させる",
                    "autonomy_level": "manual_approval",
                    "allowed_actions": ["watering", "fertigation"],
                    "max_watering_sec_per_day": "360",
                },
                "knowledge_context": {
                    "research_queries": ["トマト 開花期 EC"],
                    "external_reference_urls": ["https://example.com/reference"],
                },
            },
        )

        self.assertEqual(field["crop"], "トマト")
        self.assertEqual(field["stage"], "開花")
        self.assertEqual(field["crop_profile"]["cultivar"], "アイコ")
        self.assertEqual(field["growth_targets"]["soil_moisture_percent"]["min"], 42.0)
        self.assertEqual(field["growth_targets"]["soil_ec_us_cm"]["max"], 1400.0)
        self.assertEqual(field["cultivation_context"]["plant_count"], 18)
        self.assertEqual(field["areas"][0]["name"], "1番畝")
        self.assertEqual(field["areas"][0]["area_type"], "ridge")
        self.assertEqual(field["device_placements"][0]["scope_type"], "field")
        self.assertEqual(field["device_placements"][1]["area_id"], "ridge-1")
        self.assertEqual(field["control_policy"]["autonomy_level"], "manual_approval")
        self.assertEqual(field["control_policy"]["allowed_actions"], ["watering", "fertigation"])
        self.assertEqual(field["knowledge_context"]["research_queries"], ["トマト 開花期 EC"])

    def test_add_action_plan_records_scientific_action_hypothesis(self):
        field = self.repository.upsert(None, {"name": "北畑", "crop": "ナス", "stage": "活着"})

        plan = self.repository.add_action_plan(
            field["id"],
            {
                "action_type": "watering",
                "status": "proposed",
                "title": "土壌水分低下のため灌水",
                "scientific_reason": "目標下限を下回った",
                "preconditions": {"crop_name": "ナス"},
                "control_payload": {"duration_sec": 120},
                "human_evaluation": "朝に確認してから実施",
            },
        )

        stored = self.repository.get(field["id"])
        self.assertEqual(plan["action_type"], "watering")
        self.assertEqual(stored["action_plans"][0]["title"], "土壌水分低下のため灌水")
        self.assertEqual(stored["action_plans"][0]["preconditions"]["crop_name"], "ナス")


if __name__ == "__main__":
    unittest.main()
