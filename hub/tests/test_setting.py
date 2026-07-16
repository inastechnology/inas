import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "libsql://environment.example")
os.environ.setdefault("TURSO_AUTH_TOKEN", "environment-turso-token")
os.environ.setdefault("S3_ENDPOINT_URL", "https://storage.example")
os.environ.setdefault("S3_BUCKET_NAME", "bucket")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "environment-access-key")
os.environ.setdefault("S3_SECRET_KEY", "environment-secret-key")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.setting import DEFAULT_SETTINGS, Setting  # noqa: E402


class SettingTest(unittest.TestCase):
    def test_legacy_file_is_normalized_without_loading_secrets_or_infrastructure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "ai": {
                            "enabled": True,
                            "agent_schedule_start": "07:45",
                            "text_analyze_model": "runtime-model",
                            "text_analyze_api_key": "legacy-secret",
                        },
                        "application": {"default_language": "en"},
                        "turso": {"database_url": "libsql://legacy.example", "auth_token": "legacy-token"},
                    }
                )
            )

            current = Setting(path)

            self.assertEqual(current.get("ai")["text_analyze_model"], "runtime-model")
            self.assertEqual(current.get("ai")["text_analyze_api_key"], DEFAULT_SETTINGS["ai"]["text_analyze_api_key"])
            self.assertEqual(current.get("instagram")["post_schedule_start"], "07:45")
            self.assertIsNone(current.get("application"))
            self.assertEqual(current.get("turso"), DEFAULT_SETTINGS["turso"])
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["schema_version"], 1)
            self.assertNotIn("text_analyze_api_key", persisted["ai"])
            self.assertNotIn("agent_schedule_start", persisted["ai"])
            self.assertEqual(persisted["instagram"]["post_schedule_start"], "07:45")
            self.assertNotIn("application", persisted)
            self.assertNotIn("turso", persisted)

    def test_runtime_save_uses_allowlist_and_secure_permissions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.json"
            current = Setting(path)

            current.set(
                "ai",
                {
                    "enabled": True,
                    "text_analyze_model": "gpt-test",
                    "text_analyze_api_key": "must-not-be-persisted",
                },
            )

            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["ai"]["text_analyze_model"], "gpt-test")
            self.assertNotIn("text_analyze_api_key", persisted["ai"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_non_runtime_section_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            current = Setting(Path(temporary_directory) / "config.json")
            with self.assertRaises(ValueError):
                current.set("turso", {"auth_token": "changed"})
            with self.assertRaises(ValueError):
                current.set("application", {"default_language": "en"})

    def test_runtime_secret_is_stored_separately_and_never_in_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            secret_path = Path(temporary_directory) / "runtime-secrets.json"
            current = Setting(config_path, secret_path)

            current.set("ai", {"text_analyze_model": "gpt-test"})
            current.set_secret("ai", "text_analyze_api_key", "gui-secret-value")

            self.assertTrue(current.secret_configured("ai", "text_analyze_api_key"))
            self.assertNotIn("gui-secret-value", config_path.read_text())
            self.assertIn("gui-secret-value", secret_path.read_text())
            self.assertEqual(stat.S_IMODE(secret_path.stat().st_mode), 0o600)
            reloaded = Setting(config_path, secret_path)
            self.assertEqual(reloaded.get("ai")["text_analyze_api_key"], "gui-secret-value")

    def test_explicitly_cleared_runtime_secret_overrides_environment_fallback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            secret_path = Path(temporary_directory) / "runtime-secrets.json"
            current = Setting(config_path, secret_path)

            current.set_secret("ai", "text_analyze_api_key", "")

            reloaded = Setting(config_path, secret_path)
            self.assertEqual(reloaded.get("ai")["text_analyze_api_key"], "")
            self.assertFalse(reloaded.secret_configured("ai", "text_analyze_api_key"))


if __name__ == "__main__":
    unittest.main()
