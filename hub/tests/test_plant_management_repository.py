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

from ina_device_hub.plant_management_repository import (  # noqa: E402
    PlantManagementRepository,
    PlantManagementValidationError,
)


class PlantManagementRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = PlantManagementRepository()
        self.repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.repository.data = {
            "schema_version": 1,
            "plantings": {},
            "calendars": {},
            "feedback": [],
            "work_logs": [],
            "questions": [],
        }
        self.repository.save()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_blueberry(self):
        return self.repository.create_planting(
            "field-1",
            {
                "space_id": "space-root",
                "placement_id": "pot-a",
                "placement_name": "鉢A",
                "crop_name": "ブルーベリー",
                "cultivar": "ティフブルー",
                "planted_on": "2026-07-14",
                "plant_count": 1,
                "conditions": {"environment": "屋外", "soil_or_substrate": "酸性培養土"},
                "growth_targets": {"soil_moisture_percent": {"min": 35, "max": 65}},
            },
        )

    def _create_calendar(self, planting_id):
        return self.repository.create_calendar(
            planting_id,
            [
                {
                    "action_type": "fertilization",
                    "title": "活着後の追肥判断",
                    "priority": "should",
                    "window_start": "2026-07-20",
                    "window_end": "2026-07-31",
                    "reason": "新梢の状態を確認して追肥量を決めるため",
                    "tags": ["追肥", "活着"],
                    "rule_id": "rule-fertilization",
                },
                {
                    "action_type": "pest_control",
                    "title": "葉の病害虫確認",
                    "priority": "recommended",
                    "window_start": "2026-07-14",
                    "window_end": "2026-07-21",
                    "reason": "早期発見のため",
                    "tags": ["防除", "観察"],
                },
            ],
            {"source": "fallback", "context_snapshot": {"crop_name": "ブルーベリー"}},
            care_profile={"summary": "ブルーベリーの栽培基準", "fertilization": {"strategy": "葉色とECで判断"}},
            task_rules=[
                {
                    "rule_id": "rule-fertilization",
                    "action_type": "fertilization",
                    "title": "追肥要否を確認",
                    "recurrence_type": "interval_after_completion",
                    "anchor": "completion_date",
                    "interval_days": {"min": 30, "preferred": 45, "max": 60},
                    "active_months": list(range(1, 13)),
                }
            ],
        )

    def test_create_planting_and_calendar_returns_due_suggestions(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])

        bundle = self.repository.field_bundle("field-1", today="2026-07-14")

        self.assertEqual(calendar["revision"], 1)
        self.assertEqual(calendar["care_profile"]["summary"], "ブルーベリーの栽培基準")
        self.assertEqual(calendar["task_rules"][0]["interval_days"]["preferred"], 45)
        self.assertEqual(bundle["plantings"][0]["placement_name"], "鉢A")
        action_types = {item["code"]: item for item in bundle["action_types"]}
        self.assertEqual(action_types["fertilization"]["illustration_url"], "/static/plant-actions/fertilization.webp")
        self.assertEqual(action_types["gibberellin_treatment"]["label"], "ジベレリン処理")
        self.assertEqual(bundle["plantings"][0]["growth_targets"]["soil_moisture_percent"]["max"], 65.0)
        self.assertEqual(bundle["suggestions"][0]["timing_state"], "due")
        self.assertEqual(bundle["suggestions"][0]["action"]["title"], "葉の病害虫確認")

    def test_rejects_second_active_planting_at_same_placement(self):
        self._create_blueberry()

        with self.assertRaises(PlantManagementValidationError):
            self._create_blueberry()

    def test_action_edit_records_reusable_feedback(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]

        updated = self.repository.update_action(
            planting["id"],
            action_id,
            {"priority": "recommended", "reason": "樹勢が強いため少量から判断する"},
            use_as_guidance=True,
        )

        self.assertEqual(updated["source"], "user_edited")
        self.assertEqual(updated["priority"], "recommended")
        guidance = self.repository.guidance_examples("ブルーベリー")
        self.assertEqual(len(guidance), 1)
        self.assertEqual(guidance[0]["changes"]["priority"]["before"], "should")

    def test_complete_action_stores_selected_work_date(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]

        attachment = {
            "id": "image-1",
            "storage": "r2",
            "object_key": "field-records/field-1/2026-07-23/image-1.png",
            "content_type": "image/png",
            "size_bytes": 120,
            "original_filename": "leaf.png",
            "url": "/local/api/fields/field-1/record-images/image-1",
        }
        work_log = self.repository.complete_action(
            planting["id"],
            action_id,
            "2026-07-23",
            "少量施肥",
            rating=4,
            attachments=[attachment],
        )
        bundle = self.repository.field_bundle("field-1", today="2026-07-24")

        self.assertEqual(work_log["performed_on"], "2026-07-23")
        self.assertEqual(work_log["rating"], 4)
        self.assertEqual(work_log["attachments"][0]["storage"], "r2")
        self.assertEqual(bundle["work_logs"][0]["note"], "少量施肥")
        self.assertEqual(bundle["calendars"][planting["id"]]["actions"][0]["status"], "completed")

    def test_update_planting_targets_validates_range(self):
        planting = self._create_blueberry()

        updated = self.repository.update_planting(
            planting["id"],
            {"growth_targets": {"soil_ph": {"min": 4.5, "max": 5.5}}},
        )

        self.assertEqual(updated["growth_targets"]["soil_ph"], {"min": 4.5, "max": 5.5})
        with self.assertRaises(PlantManagementValidationError):
            self.repository.update_planting(
                planting["id"],
                {"growth_targets": {"soil_moisture_percent": {"min": 80, "max": 20}}},
            )

    def test_crop_category_and_tree_age_are_updated_together(self):
        planting = self._create_blueberry()

        fruit_tree = self.repository.update_planting(planting["id"], {"crop_category": "fruit_tree", "tree_age_years": 4})
        vegetable = self.repository.update_planting(planting["id"], {"crop_category": "vegetable"})

        self.assertEqual(fruit_tree["tree_age_years"], 4)
        self.assertIsNone(vegetable["tree_age_years"])

    def test_replace_calendar_preserves_completed_actions_and_replaces_future_plan(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        self.repository.complete_action(planting["id"], calendar["actions"][0]["id"], "2026-07-23", "実施")

        replaced = self.repository.replace_calendar(
            planting["id"],
            [
                {
                    "action_type": "observation",
                    "title": "新しい観察計画",
                    "priority": "recommended",
                    "window_start": "2026-08-01",
                    "window_end": "2026-08-07",
                }
            ],
            {"source": "llm"},
        )

        self.assertEqual(replaced["revision"], 3)
        self.assertEqual([action["status"] for action in replaced["actions"]], ["completed", "planned"])
        self.assertEqual(replaced["actions"][1]["title"], "新しい観察計画")

    def test_append_generated_actions_deduplicates_same_rule_and_window(self):
        planting = self._create_blueberry()
        self._create_calendar(planting["id"])
        next_action = {
            "rule_id": "rule-fertilization",
            "action_type": "fertilization",
            "title": "追肥要否を確認",
            "priority": "recommended",
            "window_start": "2026-09-01",
            "window_end": "2026-09-10",
        }

        first = self.repository.append_generated_actions(planting["id"], [next_action])
        second = self.repository.append_generated_actions(planting["id"], [next_action])

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        calendar = self.repository.get_calendar(planting["id"])
        self.assertEqual(sum(action["window_start"] == "2026-09-01" for action in calendar["actions"]), 1)


if __name__ == "__main__":
    unittest.main()
