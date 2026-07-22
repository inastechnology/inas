import os
import tempfile
import threading
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

    def test_two_repository_instances_keep_both_concurrent_creates(self):
        second_repository = FieldRepository()
        second_repository.field_repo_path = self.repository.field_repo_path
        barrier = threading.Barrier(2)
        errors = []

        def create(repository, name):
            barrier.wait()
            try:
                repository.upsert(None, {"name": name})
            except Exception as error:  # pragma: no cover - asserted below
                errors.append(error)

        threads = [
            threading.Thread(target=create, args=(self.repository, "圃場A")),
            threading.Thread(target=create, args=(second_repository, "圃場B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.repository.load()
        self.assertEqual(errors, [])
        self.assertEqual({field["name"] for field in self.repository.list()}, {"圃場A", "圃場B"})

    def test_upsert_stores_crop_context_targets_and_policy(self):
        field = self.repository.upsert(
            None,
            {
                "name": "南ハウス",
                "location": {
                    "prefecture": "長野県",
                    "municipality": "伊那市",
                    "locality": "西箕輪",
                    "environment_type": "greenhouse",
                },
                "crop_profile": {
                    "crop_name": "トマト",
                    "cultivar": "アイコ",
                    "growth_stage": "開花",
                    "transplant_date": "2026-06-01",
                },
                "growth_targets": {
                    "air_temperature_c": {"min": "16", "max": "30"},
                    "soil_moisture_percent": {"min": "42", "max": "68"},
                    "soil_temperature_c": {"min": "14", "max": "26"},
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
        self.assertEqual(field["location"]["prefecture"], "長野県")
        self.assertEqual(field["location"]["municipality"], "伊那市")
        self.assertEqual(field["location"]["environment_type"], "greenhouse")
        self.assertEqual(field["stage"], "開花")
        self.assertEqual(field["crop_profile"]["cultivar"], "アイコ")
        self.assertEqual(field["growth_targets"]["soil_moisture_percent"]["min"], 42.0)
        self.assertEqual(field["growth_targets"]["air_temperature_c"]["max"], 30.0)
        self.assertEqual(field["growth_targets"]["soil_temperature_c"]["min"], 14.0)
        self.assertEqual(field["growth_targets"]["soil_ec_us_cm"]["max"], 1400.0)
        self.assertEqual(field["cultivation_context"]["plant_count"], 18)
        self.assertEqual(field["areas"][0]["name"], "1番畝")
        self.assertEqual(field["areas"][0]["area_type"], "ridge")
        self.assertEqual(field["device_placements"][0]["scope_type"], "field")
        self.assertEqual(field["device_placements"][1]["area_id"], "ridge-1")
        self.assertEqual(field["control_policy"]["autonomy_level"], "manual_approval")
        self.assertEqual(field["control_policy"]["allowed_actions"], ["watering", "fertigation"])
        self.assertEqual(field["knowledge_context"]["research_queries"], ["トマト 開花期 EC"])

    def test_invalid_field_environment_is_normalized_to_unset(self):
        field = self.repository.upsert(
            None,
            {"name": "環境テスト", "location": {"prefecture": "長野県", "environment_type": "unknown"}},
        )

        self.assertEqual(field["location"]["environment_type"], "")

    def test_search_filters_and_paginates_fields(self):
        for index in range(5):
            self.repository.upsert(
                f"ina-{index}",
                {
                    "name": f"伊那圃場 {index}",
                    "location": {
                        "prefecture": "長野県",
                        "municipality": "伊那市",
                        "environment_type": "outdoor" if index < 4 else "greenhouse",
                    },
                },
            )
        self.repository.upsert(
            "matsumoto",
            {
                "name": "松本ハウス",
                "location": {"prefecture": "長野県", "municipality": "松本市", "environment_type": "greenhouse"},
            },
        )

        first = self.repository.search(query="伊那", prefecture="長野県", environment_type="outdoor", page=1, page_size=2)
        second = self.repository.search(query="伊那", prefecture="長野県", environment_type="outdoor", page=2, page_size=2)

        self.assertEqual(first["total"], 4)
        self.assertEqual(first["page_count"], 2)
        self.assertEqual([field["id"] for field in first["items"]], ["ina-0", "ina-1"])
        self.assertEqual([field["id"] for field in second["items"]], ["ina-2", "ina-3"])

    def test_search_clamps_page_and_page_size(self):
        self.repository.upsert("field-1", {"name": "北圃場"})

        result = self.repository.search(page=999, page_size=1000)

        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 100)
        self.assertEqual(result["items"][0]["id"], "field-1")

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

    def test_add_event_normalizes_multiple_manual_record_values(self):
        field = self.repository.upsert(None, {"name": "手入力圃場"})

        event = self.repository.add_event(
            field["id"],
            {
                "event_type": "daily_record",
                "occurred_at": "2026-07-18T07:15",
                "target_placement_id": "pot-a",
                "target_name": "鉢A",
                "record_values": [
                    {"key": "watering_duration_min", "value": "15"},
                    {"key": "soil_ec_us_cm", "value": "820.5"},
                ],
            },
        )

        self.assertEqual(event["record_values"][0]["label"], "潅水時間")
        self.assertEqual(event["record_values"][0]["value"], 15)
        self.assertEqual(event["record_values"][1]["value"], 820.5)
        self.assertEqual(event["target_name"], "鉢A")

        with self.assertRaisesRegex(ValueError, "unsupported record item"):
            self.repository.add_event(field["id"], {"record_values": [{"key": "unknown", "value": "1"}]})

    def test_search_records_filters_normalized_text_kind_date_and_pages(self):
        field = self.repository.upsert(None, {"name": "記録検索圃場"})
        self.repository.add_event(
            field["id"],
            {
                "event_type": "watering",
                "occurred_at": "2026-07-15T07:00",
                "title": "鉢Aを潅水",
                "target_name": "ブルーベリー鉢A",
                "description": "10分間実施",
                "tags": ["朝作業"],
            },
        )
        self.repository.add_event(
            field["id"],
            {"event_type": "fertilizer", "occurred_at": "2026-07-16T08:00", "title": "液肥を施用"},
        )
        self.repository.add_note(field["id"], {"category": "observation", "text": "葉色を確認", "tags": ["ブルーベリー"]})

        watering = self.repository.search_records(field["id"], query="灌 水 ブルーベリー", kinds=["watering"])
        first_page = self.repository.search_records(field["id"], page=1, page_size=2)
        second_page = self.repository.search_records(field["id"], page=2, page_size=2)
        dated = self.repository.search_records(field["id"], date_from="2026-07-16", kinds=["fertilizer"])

        self.assertEqual(watering["total"], 1)
        self.assertEqual(watering["items"][0]["target_name"], "ブルーベリー鉢A")
        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["items"]), 2)
        self.assertEqual(len(second_page["items"]), 1)
        self.assertEqual(dated["items"][0]["title"], "液肥を施用")


if __name__ == "__main__":
    unittest.main()
