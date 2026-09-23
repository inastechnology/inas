import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from ina_device_hub.cloudflare_token_connector import CloudflareTokenConnector, TokenProvisioningError, _NoRedirects
from ina_device_hub.collector_access_repository import CollectorAccessRepository, CollectorStorageError
from ina_device_hub.collector_access_service import CollectorAccessService
from ina_device_hub.operations_access import OperationsPermissionError, read_grant_for_actor
from tests.test_operations_api import web_server


class CollectorAccessTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.environment = patch.dict(
            os.environ,
            {
                "WORK_DIR": temporary.name,
                "HUB_AUTH_MODE": "cloudflare_access",
                "HUB_OPERATIONS_READ_GRANTS": "{}",
                "HUB_OPERATIONS_SERVICE_IDS": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.repository = CollectorAccessRepository()
        self.connector = Mock(account_id="account", app_id="app", configured=True)
        self.connector.create_token.return_value = {"id": "token-id", "client_id": "collector.access", "client_secret": "one-time-secret"}
        self.connector.create_policy.return_value = {"id": "policy-id"}
        self.fields = Mock()
        self.fields.list.return_value = [{"id": "field-a", "name": "圃場 A"}, {"id": "field-b", "name": "圃場 B"}]
        self.service = CollectorAccessService(self.fields, self.repository, self.connector)
        self.payload = {"name": "記録 AI", "days": 30, "scopes": ["records:read", "images:read"], "field_ids": ["field-a"]}

    def issue(self):
        return self.service.issue(self.payload, "admin@example.com")

    def test_issue_persists_only_metadata_and_enforces_scopes_and_fields(self):
        result = self.issue()
        self.assertEqual(result["client_secret"], "one-time-secret")
        self.assertNotIn("one-time-secret", self.repository.path.read_text())
        self.assertNotIn("client_secret", json.dumps(self.service.list()))
        self.assertEqual(self.repository.path.stat().st_mode & 0o777, 0o600)
        grant = read_grant_for_actor("service:collector.access")
        grant.require("records:read", "field-a")
        with self.assertRaises(OperationsPermissionError):
            grant.require("records:read", "field-b")
        self.connector.create_policy.assert_called_once_with(f"inas-collector-{result['collector']['id']}", "token-id")

    def test_update_and_revocation_apply_to_new_requests_without_restart(self):
        collector_id = self.issue()["collector"]["id"]
        self.service.update(collector_id, {"scopes": ["images:read"], "field_ids": ["field-b"]}, "admin@example.com")
        grant = read_grant_for_actor("service:collector.access")
        grant.require("images:read", "field-b")
        with self.assertRaises(OperationsPermissionError):
            grant.require("records:read", "field-b")
        self.connector.delete_token.side_effect = TokenProvisioningError("offline")
        result = self.service.revoke(collector_id, "admin@example.com")
        self.assertTrue(result["cleanup_pending"])
        with self.assertRaises(OperationsPermissionError):
            read_grant_for_actor("service:collector.access")
        self.connector.delete_token.side_effect = None
        self.assertFalse(self.service.revoke(collector_id, "admin@example.com")["cleanup_pending"])

    def test_revocation_is_persisted_before_cloudflare_call(self):
        collector_id = self.issue()["collector"]["id"]

        def assert_denied(_token_id):
            with self.assertRaises(OperationsPermissionError):
                read_grant_for_actor("service:collector.access")

        self.connector.delete_token.side_effect = assert_denied
        self.service.revoke(collector_id, "admin@example.com")

    def test_invalid_permissions_do_not_create_remote_tokens(self):
        for change in (
            {"scopes": []},
            {"scopes": ["devices:write"]},
            {"field_ids": []},
            {"field_ids": ["missing"]},
            {"field_ids": ["*", "field-a"]},
            {"days": True},
            {"name": "bad\nname"},
        ):
            with self.subTest(change=change), self.assertRaises(TokenProvisioningError):
                self.service.issue({**self.payload, **change}, "admin@example.com")
        self.connector.create_token.assert_not_called()

    def test_expiration_and_corrupt_storage_fail_closed(self):
        collector_id = self.issue()["collector"]["id"]
        records = self.repository.read()
        records[collector_id]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        self.repository.write(records)
        with self.assertRaises(OperationsPermissionError):
            read_grant_for_actor("service:collector.access")
        self.assertEqual(self.service.list()[0]["status"], "expired")
        self.repository.path.write_text("{broken")
        with self.assertRaises(OperationsPermissionError):
            read_grant_for_actor("service:legacy.access")

    def test_failed_policy_creation_never_grants_access(self):
        self.connector.create_policy.side_effect = TokenProvisioningError("offline")
        with self.assertRaises(TokenProvisioningError):
            self.issue()
        self.connector.delete_token.assert_called_once_with("token-id")
        with self.assertRaises(OperationsPermissionError):
            read_grant_for_actor("service:collector.access")
        self.assertNotIn("one-time-secret", self.repository.path.read_text())

    def test_unknown_issuance_result_remains_visible_for_cleanup(self):
        self.connector.create_token.side_effect = TokenProvisioningError("timeout")
        with self.assertRaises(TokenProvisioningError):
            self.issue()
        item = self.service.list()[0]
        self.assertEqual(item["status"], "revoked")
        self.assertTrue(item["cleanup_pending"])

    def test_issuance_rejects_writer_or_host_grant_overlap(self):
        for settings in ({"HUB_OPERATIONS_SERVICE_IDS": "collector.access"}, {"HUB_OPERATIONS_READ_GRANTS": '{"collector.access":{}}'}):
            with self.subTest(settings=settings), patch.dict(os.environ, settings), self.assertRaises(TokenProvisioningError):
                self.issue()
        self.connector.create_policy.assert_not_called()

    def test_repository_refuses_secret_keys(self):
        with self.assertRaises(CollectorStorageError):
            self.repository.write({"x": {"client_secret": "never-store"}})


class CloudflareTokenConnectorTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "HUB_AUTH_MODE": "cloudflare_access",
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "HUB_COLLECTOR_ACCESS_APP_ID": "app",
                "HUB_COLLECTOR_TOKEN_API_TOKEN": "private-management-token",
                "CLOUDFLARE_ACCESS_POLICY_AUD": "aud",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.connector = CloudflareTokenConnector()

    def test_policy_matches_only_issued_token(self):
        with patch.object(self.connector, "request", return_value={}) as request:
            self.connector.create_policy("collector", "token-id")
        method, path, body = request.call_args.args
        self.assertEqual((method, path), ("POST", "apps/app/policies"))
        self.assertEqual(body["decision"], "non_identity")
        self.assertEqual(body["include"], [{"service_token": {"token_id": "token-id"}}])

    def test_checks_application_audience_before_issuance(self):
        for app in ({"aud": "other", "type": "self_hosted"}, {"aud": "aud", "type": "saas"}):
            with patch.object(self.connector, "request", return_value=app), self.assertRaises(TokenProvisioningError):
                self.connector.verify_application()

    def test_transport_hides_errors_and_never_follows_redirects(self):
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))
        for error in (HTTPError("https://private.invalid", 403, "private-body", {}, None), URLError("private-details")):
            with patch.object(self.connector.opener, "open", side_effect=error), self.assertRaises(TokenProvisioningError) as raised:
                self.connector.create_token("collector", 7)
            self.assertNotIn("private", str(raised.exception))

    def test_delete_already_absent_token_is_idempotent(self):
        with patch.object(self.connector.opener, "open", side_effect=HTTPError("https://private.invalid", 404, "", {}, None)):
            self.assertEqual(self.connector.delete_token("token-id"), {})


