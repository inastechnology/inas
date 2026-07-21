import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

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
os.environ["HUB_AUTH_MODE"] = "local"

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.extension_installation_service import ExtensionInstallationService  # noqa: E402
from tests.test_extension_installation_service import FakeAIService, _manifest  # noqa: E402


class ExtensionWebTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.service = ExtensionInstallationService(self.temporary_directory.name, ai_service=FakeAIService())
        self.service_patch = patch.object(web_server, "extension_installation_service", return_value=self.service)
        self.service_patch.start()
        self.client = web_server.app.test_client()

    def tearDown(self):
        self.service_patch.stop()
        self.temporary_directory.cleanup()

    def test_page_explains_ai_confirmation_before_external_review(self):
        response = self.client.get("/settings/extensions")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("この操作だけではインストールされず、AIにも送信されません", html)
        self.assertIn("AI監査を始めますか？", html)
        self.assertIn("APIキー、DB、機器データ、圃場データ、利用者情報", html)
        self.assertIn("AIサービスの契約内容に応じて利用料", html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_ai_audit_api_rejects_missing_confirmation(self):
        review = self._upload("com.example.web-consent")

        response = self.client.post(f"/local/api/extensions/reviews/{review['id']}/ai-audit", json={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("確認ダイアログ", response.get_json()["error"])
        self.assertEqual(self.service.ai_service.calls, [])

    def test_review_audit_and_install_flow(self):
        review = self._upload("com.example.web-flow")
        self.assertEqual(review["ai_audit"]["status"], "pending_consent")

        audit_response = self.client.post(
            f"/local/api/extensions/reviews/{review['id']}/ai-audit",
            json={"confirmed": True},
        )
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(audit_response.get_json()["review"]["ai_audit"]["status"], "completed")

        install_response = self.client.post(f"/local/api/extensions/reviews/{review['id']}/install")
        self.assertEqual(install_response.status_code, 200)
        self.assertEqual(install_response.get_json()["extension"]["id"], "com.example.web-flow")

    def _upload(self, extension_id):
        payload = json.dumps(_manifest(extension_id), ensure_ascii=False).encode()
        response = self.client.post(
            "/local/api/extensions/reviews",
            data={"extension": (io.BytesIO(payload), "extension.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["review"]


if __name__ == "__main__":
    unittest.main()
