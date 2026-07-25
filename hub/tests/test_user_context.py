import os
import unittest
from unittest.mock import patch

from flask import Flask, request

from ina_device_hub import user_context


class UserContextTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_local_mode_keeps_explicit_local_admin_fallback(self):
        with patch.dict(os.environ, {"HUB_AUTH_MODE": "local", "HUB_LOCAL_USER_EMAIL": "local@example.com"}, clear=False):
            with self.app.test_request_context("/"):
                current = user_context.authenticate_request(request)

        self.assertEqual(current.email, "local@example.com")
        self.assertEqual(current.role, "admin")
        self.assertFalse(current.authenticated)

    def test_cloudflare_mode_rejects_missing_jwt(self):
        with patch.dict(os.environ, {"HUB_AUTH_MODE": "cloudflare_access"}, clear=False):
            with self.app.test_request_context("/"):
                with self.assertRaises(user_context.AccessAuthenticationError):
                    user_context.authenticate_request(request)

    def test_cloudflare_mode_uses_verified_email_and_role(self):
        environment = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "HUB_ADMIN_EMAILS": "admin@example.com",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "team.cloudflareaccess.com",
            "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
        }
        headers = {
            user_context.ACCESS_JWT_HEADER: "signed-token",
            user_context.ACCESS_EMAIL_HEADER: "admin@example.com",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(
                user_context,
                "_verify_access_token",
                return_value={"email": "admin@example.com"},
            ),
        ):
            with self.app.test_request_context("/", headers=headers):
                current = user_context.authenticate_request(request)

        self.assertTrue(current.authenticated)
        self.assertEqual(current.email, "admin@example.com")
        self.assertEqual(current.role, "admin")

    def test_cloudflare_mode_rejects_mismatched_identity_headers(self):
        environment = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
            "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
        }
        headers = {
            user_context.ACCESS_JWT_HEADER: "signed-token",
            user_context.ACCESS_EMAIL_HEADER: "other@example.com",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(
                user_context,
                "_verify_access_token",
                return_value={"email": "worker@example.com"},
            ),
        ):
            with self.app.test_request_context("/", headers=headers):
                with self.assertRaises(user_context.AccessAuthenticationError):
                    user_context.authenticate_request(request)

    def test_access_configuration_accepts_only_cloudflare_https_origin(self):
        self.assertEqual(
            user_context._normalized_team_domain("team.cloudflareaccess.com"),
            "https://team.cloudflareaccess.com",
        )
        for value in (
            "http://team.cloudflareaccess.com",
            "https://team.cloudflareaccess.com/path",
            "https://user@team.cloudflareaccess.com",
            "https://bad..cloudflareaccess.com",
            "https://example.com",
        ):
            self.assertEqual(user_context._normalized_team_domain(value), "")

    def test_access_application_claims_require_type_subject_and_times(self):
        valid = {
            "type": "app",
            "sub": "access-user-123",
            "iat": 1_000,
            "nbf": 1_000,
            "exp": 1_100,
        }
        user_context._validate_access_application_claims(valid)
        for invalid in (
            {**valid, "type": "org"},
            {**valid, "sub": ""},
            {**valid, "exp": 999},
            {**valid, "nbf": 1_101},
        ):
            with self.assertRaises(user_context.AccessAuthenticationError):
                user_context._validate_access_application_claims(invalid)


if __name__ == "__main__":
    unittest.main()