class CollectorAccessRoutesTest(CollectorAccessTest):
    def setUp(self):
        super().setUp()
        from ina_device_hub import collector_access_routes, user_context

        self.client = web_server.app.test_client()
        self.user_context = user_context
        self.route_service = patch.object(collector_access_routes, "collector_service", return_value=self.service)
        self.route_service.start()
        self.addCleanup(self.route_service.stop)
        self.auth_environment = patch.dict(
            os.environ,
            {
                "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
                "CLOUDFLARE_ACCESS_POLICY_AUD": "aud",
                "HUB_ADMIN_EMAILS": "admin@example.com",
            },
        )
        self.auth_environment.start()
        self.addCleanup(self.auth_environment.stop)
        self.headers = {user_context.ACCESS_JWT_HEADER: "fake-signed-token", "Sec-Fetch-Site": "same-origin"}

    def test_admin_issues_once_and_list_response_has_no_secret(self):
        with patch.object(self.user_context, "_verify_access_token", return_value={"email": "admin@example.com"}):
            response = self.client.post("/local/api/settings/ai-access", json=self.payload, headers=self.headers)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.get_json()["client_secret"], "one-time-secret")
            self.assertIn("no-store", response.headers["Cache-Control"])
            listing = self.client.get("/local/api/settings/ai-access", headers=self.headers)
            self.assertNotIn("one-time-secret", listing.get_data(as_text=True))
            page = self.client.get("/settings/ai-access", headers=self.headers)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Token を発行", page.get_data(as_text=True))

    def test_operator_and_cross_origin_writes_are_denied(self):
        with patch.object(self.user_context, "_verify_access_token", return_value={"email": "operator@example.com"}):
            self.assertEqual(self.client.post("/local/api/settings/ai-access", json=self.payload, headers=self.headers).status_code, 403)
            self.assertEqual(self.client.get("/settings/ai-access", headers=self.headers).status_code, 403)
        with patch.object(self.user_context, "_verify_access_token", return_value={"email": "admin@example.com"}):
            headers = {**self.headers, "Sec-Fetch-Site": "cross-site"}
            self.assertEqual(self.client.post("/local/api/settings/ai-access", json=self.payload, headers=headers).status_code, 403)
        self.connector.create_token.assert_not_called()

    def test_machine_token_cannot_manage_access_and_cannot_become_writer(self):
        self.issue()
        with patch.object(self.user_context, "_verify_access_token", return_value={"common_name": "collector.access"}):
            self.assertEqual(self.client.post("/local/api/settings/ai-access", json=self.payload, headers=self.headers).status_code, 401)
            self.assertEqual(self.client.get("/operations/api/v1/health", headers=self.headers).status_code, 200)
            self.assertEqual(self.client.get("/operations/api/v1/devices", headers=self.headers).status_code, 403)
            with patch.dict(os.environ, {"HUB_OPERATIONS_SERVICE_IDS": "collector.access"}):
                self.assertEqual(self.client.get("/operations/api/v1/health", headers=self.headers).status_code, 401)

    def test_local_implicit_admin_cannot_issue_token(self):
        with patch.dict(os.environ, {"HUB_AUTH_MODE": "local"}):
            self.assertEqual(self.client.post("/local/api/settings/ai-access", json=self.payload).status_code, 403)
        self.connector.create_token.assert_not_called()
