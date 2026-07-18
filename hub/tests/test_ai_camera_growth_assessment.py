import json
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
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.ai_content_service import AIContentService  # noqa: E402


class AIPlantGrowthAssessmentTest(unittest.TestCase):
    def setUp(self):
        self.service = AIContentService()
        self.service.ai_settings = {
            "enabled": True,
            "image_analyze_api_key": "test-key",
            "image_analyze_base_url": "https://example.invalid/v1",
            "image_analyze_model": "vision-model",
        }

    def test_assessment_sends_bounded_data_url_and_parses_json_fence(self):
        calls = []

        def fake_chat_completion(**kwargs):
            calls.append(kwargs)
            return "```json\n" + json.dumps({"overall_status": "healthy", "confidence": 0.8}, ensure_ascii=False) + "\n```"

        self.service._chat_completion = fake_chat_completion

        result = self.service.assess_plant_growth(
            {"field": {"name": "果樹園"}, "plantings": [{"crop_name": "ライチ"}]},
            [{"label": "現在画像", "captured_at": "2026-07-19T08:00:00", "bytes": b"\xff\xd8frame\xff\xd9"}],
        )

        self.assertEqual(result["overall_status"], "healthy")
        content = calls[0]["messages"][1]["content"]
        image_item = next(item for item in content if item["type"] == "image_url")
        self.assertTrue(image_item["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        prompt = content[0]["text"]
        self.assertIn("確定診断", prompt)
        self.assertIn("製品名", prompt)

    def test_assessment_requires_configured_image_channel(self):
        self.service.ai_settings["enabled"] = False

        with self.assertRaises(RuntimeError):
            self.service.assess_plant_growth({}, [{"bytes": b"image"}])


if __name__ == "__main__":
    unittest.main()
