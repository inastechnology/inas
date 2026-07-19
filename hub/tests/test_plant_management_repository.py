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
    PlantManagementConflictError,
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
        self.assertEqual(calendar["actions"][0]["required_people"], 1)
        self.assertEqual(calendar["actions"][0]["estimated_minutes"], 30)

    def test_fertilizer_history_is_scoped_to_substrate_and_survives_planting(self):
        planting = self._create_blueberry()
        application = self.repository.create_fertilizer_application(
            planting["id"],
            {
                "applied_on": "2026-07-14",
                "material_kind": "cattle_manure",
                "material_name": "牛ふん堆肥",
                "amount_kg": 20,
                "nutrient_percent": {"n": 2, "p2o5": 1, "k2o": 1.5, "mgo": 0.5},
                "annual_available_percent": 10,
                "effect_years": 2,
                "start_delay_days": 0,
                "analysis_source": "製品分析表",
            },
        )

        context = self.repository.fertilizer_effect_context(planting["id"], as_of="2026-07-14")
        bundle = self.repository.field_bundle("field-1")

        self.assertEqual(application["placement_id"], "pot-a")
        self.assertEqual(context["effect_summary"]["nutrients"]["n"]["applied_kg"], 0.4)
        self.assertEqual(context["effect_summary"]["nutrients"]["n"]["remaining_kg"], 0.08)
        self.assertEqual(context["effect_summary"]["nutrients"]["mgo"]["remaining_kg"], 0.02)
        self.assertEqual(bundle["fertilizer_applications"][0]["id"], application["id"])

    def test_fertilizer_history_requires_nutrient_analysis(self):
        planting = self._create_blueberry()

        with self.assertRaises(PlantManagementValidationError):
            self.repository.create_fertilizer_application(
                planting["id"],
                {
                    "applied_on": "2026-07-14",
                    "material_name": "成分不明堆肥",
                    "amount_kg": 20,
                    "nutrient_percent": {"n": 0, "p2o5": 0, "k2o": 0},
                    "annual_available_percent": 10,
                    "effect_years": 1,
                },
            )

    def test_suggestions_start_seven_days_before_work_window(self):
        planting = self._create_blueberry()
        self._create_calendar(planting["id"])

        eight_days_before = self.repository.list_suggestions("field-1", today="2026-07-12")
        seven_days_before = self.repository.list_suggestions("field-1", today="2026-07-13")

        title = "活着後の追肥判断"
        self.assertNotIn(title, {item["action"]["title"] for item in eight_days_before})
        self.assertIn(title, {item["action"]["title"] for item in seven_days_before})

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

    def test_action_can_move_to_in_progress_with_workload_and_remains_a_suggestion(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]

        updated = self.repository.update_action(
            planting["id"],
            action_id,
            {"status": "in_progress", "required_people": 3, "estimated_minutes": 75},
        )
        suggestions = self.repository.list_suggestions("field-1", today="2026-07-20")

        self.assertEqual(updated["status"], "in_progress")
        self.assertEqual(updated["required_people"], 3)
        self.assertEqual(updated["estimated_minutes"], 75)
        self.assertIn(action_id, {item["action"]["id"] for item in suggestions})

        with self.assertRaises(PlantManagementValidationError):
            self.repository.update_action(planting["id"], action_id, {"required_people": 0})

    def test_skip_action_records_decision_guidance_and_can_be_reopened(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]
        attachment = {
            "id": "skip-image-1",
            "storage": "r2",
            "object_key": "field-records/field-1/2026-07-19/skip-image-1.png",
            "content_type": "image/png",
            "size_bytes": 120,
            "original_filename": "leaf.png",
            "url": "/local/api/fields/field-1/record-images/skip-image-1",
        }

        skipped = self.repository.skip_action(
            planting["id"],
            action_id,
            "2026-07-19",
            "generated_in_error",
            "葉色と新梢は良好で、排液ECは1.2 mS/cmだった",
            "期限切れの自動作業のため不要",
            next_review_on="2026-08-01",
            attachments=[attachment],
            decided_by="worker@example.com",
            use_as_guidance=True,
        )

        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(skipped["skip_decision"]["reason_code"], "generated_in_error")
        self.assertEqual(skipped["skip_decision"]["attachments"][0]["id"], "skip-image-1")
        self.assertNotIn(action_id, {item["action"]["id"] for item in self.repository.list_suggestions("field-1", today="2026-07-19")})
        skipped_search = self.repository.search_actions(planting["id"], query="排液EC", statuses=["skipped"])
        self.assertEqual(skipped_search["items"][0]["id"], action_id)
        guidance = self.repository.guidance_examples("ブルーベリー")
        self.assertEqual(guidance[0]["decision_type"], "skip_action")
        self.assertEqual(guidance[0]["reason_code"], "generated_in_error")

        reloaded = PlantManagementRepository()
        reloaded.repository_path = self.repository.repository_path
        reloaded.load()
        self.assertEqual(reloaded.get_calendar(planting["id"])["actions"][0]["skip_decision"]["next_review_on"], "2026-08-01")

        reopened = self.repository.update_action(planting["id"], action_id, {"status": "planned"})
        self.assertEqual(reopened["status"], "planned")
        self.assertIsNone(reopened["skip_decision"])
        self.assertEqual(len(self.repository.guidance_examples("ブルーベリー")), 1)

    def test_skip_action_requires_a_supported_reason_observation_and_valid_review_date(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]

        with self.assertRaises(PlantManagementValidationError):
            self.repository.skip_action(planting["id"], action_id, "2026-07-19", "unknown", "確認済み")
        with self.assertRaises(PlantManagementValidationError):
            self.repository.skip_action(planting["id"], action_id, "2026-07-19", "other", "")
        with self.assertRaises(PlantManagementValidationError):
            self.repository.skip_action(
                planting["id"], action_id, "2026-07-19", "other", "確認済み", next_review_on="2026-07-18"
            )
        with self.assertRaises(PlantManagementValidationError):
            self.repository.update_action(planting["id"], action_id, {"status": "skipped"})

    def test_search_actions_filters_text_status_period_and_paginates(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        fertilizer_id = calendar["actions"][0]["id"]
        self.repository.update_action(planting["id"], fertilizer_id, {"status": "in_progress"})

        by_text = self.repository.search_actions(planting["id"], query="新 梢 追肥", statuses=["in_progress"])
        by_period = self.repository.search_actions(
            planting["id"],
            date_from="2026-07-14",
            date_to="2026-07-21",
            page=1,
            page_size=1,
        )

        self.assertEqual(by_text["total"], 1)
        self.assertEqual(by_text["items"][0]["id"], fertilizer_id)
        self.assertEqual(by_period["total"], 2)
        self.assertEqual(by_period["page_count"], 2)
        self.assertTrue(by_period["has_next"])

    def test_complete_action_stores_selected_work_date(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]
        self.repository.update_action(planting["id"], action_id, {"status": "in_progress"})

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
            work_details={
                "execution": {
                    "target": "鉢Aの根域",
                    "method_id": "custom",
                    "method_label": "液肥Aを施す",
                    "method_type": "material_application",
                    "material_name": "液肥A",
                    "amount_or_rate": "500倍を1鉢2L",
                    "custom_method": "液肥Aを施す",
                    "follow_up_days": 10,
                }
            },
        )
        bundle = self.repository.field_bundle("field-1", today="2026-07-24")

        self.assertEqual(work_log["performed_on"], "2026-07-23")
        self.assertEqual(work_log["rating"], 4)
        self.assertEqual(work_log["attachments"][0]["storage"], "r2")
        self.assertEqual(work_log["work_details"]["execution"]["follow_up_days"], 10)
        self.assertEqual(work_log["work_details"]["execution"]["material_name"], "液肥A")
        self.assertEqual(work_log["work_details"]["execution"]["amount_or_rate"], "500倍を1鉢2L")
        self.assertEqual(bundle["work_logs"][0]["note"], "少量施肥")
        self.assertEqual(bundle["calendars"][planting["id"]]["actions"][0]["status"], "completed")

    def test_legacy_pest_control_fields_migrate_to_common_work_model(self):
        planting = self._create_blueberry()
        calendar = self.repository.create_calendar(
            planting["id"],
            [
                {
                    "action_type": "pest_control",
                    "title": "害虫確認",
                    "priority": "recommended",
                    "window_start": "2026-07-20",
                    "window_end": "2026-07-21",
                    "pest_control": {
                        "targets": ["アブラムシ類"],
                        "observation_points": ["新芽と葉裏"],
                        "method_options": [
                            {
                                "id": "legacy-method",
                                "label": "既存の方法",
                                "method_type": "physical",
                                "product_name": "旧資材名",
                                "effective_days_default": 7,
                            }
                        ],
                    },
                }
            ],
        )

        action = calendar["actions"][0]
        self.assertNotIn("pest_control", action)
        self.assertEqual(action["work_plan"]["checkpoints"], ["新芽と葉裏"])
        self.assertEqual(action["work_plan"]["method_options"][0]["material_name"], "旧資材名")
        self.assertEqual(action["work_plan"]["method_options"][0]["follow_up_days_default"], 7)
        self.assertTrue(action["work_plan"]["start_conditions"])
        self.assertTrue(action["work_plan"]["completion_criteria"])
        self.assertEqual(action["work_plan"]["method_options"][0]["frequency"]["mode"], "as_needed")

    def test_generated_work_plan_is_parsed_into_the_fixed_action_format(self):
        planting = self._create_blueberry()
        calendar = self.repository.create_calendar(
            planting["id"],
            [
                {
                    "action_type": "fertilization",
                    "title": "液肥の要否を判断",
                    "priority": "recommended",
                    "window_start": "2026-08-01",
                    "window_end": "2026-08-07",
                    "work_plan": {
                        "targets": ["鉢Aの根域"],
                        "start_conditions": ["排液ECが目標以下で葉色が薄い"],
                        "skip_conditions": ["根傷みまたは過湿がある"],
                        "checkpoints": ["葉色", "排液EC"],
                        "completion_criteria": ["使用量と排液ECを記録した"],
                        "method_options": [
                            {
                                "id": "verified-liquid-feed",
                                "label": "検証済み液肥を施す",
                                "method_type": "material_application",
                                "material_name": "液肥A",
                                "purpose": "樹勢を維持する",
                                "application_method": "培地を軽く湿らせてから根域へ施す",
                                "amount_or_rate": "500倍を1鉢2L",
                                "procedure_steps": ["排液ECを測る", "500倍に希釈する", "根域へ2L施す"],
                                "completion_checks": ["排液と施用量を記録した"],
                                "precautions": ["EC高値なら見送る"],
                                "frequency": {
                                    "mode": "interval",
                                    "min_interval_days": 10,
                                    "preferred_interval_days": 14,
                                    "max_interval_days": 21,
                                    "max_applications": 3,
                                    "basis": "製品表示と排液EC",
                                },
                            }
                        ],
                    },
                }
            ],
        )

        plan = calendar["actions"][0]["work_plan"]
        method = plan["method_options"][0]
        self.assertEqual(plan["start_conditions"], ["排液ECが目標以下で葉色が薄い"])
        self.assertEqual(plan["skip_conditions"], ["根傷みまたは過湿がある"])
        self.assertEqual(method["amount_or_rate"], "500倍を1鉢2L")
        self.assertEqual(method["procedure_steps"][1], "500倍に希釈する")
        self.assertEqual(method["frequency"]["preferred_interval_days"], 14)
        self.assertEqual(method["frequency"]["max_applications"], 3)

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
        self.repository.update_action(planting["id"], calendar["actions"][0]["id"], {"status": "in_progress"})
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

        self.assertEqual(replaced["revision"], 4)
        self.assertEqual([action["status"] for action in replaced["actions"]], ["completed", "planned"])
        self.assertEqual(replaced["actions"][1]["title"], "新しい観察計画")

    def test_planned_action_cannot_be_completed_or_deleted_after_start(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        action_id = calendar["actions"][0]["id"]

        with self.assertRaises(PlantManagementValidationError):
            self.repository.complete_action(planting["id"], action_id, "2026-07-23")

        self.repository.update_action(planting["id"], action_id, {"status": "in_progress"})
        with self.assertRaises(PlantManagementValidationError):
            self.repository.delete_action(planting["id"], action_id)

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

    def test_calendar_generation_task_is_durable_and_commits_generated_calendar(self):
        planting = self._create_blueberry()
        queued = self.repository.enqueue_calendar_generation(
            planting["id"],
            kind="initial",
            start_date="2026-07-14",
            planning_notes="週末に作業する",
            audience={"experience_level": "beginner"},
        )

        with self.assertRaises(PlantManagementConflictError):
            self.repository.enqueue_calendar_generation(planting["id"], kind="regenerate", start_date="2026-07-20")

        claimed = self.repository.claim_next_calendar_generation()
        result = self.repository.complete_calendar_generation(
            claimed["id"],
            {
                "growth_targets": {"soil_moisture_percent": {"min": 30, "max": 60}},
                "actions": [
                    {
                        "action_type": "observation",
                        "title": "葉色を確認",
                        "window_start": "2026-07-14",
                        "window_end": "2026-07-20",
                    }
                ],
                "generation": {"source": "test"},
            },
        )

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(result["task"]["status"], "succeeded")
        self.assertEqual(result["calendar"]["actions"][0]["title"], "葉色を確認")
        bundle = self.repository.field_bundle("field-1")
        self.assertEqual(bundle["generation_tasks"][0]["status"], "succeeded")
        self.assertEqual(bundle["plantings"][0]["growth_targets"]["soil_moisture_percent"], {"min": 30.0, "max": 60.0})

    def test_automatic_regeneration_reconciles_existing_actions_without_duplicates(self):
        planting = self._create_blueberry()
        original = self._create_calendar(planting["id"])
        original_fertilizer_id = original["actions"][0]["id"]
        queued = self.repository.enqueue_calendar_generation(
            planting["id"], kind="regenerate", start_date="2026-07-20", mode="automatic"
        )
        self.repository.claim_next_calendar_generation()

        result = self.repository.complete_calendar_generation(
            queued["id"],
            {
                "actions": [
                    {
                        "rule_id": "rule-fertilization",
                        "action_type": "fertilization",
                        "title": "葉色とECを見て追肥を判断",
                        "window_start": "2026-07-22",
                        "window_end": "2026-08-05",
                        "reason": "残存肥効も含めて判断するため",
                    },
                    {
                        "action_type": "harvest",
                        "title": "収穫適期を確認",
                        "window_start": "2026-08-10",
                        "window_end": "2026-08-20",
                    },
                ],
                "generation": {"source": "test"},
            },
        )

        actions = result["calendar"]["actions"]
        self.assertEqual(sum(action["action_type"] == "fertilization" for action in actions), 1)
        self.assertEqual(next(action for action in actions if action["action_type"] == "fertilization")["id"], original_fertilizer_id)
        self.assertEqual({action["action_type"] for action in actions}, {"fertilization", "harvest"})

    def test_review_regeneration_requires_each_change_to_be_decided(self):
        planting = self._create_blueberry()
        original = self._create_calendar(planting["id"])
        original_titles = [action["title"] for action in original["actions"]]
        queued = self.repository.enqueue_calendar_generation(
            planting["id"], kind="regenerate", start_date="2026-07-20", mode="review"
        )
        self.repository.claim_next_calendar_generation()

        result = self.repository.complete_calendar_generation(
            queued["id"],
            {
                "growth_targets": {"soil_moisture_percent": {"min": 30, "max": 60}},
                "actions": [
                    {
                        "rule_id": "rule-fertilization",
                        "action_type": "fertilization",
                        "title": "追肥前にECを確認",
                        "window_start": "2026-07-23",
                        "window_end": "2026-08-03",
                    },
                    {
                        "action_type": "harvest",
                        "title": "収穫適期を確認",
                        "window_start": "2026-08-10",
                        "window_end": "2026-08-20",
                    },
                ],
                "generation": {"source": "test-review"},
            },
        )

        self.assertEqual(result["task"]["status"], "awaiting_review")
        self.assertEqual({item["change_type"] for item in result["task"]["proposals"]}, {"add", "update", "delete"})
        self.assertEqual([action["title"] for action in self.repository.get_calendar(planting["id"])["actions"]], original_titles)
        with self.assertRaises(PlantManagementConflictError):
            self.repository.enqueue_calendar_generation(planting["id"], kind="regenerate", start_date="2026-08-01")

        for proposal in result["task"]["proposals"]:
            decision = "rejected" if proposal["change_type"] == "add" else "approved"
            decided = self.repository.decide_calendar_generation_proposal(result["task"]["id"], proposal["id"], decision)

        self.assertEqual(decided["task"]["status"], "succeeded")
        titles = [action["title"] for action in decided["calendar"]["actions"]]
        self.assertIn("追肥前にECを確認", titles)
        self.assertNotIn("葉の病害虫確認", titles)
        self.assertNotIn("収穫適期を確認", titles)
        self.assertEqual(self.repository.get_planting(planting["id"])["growth_targets"]["soil_moisture_percent"], {"min": 35.0, "max": 65.0})

    def test_regeneration_does_not_match_unrelated_recurring_actions_by_rule_id_alone(self):
        planting = self._create_blueberry()
        self.repository.create_calendar(
            planting["id"],
            [
                {
                    "rule_id": "rule-observation",
                    "action_type": "observation",
                    "title": "季節の生育変化と次の重点作業を確認",
                    "window_start": "2027-04-15",
                    "window_end": "2027-04-22",
                }
            ],
        )
        queued = self.repository.enqueue_calendar_generation(
            planting["id"], kind="regenerate", start_date="2026-07-20", mode="review"
        )
        self.repository.claim_next_calendar_generation()

        result = self.repository.complete_calendar_generation(
            queued["id"],
            {
                "actions": [
                    {
                        "rule_id": "rule-observation",
                        "action_type": "observation",
                        "title": "定植後の活着確認",
                        "window_start": "2026-07-20",
                        "window_end": "2026-08-02",
                    },
                    {
                        "rule_id": "rule-observation",
                        "action_type": "observation",
                        "title": "季節の生育変化と次の重点作業を確認",
                        "window_start": "2027-04-15",
                        "window_end": "2027-04-22",
                    },
                ]
            },
        )

        self.assertEqual(len(result["task"]["proposals"]), 1)
        self.assertEqual(result["task"]["proposals"][0]["change_type"], "add")
        self.assertEqual(result["task"]["proposals"][0]["title"], "定植後の活着確認")

    def test_regeneration_does_not_duplicate_an_in_progress_action(self):
        planting = self._create_blueberry()
        calendar = self._create_calendar(planting["id"])
        in_progress = self.repository.update_action(
            planting["id"], calendar["actions"][0]["id"], {"status": "in_progress"}
        )
        queued = self.repository.enqueue_calendar_generation(
            planting["id"], kind="regenerate", start_date="2026-07-20", mode="review"
        )
        self.repository.claim_next_calendar_generation()

        result = self.repository.complete_calendar_generation(
            queued["id"],
            {
                "actions": [
                    {
                        "rule_id": in_progress["rule_id"],
                        "action_type": in_progress["action_type"],
                        "title": in_progress["title"],
                        "window_start": in_progress["window_start"],
                        "window_end": in_progress["window_end"],
                    }
                ]
            },
        )

        self.assertFalse(any(item.get("after", {}).get("title") == in_progress["title"] for item in result["task"]["proposals"] if item.get("after")))

    def test_interrupted_calendar_generation_is_requeued_and_failed_task_can_be_retried(self):
        planting = self._create_blueberry()
        first = self.repository.enqueue_calendar_generation(planting["id"], kind="initial", start_date="2026-07-14")
        self.repository.claim_next_calendar_generation()

        recovered = self.repository.recover_interrupted_calendar_generations()
        claimed_again = self.repository.claim_next_calendar_generation()
        failed = self.repository.fail_calendar_generation(claimed_again["id"], "AI connection timed out")
        retry = self.repository.enqueue_calendar_generation(planting["id"], kind="initial", start_date="2026-07-15")

        self.assertEqual(recovered[0]["id"], first["id"])
        self.assertEqual(recovered[0]["status"], "queued")
        self.assertEqual(claimed_again["attempts"], 2)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "AI connection timed out")
        self.assertEqual(retry["status"], "queued")


if __name__ == "__main__":
    unittest.main()
