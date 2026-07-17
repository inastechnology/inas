import unittest
from datetime import date, timedelta

from ina_device_hub.ai_content_service import AIContentService
from ina_device_hub.plant_calendar_quality import evaluate_plant_calendar


class PlantCalendarQualityTest(unittest.TestCase):
    def setUp(self):
        self.service = AIContentService()
        self.service.ai_settings = {"enabled": False, "text_analyze_api_key": ""}

    def test_established_monthly_fallback_passes_quality_gate(self):
        today = date.today()
        context = {
            "planting": {
                "crop_name": "ライチ",
                "crop_category": "fruit_tree",
                "planted_on": (today - timedelta(days=115)).isoformat(),
                "conditions": {"notes": "4/15に施肥、6/24に防除。"},
            },
            "planning": {
                "start_date": today.isoformat(),
                "current_date": today.isoformat(),
                "horizon_months": 12,
                "notes": "１か月に１回の作業。それ以外は自動潅水とカメラ監視。",
            },
        }

        calendar = self.service.generate_plant_calendar(context)
        report = evaluate_plant_calendar(context, calendar, {"minimum_score": 90})

        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["score"], 90)

    def test_quality_gate_reports_expired_and_automated_manual_work(self):
        today = date.today()
        context = {
            "planting": {"crop_name": "ライチ", "planted_on": (today - timedelta(days=120)).isoformat()},
            "planning": {"start_date": today.isoformat(), "current_date": today.isoformat(), "notes": "自動潅水"},
        }
        calendar = {
            "actions": [
                {
                    "action_type": "watering",
                    "title": "定植後の活着確認と水やり",
                    "window_start": (today - timedelta(days=10)).isoformat(),
                    "window_end": (today - timedelta(days=5)).isoformat(),
                    "reason": "短い",
                    "instructions": "短い",
                }
            ]
        }

        report = evaluate_plant_calendar(context, calendar)
        failed = {item["id"] for item in report["checks"] if not item["passed"]}

        self.assertFalse(report["passed"])
        self.assertIn("future_only", failed)
        self.assertIn("automation_boundary", failed)
        self.assertIn("history_aware", failed)
