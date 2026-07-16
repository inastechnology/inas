import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cloudflare_access_setup.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("cloudflare_access_setup", SCRIPT_PATH)
cloudflare_access_setup = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(cloudflare_access_setup)


class CloudflareAccessSetupTest(unittest.TestCase):
    def test_email_domain_normalization(self):
        self.assertEqual(cloudflare_access_setup.normalize_email_domain(" @Example.COM "), "example.com")
        with self.assertRaises(cloudflare_access_setup.ScriptError):
            cloudflare_access_setup.normalize_email_domain("https://example.com")

    def test_group_payload_only_keeps_explicit_email_identities(self):
        existing = {
            "include": [{"everyone": {}}, {"email_domain": {"domain": "legacy.example"}}],
            "exclude": [{"email": {"email": "retired@example.com"}}],
        }

        payload = cloudflare_access_setup.group_payload(
            "company-users",
            ["worker@example.com"],
            existing,
            ["example.com"],
        )

        self.assertEqual(
            payload["include"],
            [
                {"email": {"email": "worker@example.com"}},
                {"email_domain": {"domain": "example.com"}},
            ],
        )
        self.assertEqual(payload["exclude"], existing["exclude"])

    def test_updating_exact_emails_preserves_company_domain(self):
        existing = {"include": [{"email_domain": {"domain": "example.com"}}]}
        payload = cloudflare_access_setup.group_payload("company-users", [], existing)
        self.assertEqual(payload["include"], [{"email_domain": {"domain": "example.com"}}])


if __name__ == "__main__":
    unittest.main()
