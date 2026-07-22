import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOCAL_STORAGE_BASE_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "local")
os.environ.setdefault("TURSO_AUTH_TOKEN", "local")
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

from ina_device_hub import user_context, web_server  # noqa: E402


class WebServerSecurityTest(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()
        self.environment = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "HUB_ADMIN_EMAILS": "admin@example.com",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
            "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
        }

    def _headers(self, email="worker@example.com", *, include_origin=True):
        headers = {
            user_context.ACCESS_JWT_HEADER: "signed-token",
            user_context.ACCESS_EMAIL_HEADER: email,
        }
        if include_origin:
            headers["Origin"] = "http://localhost"
        return headers

    def test_health_endpoint_is_public_but_application_requires_access_jwt(self):
        with patch.dict(os.environ, self.environment, clear=False):
            health = self.client.get("/healthz")
            application = self.client.get("/")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(application.status_code, 401)

    def test_device_firmware_download_path_does_not_require_browser_access_jwt(self):
        with patch.dict(os.environ, self.environment, clear=False):
            response = self.client.get("/firmware/WTR/missing/firmware.bin")

        self.assertEqual(response.status_code, 404)

    def test_operations_authentication_rejection_notifies_discord_without_secret_headers(self):
        notification_service = Mock()
        headers = {
            "CF-Connecting-IP": "203.0.113.10",
            "CF-Ray": "ray-123",
            "User-Agent": "unexpected-client/1.0",
            "CF-Access-Client-Secret": "must-not-be-forwarded",
        }
        with patch.dict(os.environ, self.environment, clear=False), patch.object(web_server, "discord_notification_service", return_value=notification_service):
            response = self.client.get("/operations/api/v1/health", headers=headers)

        self.assertEqual(response.status_code, 401)
        reason, details = notification_service.notify_operations_security_alert.call_args.args
        self.assertIn("missing", reason)
        self.assertEqual(details["client_ip"], "203.0.113.10")
        self.assertEqual(details["cf_ray"], "ray-123")
        self.assertNotIn("must-not-be-forwarded", str(details))

    def test_cloudflare_write_requires_same_origin(self):
        with (
            patch.dict(os.environ, self.environment, clear=False),
            patch.object(
                user_context,
                "_verify_access_token",
                return_value={"email": "worker@example.com"},
            ),
        ):
            response = self.client.post("/local/api/fields", headers=self._headers(include_origin=False), json={})

        self.assertEqual(response.status_code, 403)
        self.assertIn("same-origin", response.get_json()["error"])

    def test_cloudflare_write_accepts_public_origin_from_trusted_proxy_headers(self):
        headers = self._headers()
        headers.update(
            {
                "Origin": "https://hub.example.com",
                "X-Forwarded-Host": "hub.example.com",
                "X-Forwarded-Proto": "https",
            }
        )
        with (
            patch.dict(os.environ, self.environment, clear=False),
            patch.object(
                user_context,
                "_verify_access_token",
                return_value={"email": "worker@example.com"},
            ),
        ):
            response = self.client.post("/not-found", headers=headers)

        self.assertEqual(response.status_code, 404)

    def test_operator_cannot_modify_device_or_firmware_administration(self):
        with (
            patch.dict(os.environ, self.environment, clear=False),
            patch.object(
                user_context,
                "_verify_access_token",
                return_value={"email": "worker@example.com"},
            ),
        ):
            device = self.client.post("/local/api/mqtt-devices/device-1/disable", headers=self._headers())
            legacy_config = self.client.put("/local/api/device-configs/device-1", headers=self._headers(), json={})
            legacy_edit = self.client.post("/devices/device-1/edit", headers=self._headers(), data={})
            firmware = self.client.post("/local/api/firmware-artifacts/inspect", headers=self._headers(), data=b"firmware")

        self.assertEqual(device.status_code, 403)
        self.assertEqual(legacy_config.status_code, 403)
        self.assertEqual(legacy_edit.status_code, 403)
        self.assertEqual(firmware.status_code, 403)

    def test_legacy_local_mode_does_not_add_new_global_role_restrictions(self):
        headers = {user_context.ACCESS_EMAIL_HEADER: "worker@example.com"}
        with patch.dict(os.environ, {"HUB_AUTH_MODE": "local", "HUB_ADMIN_EMAILS": ""}, clear=False):
            response = self.client.post("/local/api/mqtt-devices/missing/disable", headers=headers)

        self.assertNotEqual(response.status_code, 403)

    def test_security_headers_are_applied_globally(self):
        with patch.dict(os.environ, {"HUB_AUTH_MODE": "local"}, clear=False):
            response = self.client.get("/healthz")

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors", response.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
