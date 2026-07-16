import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_admin_demo_server.py"
SPEC = importlib.util.spec_from_file_location("run_admin_demo_server", SCRIPT_PATH)
run_admin_demo_server = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(run_admin_demo_server)


class AdminDemoServerTest(unittest.TestCase):
    def test_demo_environment_does_not_inherit_external_turso_or_ai(self):
        inherited = {
            "TURSO_DATABASE_URL": "libsql://production.example",
            "TURSO_AUTH_TOKEN": "production-token",
            "AI_ENABLED": "true",
            "AI_IMAGE_ANALYZE_API_KEY": "production-image-key",
            "AI_TEXT_ANALYZE_API_KEY": "production-text-key",
        }
        with patch.dict(os.environ, inherited, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "local-demo")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "local-demo")
            self.assertEqual(os.environ["AI_ENABLED"], "false")
            self.assertEqual(os.environ["AI_IMAGE_ANALYZE_API_KEY"], "")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "")

    def test_demo_specific_values_require_explicit_prefix(self):
        overrides = {
            "HUB_DEMO_TURSO_DATABASE_URL": "libsql://demo.example",
            "HUB_DEMO_TURSO_AUTH_TOKEN": "demo-token",
            "HUB_DEMO_AI_TEXT_ANALYZE_API_KEY": "demo-ai-key",
        }
        with patch.dict(os.environ, overrides, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "libsql://demo.example")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "demo-token")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "demo-ai-key")


if __name__ == "__main__":
    unittest.main()
