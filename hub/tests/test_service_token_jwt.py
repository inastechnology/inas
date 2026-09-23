"""Regression coverage using signed JWTs with Cloudflare's actual service shape."""

import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, request

from ina_device_hub import user_context


class ServiceTokenJwtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.issuer = "https://team.cloudflareaccess.com"

    def setUp(self):
        now = int(time.time())
        self.claims = {"type": "app", "aud": ["test-audience"], "iss": self.issuer, "exp": now + 300, "iat": now, "sub": "", "common_name": "collector.access"}
        self.client = patch.object(user_context, "_jwk_client").start().return_value
        self.client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
        self.addCleanup(patch.stopall)

    def token(self, **changes):
        return jwt.encode({**self.claims, **changes}, self.key, algorithm="RS256")

    def verify(self, token):
        return user_context._verify_access_token(token, self.issuer, "test-audience", service_token=True)

    def test_accepts_signed_service_token_with_empty_subject_and_no_nbf(self):
        self.assertEqual(self.verify(self.token())["common_name"], "collector.access")

    def test_preserves_signature_audience_issuer_and_time_validation(self):
        for changes in (
            {"aud": ["wrong"]},
            {"iss": "https://other.cloudflareaccess.com"},
            {"exp": int(time.time()) - 30},
            {"iat": int(time.time()) + 60},
            {"nbf": int(time.time()) + 60},
        ):
            with self.subTest(changes=changes), self.assertRaises(jwt.InvalidTokenError):
                self.verify(self.token(**changes))
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(jwt.InvalidSignatureError):
            self.verify(jwt.encode(self.claims, other, algorithm="RS256"))

    def test_rejects_missing_or_invalid_service_identity_and_claims(self):
        for changes in (
            {"common_name": ""},
            {"common_name": None},
            {"common_name": "bad\nidentity"},
            {"type": "org"},
            {"iat": True},
            {"nbf": None},
            {"nbf": True},
            {"sub": None},
        ):
            with self.subTest(changes=changes), self.assertRaises((jwt.InvalidTokenError, user_context.AccessAuthenticationError, TypeError)):
                self.verify(self.token(**changes))
        for missing in ("sub", "exp", "iat", "common_name"):
            claims = {k: v for k, v in self.claims.items() if k != missing}
            with self.subTest(missing=missing), self.assertRaises((jwt.InvalidTokenError, user_context.AccessAuthenticationError)):
                self.verify(jwt.encode(claims, self.key, algorithm="RS256"))

    def test_human_verification_stays_strict(self):
        with self.assertRaises(jwt.MissingRequiredClaimError):
            user_context._verify_access_token(self.token(), self.issuer, "test-audience")
        with self.assertRaises(user_context.AccessAuthenticationError):
            user_context._verify_access_token(self.token(nbf=self.claims["iat"]), self.issuer, "test-audience")
        human = self.token(sub="human-id", nbf=self.claims["iat"], email="user@example.com")
        self.assertEqual(user_context._verify_access_token(human, self.issuer, "test-audience")["sub"], "human-id")

    def test_signed_service_token_still_requires_grant_and_separate_identity(self):
        app = Flask(__name__)
        settings = {
            "HUB_AUTH_MODE": "cloudflare_access",
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN": self.issuer,
            "CLOUDFLARE_ACCESS_POLICY_AUD": "test-audience",
            "HUB_OPERATIONS_SERVICE_IDS": "",
            "HUB_OPERATIONS_READ_GRANTS": json.dumps({"collector.access": {"scopes": ["records:read", "images:read"], "field_ids": ["field-a"]}}),
        }
        with patch.dict(os.environ, settings), app.test_request_context("/operations/api/v1/health", headers={user_context.ACCESS_JWT_HEADER: self.token()}):
            self.assertEqual(user_context.authenticate_request(request).role, "collector")
        for overrides in ({"HUB_OPERATIONS_READ_GRANTS": "{}"}, {"HUB_OPERATIONS_SERVICE_IDS": "collector.access"}):
            with (
                patch.dict(os.environ, {**settings, **overrides}),
                app.test_request_context("/operations/api/v1/health", headers={user_context.ACCESS_JWT_HEADER: self.token()}),
            ):
                with self.assertRaises(user_context.AccessAuthenticationError):
                    user_context.authenticate_request(request)
