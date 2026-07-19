import json
import os
import tempfile
import unittest
from datetime import UTC, datetime

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")

from ina_device_hub.crop_knowledge_provider import CropKnowledgeProvider  # noqa: E402


class CropKnowledgeProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.tmp_dir.name, "crop-knowledge.json")
        self.context = {
            "planting": {
                "crop_name": "ライチ",
                "cultivar": "ジャカパット",
                "crop_category": "fruit_tree",
                "tree_age_years": 4,
                "cultivation_method": "container",
                "planted_on": "2026-03-24",
                "conditions": {"soil_or_substrate": "酸性用土", "environment": "軒下"},
            },
            "field": {"location": {"prefecture": "愛媛県", "municipality": "西条市"}},
            "planning": {"start_date": "2026-07-19"},
        }
        self.settings = {
            "enabled": True,
            "text_analyze_api_key": "test-key",
            "text_analyze_base_url": "https://api.openai.com/v1",
            "text_analyze_model": "gpt-test",
            "plant_calendar_web_knowledge_enabled": True,
            "plant_calendar_web_knowledge_cache_days": 30,
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_search_parses_structured_evidence_and_reuses_cache(self):
        calls = []

        def fake_post(url, payload, api_key):
            calls.append((url, payload, api_key))
            answer = {
                "summary": ["鉢栽培では根域の乾きと排水を確認して潅水を判断する。"],
                "assumptions": ["資料は愛媛県のライチ専用基準ではない。"],
                "sources": [
                    {
                        "title": "果樹栽培指針",
                        "url": "https://www.pref.ehime.jp/example/fruit.pdf",
                        "publisher": "愛媛県",
                        "applicable_region": "愛媛県",
                        "published_at": "2025-03",
                    },
                    {"title": "広告記事", "url": "https://example.com/lychee"},
                ],
            }
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {"title": "農研機構資料", "url": "https://www.naro.go.jp/example/manual.html"},
                                {"title": "ブログ", "url": "https://example.org/post"},
                            ]
                        },
                    },
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer, ensure_ascii=False)}]},
                ]
            }

        provider = CropKnowledgeProvider(
            ai_settings=self.settings,
            cache_path=self.cache_path,
            http_post=fake_post,
            now=lambda: datetime(2026, 7, 19, tzinfo=UTC),
        )

        first = provider.get(self.context)
        second = provider.get(self.context)

        self.assertEqual(first["status"], "available")
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/responses")
        self.assertEqual(calls[0][2], "test-key")
        self.assertEqual(calls[0][1]["tool_choice"], "required")
        self.assertIn("go.jp", calls[0][1]["tools"][0]["filters"]["allowed_domains"])
        self.assertEqual([source["publisher"] for source in first["sources"]], ["愛媛県", "農研機構"])
        self.assertTrue(all("example." not in source["url"] for source in first["sources"]))
        self.assertEqual(first["sources"][0]["fetched_at"], "2026-07-19T00:00:00+00:00")

    def test_unsupported_compatible_provider_does_not_make_request(self):
        settings = {**self.settings, "text_analyze_base_url": "https://llm.example.test/v1"}
        provider = CropKnowledgeProvider(
            ai_settings=settings,
            cache_path=self.cache_path,
            http_post=lambda *_: self.fail("unsupported provider must not be called"),
        )

        result = provider.get(self.context)

        self.assertEqual(result["status"], "unsupported_provider")
        self.assertEqual(result["sources"], [])

    def test_untrusted_only_response_is_not_used_as_evidence(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"summary":["強い断定"],"sources":[{"title":"ブログ","url":"https://example.com/post"}]}',
                        }
                    ],
                }
            ]
        }
        provider = CropKnowledgeProvider(
            ai_settings=self.settings,
            cache_path=self.cache_path,
            http_post=lambda *_: response,
        )

        result = provider.get(self.context)

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["summary"], [])
        self.assertEqual(result["sources"], [])

    def test_search_failure_returns_error_status_without_raising(self):
        provider = CropKnowledgeProvider(
            ai_settings=self.settings,
            cache_path=self.cache_path,
            http_post=lambda *_: (_ for _ in ()).throw(RuntimeError("temporary failure")),
        )

        result = provider.get(self.context)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["sources"], [])

    def test_cached_evidence_remains_available_after_ai_key_is_removed(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"summary":["要点"],"sources":[{"title":"農研機構","url":"https://www.naro.go.jp/manual"}]}',
                        }
                    ],
                }
            ]
        }
        first = CropKnowledgeProvider(ai_settings=self.settings, cache_path=self.cache_path, http_post=lambda *_: response)
        first.get(self.context)
        without_key = CropKnowledgeProvider(
            ai_settings={**self.settings, "text_analyze_api_key": ""},
            cache_path=self.cache_path,
            http_post=lambda *_: self.fail("cache should avoid a request"),
        )

        result = without_key.get(self.context)

        self.assertEqual(result["status"], "available")
        self.assertTrue(result["cache_hit"])


if __name__ == "__main__":
    unittest.main()
