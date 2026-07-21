import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
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

from ina_device_hub.extension_installation_service import ExtensionInstallationService, ExtensionInstallError, ExtensionReviewError


def _manifest(extension_id="com.example.extension", *, description="毎日の確認を分かりやすく表示します。"):
    return {
        "schema_version": 1,
        "id": extension_id,
        "name": "圃場確認ガイド",
        "version": "1.0.0",
        "description": description,
        "compatibility": {"hub_extension_api": 1},
        "ui": {
            "device_detail": {
                "device_kinds": ["FGT"],
                "overview_cards": [
                    {
                        "id": "daily-guide",
                        "type": "callout",
                        "title": "今日の確認",
                        "description": "タンクの水量を確認します。",
                        "tone": "water",
                    }
                ],
            }
        },
    }


class FakeAIService:
    def __init__(self, *, available=True):
        self.available = available
        self.calls = []

    def audit_extension_manifest(self, manifest, static_findings):
        self.calls.append((manifest, static_findings))
        if not self.available:
            return {
                "status": "unavailable",
                "risk_level": "unknown",
                "summary": "AIが未設定です。",
                "findings": [],
                "recommendation": "人が確認してください。",
                "model": "",
            }
        return {
            "status": "completed",
            "risk_level": "low",
            "summary": "危険な案内は見つかりませんでした。",
            "findings": [],
            "recommendation": "提供元を確認して判断してください。",
            "model": "test-model",
        }


class ExtensionInstallationServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.ai_service = FakeAIService()
        self.service = ExtensionInstallationService(self.temporary_directory.name, ai_service=self.ai_service)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _review(self, manifest=None):
        payload = json.dumps(manifest or _manifest(), ensure_ascii=False).encode()
        return self.service.review_upload("extension.json", payload, reviewed_by="admin@example.com")

    def test_upload_runs_only_static_review_until_explicit_ai_consent(self):
        review = self._review()

        self.assertEqual(review["ai_audit"]["status"], "pending_consent")
        self.assertEqual(self.ai_service.calls, [])
        with self.assertRaisesRegex(ExtensionReviewError, "確認ダイアログ"):
            self.service.audit_review(review["id"], approved_by="admin@example.com")
        self.assertEqual(self.ai_service.calls, [])

        audited = self.service.audit_review(review["id"], consent_confirmed=True, approved_by="admin@example.com")

        self.assertEqual(audited["ai_audit"]["status"], "completed")
        self.assertTrue(audited["ai_audit_consent"]["confirmed"])
        self.assertEqual(audited["ai_audit_consent"]["shared_data"], ["validated_manifest", "static_findings"])
        self.assertEqual(len(self.ai_service.calls), 1)

    def test_install_is_blocked_until_ai_preflight_has_been_confirmed(self):
        review = self._review()

        with self.assertRaisesRegex(ExtensionInstallError, "AI監査の確認"):
            self.service.install_review(review["id"], installed_by="admin@example.com")

        self.service.audit_review(review["id"], consent_confirmed=True, approved_by="admin@example.com")
        result = self.service.install_review(review["id"], installed_by="admin@example.com")

        manifest_path = Path(self.temporary_directory.name) / "extensions" / "installed" / "com.example.extension" / "1.0.0" / "extension.json"
        self.assertTrue(manifest_path.is_file())
        self.assertEqual(result["extension"]["id"], "com.example.extension")
        audit_events = [json.loads(line) for line in self.service.audit_log_path.read_text().splitlines()]
        self.assertEqual([event["event"] for event in audit_events], ["reviewed", "ai_audit_approved", "ai_audit_completed", "installed"])
        self.assertTrue(audit_events[1]["ai_audit_consent"])

    def test_ai_unavailable_is_recorded_only_after_consent_and_allows_human_decision(self):
        service = ExtensionInstallationService(self.temporary_directory.name, ai_service=FakeAIService(available=False))
        payload = json.dumps(_manifest("com.example.no-ai"), ensure_ascii=False).encode()
        review = service.review_upload("extension.json", payload)

        audited = service.audit_review(review["id"], consent_confirmed=True)
        result = service.install_review(review["id"])

        self.assertEqual(audited["ai_audit"]["status"], "unavailable")
        self.assertEqual(result["extension"]["id"], "com.example.no-ai")

    def test_zip_rejects_path_traversal_and_extra_executable_file(self):
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("extension.json", json.dumps(_manifest("com.example.zip")))
            archive.writestr("../run.py", "print('unsafe')")

        review = self.service.review_upload("unsafe.inas-extension", package.getvalue())

        self.assertFalse(review["install_allowed"])
        self.assertTrue(any(item["severity"] == "block" for item in review["static_findings"]))
        self.assertEqual(self.ai_service.calls, [])

    def test_unknown_manifest_field_is_blocked(self):
        manifest = _manifest("com.example.unknown")
        manifest["permissions"] = ["network"]

        review = self._review(manifest)

        self.assertFalse(review["install_allowed"])
        self.assertIn("unsupported fields", review["static_findings"][-1]["detail"])

    def test_identity_requires_reverse_domain_and_visible_contribution(self):
        invalid_id = _manifest("extension")
        empty = _manifest("com.example.empty")
        empty["ui"]["device_detail"].pop("overview_cards")

        invalid_id_review = self._review(invalid_id)
        empty_review = self._review(empty)

        self.assertFalse(invalid_id_review["install_allowed"])
        self.assertFalse(empty_review["install_allowed"])
        self.assertIn("visible contribution", empty_review["static_findings"][-1]["detail"])

    def test_active_content_and_reserved_official_identity_are_blocked(self):
        manifest = _manifest("jp.inas.official.fake", description="<script>alert(1)</script>")

        review = self._review(manifest)

        categories = {item["category"] for item in review["static_findings"] if item["severity"] == "block"}
        self.assertEqual(categories, {"identity", "active_content"})
        self.assertFalse(review["install_allowed"])


if __name__ == "__main__":
    unittest.main()
