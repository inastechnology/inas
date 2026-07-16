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

from ina_device_hub.ai_content_service import AIContentService  # noqa: E402


class AIContentServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = AIContentService()
        self.context = {
            "planting": {
                "crop_name": "ブルーベリー",
                "cultivar": "ティフブルー",
                "planted_on": "2026-07-14",
                "placement_name": "鉢A",
            }
        }

    def test_calendar_fallback_has_priorities_reasons_and_tags(self):
        self.service.ai_settings = {"text_analyze_api_key": ""}

        result = self.service.generate_plant_calendar(self.context)

        self.assertEqual(result["generation"]["source"], "fallback")
        self.assertGreaterEqual(len(result["actions"]), 6)
        self.assertIn(result["actions"][0]["priority"], {"required", "should", "recommended", "optional"})
        self.assertTrue(result["actions"][0]["reason"])
        self.assertTrue(result["actions"][0]["tags"])
        self.assertTrue(any("結実" in action["tags"] for action in result["actions"]))
        self.assertTrue(result["care_profile"]["irrigation"]["decision_factors"])
        self.assertTrue(any(rule["anchor"] == "completion_date" for rule in result["task_rules"]))
        self.assertEqual(result["growth_targets"]["soil_ph"], {"min": 4.5, "max": 5.5})
        self.assertTrue(all(action["work_plan"]["targets"] for action in result["actions"]))
        self.assertTrue(all(action["work_plan"]["start_conditions"] for action in result["actions"]))
        self.assertTrue(all(action["work_plan"]["skip_conditions"] for action in result["actions"]))
        self.assertTrue(all(action["work_plan"]["checkpoints"] for action in result["actions"]))
        self.assertTrue(all(action["work_plan"]["method_options"] for action in result["actions"]))
        self.assertTrue(all(action["work_plan"]["completion_criteria"] for action in result["actions"]))
        self.assertTrue(
            all(
                method["procedure_steps"] and method["completion_checks"] and method["precautions"]
                for action in result["actions"]
                for method in action["work_plan"]["method_options"]
            )
        )
        fertilization = next(action for action in result["actions"] if action["action_type"] == "fertilization")
        pruning = next(action for action in result["actions"] if action["action_type"] == "pruning")
        self.assertIn("葉色と樹勢", fertilization["work_plan"]["checkpoints"])
        self.assertTrue(any(method["method_type"] == "material_application" for method in fertilization["work_plan"]["method_options"]))
        self.assertIn("枯枝・交差枝・徒長枝", pruning["work_plan"]["targets"])
        pest_action = next(action for action in result["actions"] if action["action_type"] == "pest_control")
        self.assertTrue(pest_action["work_plan"]["checkpoints"])

    def test_calendar_does_not_call_api_when_ai_is_disabled(self):
        self.service.ai_settings = {"enabled": False, "text_analyze_api_key": "configured", "text_analyze_model": "model"}
        self.service._chat_completion = lambda **kwargs: self.fail("disabled AI must not call the API")

        result = self.service.generate_plant_calendar(self.context)

        self.assertEqual(result["generation"]["source"], "fallback")

    def test_calendar_parses_json_code_fence_from_llm(self):
        self.service.ai_settings = {
            "text_analyze_api_key": "test",
            "text_analyze_base_url": "https://example.test/v1",
            "text_analyze_model": "test-model",
        }
        self.service._chat_completion = lambda **kwargs: """```json
{"actions":[{"action_type":"fertilization","title":"追肥判断","priority":"recommended","window_start":"2026-08-01","window_end":"2026-08-10","timing_label":"8月上旬","reason":"樹勢維持","instructions":"葉色を確認","tags":["追肥"]}]}
```"""

        result = self.service.generate_plant_calendar(self.context, guidance_examples=[{"changes": {"priority": {"after": "recommended"}}}])

        self.assertEqual(result["generation"]["source"], "llm")
        self.assertEqual(result["generation"]["model"], "test-model")
        self.assertEqual(result["actions"][0]["title"], "追肥判断")
        self.assertEqual(result["growth_targets"]["soil_moisture_percent"], {"min": 35, "max": 65})
        self.assertTrue(result["care_profile"])
        self.assertEqual(result["actions"][0]["rule_id"], "rule-fertilization")

    def test_calendar_sanitizes_out_of_domain_generated_targets(self):
        self.service.ai_settings = {"text_analyze_api_key": "test", "text_analyze_model": "test-model"}
        self.service._chat_completion = lambda **kwargs: """
        {"growth_targets":{"soil_moisture_percent":{"min":-1,"max":900},"soil_ph":{"min":4.5,"max":5.5}},
         "actions":[{"action_type":"observation","title":"観察","priority":"recommended","window_start":"2026-08-01","window_end":"2026-08-02"}]}
        """

        result = self.service.generate_plant_calendar(self.context)

        self.assertEqual(result["growth_targets"]["soil_moisture_percent"], {"min": 35, "max": 65})
        self.assertEqual(result["growth_targets"]["soil_ph"], {"min": 4.5, "max": 5.5})

    def test_question_fallback_references_registered_calendar(self):
        self.service.ai_settings = {"text_analyze_api_key": ""}
        context = {
            **self.context,
            "calendar": {"actions": [{"title": "活着後の追肥要否を判断", "status": "planned"}]},
        }

        answer = self.service.answer_plant_question(context, "追肥はいつですか")

        self.assertIn("ブルーベリー", answer)
        self.assertIn("活着後の追肥要否を判断", answer)
        self.assertIn("製品ラベル", answer)

    def test_follow_up_fallback_uses_actual_completion_date(self):
        self.service.ai_settings = {"text_analyze_api_key": ""}
        context = {
            "task_rule": {
                "rule_id": "rule-fertilization",
                "action_type": "fertilization",
                "title": "追肥要否を確認",
                "recurrence_type": "interval_after_completion",
                "anchor": "completion_date",
                "interval_days": {"min": 40, "preferred": 45, "max": 50},
                "active_months": list(range(1, 13)),
                "conditions": ["葉色とECを確認"],
                "skip_conditions": ["ECが高い"],
            },
            "completed_action": {"action_type": "fertilization", "priority": "recommended"},
            "completion_event": {"performed_on": "2026-08-10"},
        }

        result = self.service.generate_follow_up_tasks(context)

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["actions"][0]["rule_id"], "rule-fertilization")
        self.assertIn("2026-08-10", result["actions"][0]["reason"])
        self.assertLessEqual(result["actions"][0]["window_start"], "2026-09-24")
        self.assertGreaterEqual(result["actions"][0]["window_end"], "2026-09-24")

    def test_follow_up_llm_prompt_does_not_rebuild_care_profile(self):
        self.service.ai_settings = {"text_analyze_api_key": "test", "text_analyze_model": "test-model"}
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return '{"decision_summary":"完了日から再計算","actions":[]}'

        self.service._chat_completion = fake_chat
        context = {
            "care_profile": {"summary": "保存済み基準"},
            "task_rule": {
                "rule_id": "rule-fertilization",
                "recurrence_type": "interval_after_completion",
                "interval_days": {"preferred": 45},
            },
            "completion_event": {"performed_on": "2026-08-10"},
        }

        result = self.service.generate_follow_up_tasks(context)

        prompt = "\n".join(message["content"] for message in captured["messages"])
        self.assertEqual(result["actions"], [])
        self.assertIn("新しい栽培知識や目標値を作り直してはいけません", prompt)
        self.assertIn("保存済み基準", prompt)

    def test_initial_and_follow_up_prompts_apply_the_selected_experience_level(self):
        beginner_context = {**self.context, "audience": {"experience_level": "beginner"}}
        initial_prompt = "\n".join(
            message["content"] for message in self.service._initial_plant_plan_messages(beginner_context, [])
        )
        self.assertIn("対象利用者は農業初心者です", initial_prompt)
        self.assertIn("準備、実施、終了確認", initial_prompt)
        self.assertIn("procedure_steps", initial_prompt)
        self.assertIn("validated_pesticide_candidates", initial_prompt)
        self.assertIn("収穫前日数", initial_prompt)

        professional_context = {
            "audience": {"experience_level": "professional"},
            "task_rule": {"recurrence_type": "interval_after_completion"},
        }
        follow_up_prompt = "\n".join(
            message["content"] for message in self.service._follow_up_task_messages(professional_context)
        )
        self.assertIn("対象利用者は農業・園芸の実務経験者です", follow_up_prompt)
        self.assertIn("判断閾値", follow_up_prompt)
        self.assertIn("frequency", follow_up_prompt)
        self.assertIn("同じ肥料、農薬、資材、方法の再実施を自動決定しない", follow_up_prompt)

    def test_unknown_experience_level_uses_standard_prompt(self):
        context = {**self.context, "audience": {"experience_level": "unknown"}}

        prompt = "\n".join(message["content"] for message in self.service._initial_plant_plan_messages(context, []))

        self.assertIn("対象利用者は基本的な栽培作業ができる標準レベルです", prompt)

    def test_pest_follow_up_uses_recorded_follow_up_days(self):
        self.service.ai_settings = {"text_analyze_api_key": ""}
        context = {
            "task_rule": {
                "rule_id": "rule-pest-control",
                "action_type": "pest_control",
                "title": "害虫の再発を確認",
                "recurrence_type": "continuous_review",
                "anchor": "completion_date",
                "interval_days": {"min": 7, "preferred": 14, "max": 21},
                "active_months": list(range(1, 13)),
            },
            "completed_action": {
                "action_type": "pest_control",
                "priority": "should",
                "work_plan": {"targets": ["アブラムシ類"], "checkpoints": ["新芽と葉裏"]},
            },
            "completion_event": {
                "performed_on": "2026-08-10",
                "work_details": {"execution": {"target": "アブラムシ類", "follow_up_days": 10}},
            },
        }

        result = self.service.generate_follow_up_tasks(context)

        action = result["actions"][0]
        self.assertEqual(action["timing_label"], "前回実施日から約10日後")
        self.assertEqual(action["work_plan"]["targets"], ["アブラムシ類"])
        self.assertIn("再発・残存", action["instructions"])

    def test_fertilization_follow_up_uses_recorded_method_and_follow_up_days(self):
        self.service.ai_settings = {"text_analyze_api_key": ""}
        context = {
            "task_rule": {
                "rule_id": "rule-fertilization",
                "action_type": "fertilization",
                "title": "追肥後の状態確認",
                "recurrence_type": "interval_after_completion",
                "anchor": "completion_date",
                "interval_days": {"min": 30, "preferred": 45, "max": 60},
                "active_months": list(range(1, 13)),
            },
            "completed_action": {
                "action_type": "fertilization",
                "priority": "recommended",
                "work_plan": {"targets": ["根域・培地"], "checkpoints": ["葉色と樹勢"]},
            },
            "completion_event": {
                "performed_on": "2026-08-10",
                "work_details": {
                    "execution": {
                        "target": "鉢Aの根域",
                        "method_label": "液肥を施す",
                        "follow_up_days": 12,
                    }
                },
            },
        }

        result = self.service.generate_follow_up_tasks(context)

        action = result["actions"][0]
        self.assertEqual(action["timing_label"], "前回実施日から約12日後")
        self.assertEqual(action["work_plan"]["targets"], ["鉢Aの根域"])
        self.assertIn("液肥を施す", action["instructions"])


if __name__ == "__main__":
    unittest.main()
