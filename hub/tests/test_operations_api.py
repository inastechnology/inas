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

from ina_device_hub import operations_api, user_context, web_server  # noqa: E402


class OperationsApiTest(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()
        self.environment = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
            "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
            "HUB_OPERATIONS_SERVICE_IDS": "service-token-id.access",
        }
        self.headers = {user_context.ACCESS_JWT_HEADER: "signed-service-token"}

    def _service(self):
        service = Mock()
        service.repository.get_all.return_value = {
            "wtr-active": {"device_id": "wtr-active", "device_kind": "WTR", "state": "active", "firmware_version": "0.0.3"},
            "wtr-retired": {"device_id": "wtr-retired", "device_kind": "WTR", "state": "retired", "firmware_version": "0.0.2"},
            "env-active": {"device_id": "env-active", "device_kind": "ENV", "state": "active"},
        }
        service.artifact_repository.get.return_value = {"device_kind": "WTR", "version": "0.0.4", "rollout_state": "active"}
        service.set_firmware_target.side_effect = lambda device_id, version: {"device_id": device_id, "target_firmware_version": version}
        service.upsert_firmware_binary.return_value = {
            "device_kind": "WTR",
            "version": "0.0.4",
            "sha256": "a" * 64,
        }
        return service

    def _patch_auth(self, common_name="service-token-id.access"):
        return patch.object(user_context, "_verify_access_token", return_value={"common_name": common_name})

    def test_operations_api_requires_allowlisted_service_token(self):
        with patch.dict(os.environ, self.environment, clear=False), self._patch_auth("other-service.access"):
            response = self.client.get("/operations/api/v1/health", headers=self.headers)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Cloudflare Access service is not allowed")

    def test_operations_api_rejects_local_auth_mode(self):
        with patch.dict(os.environ, {**self.environment, "HUB_AUTH_MODE": "local"}, clear=False):
            response = self.client.get("/operations/api/v1/health", headers=self.headers)

        self.assertEqual(response.status_code, 401)

    def test_device_list_filters_kind_without_status_history(self):
        service = self._service()
        with (
            patch.dict(os.environ, self.environment, clear=False),
            self._patch_auth(),
            patch.object(operations_api, "ota_update_service", return_value=service),
        ):
            response = self.client.get("/operations/api/v1/devices?device_kind=WTR", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()["items"]), {"wtr-active", "wtr-retired"})

    def test_rollout_defaults_to_dry_run_and_excludes_retired_devices(self):
        service = self._service()
        with (
            patch.dict(os.environ, self.environment, clear=False),
            self._patch_auth(),
            patch.object(operations_api, "ota_update_service", return_value=service),
        ):
            response = self.client.post(
                "/operations/api/v1/devices/firmware-rollouts",
                headers=self.headers,
                json={"device_kind": "WTR", "version": "0.0.4"},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["candidate_device_ids"], ["wtr-active"])
        self.assertEqual(payload["skipped"], [{"device_id": "wtr-retired", "reason": "retired"}])
        service.set_firmware_target.assert_not_called()

    def test_rollout_applies_explicit_device_targets_idempotently(self):
        service = self._service()
        with (
            patch.dict(os.environ, self.environment, clear=False),
            self._patch_auth(),
            patch.object(operations_api, "ota_update_service", return_value=service),
            patch.object(operations_api, "append_device_event"),
        ):
            response = self.client.post(
                "/operations/api/v1/devices/firmware-rollouts",
                headers=self.headers,
                json={"device_kind": "WTR", "version": "0.0.4", "device_ids": ["wtr-active"], "dry_run": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["updated"], [{"device_id": "wtr-active", "target_firmware_version": "0.0.4"}])
        service.set_firmware_target.assert_called_once_with("wtr-active", "0.0.4")

    def test_publish_accepts_binary_without_browser_origin(self):
        service = self._service()
        with (
            patch.dict(os.environ, self.environment, clear=False),
            self._patch_auth(),
            patch.object(operations_api, "ota_update_service", return_value=service),
            patch.object(operations_api, "append_device_event"),
        ):
            response = self.client.post(
                "/operations/api/v1/devices/firmware-artifacts/WTR/0.0.4",
                headers={**self.headers, "Content-Type": "application/octet-stream"},
                data=b"firmware",
            )

        self.assertEqual(response.status_code, 201)
        service.upsert_firmware_binary.assert_called_once_with("WTR", "0.0.4", b"firmware")


if __name__ == "__main__":
    unittest.main()
