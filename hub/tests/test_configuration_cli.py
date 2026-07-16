import stat
import tempfile
import unittest
from pathlib import Path

from dotenv import dotenv_values

from ina_device_hub.configuration_cli import DEFAULT_ENV_TEMPLATE_PATH, FIELDS, EnvDocument, configure, install


class ConfigurationCLITest(unittest.TestCase):
    def test_configure_catalog_covers_default_env(self):
        template_keys = set(dotenv_values(DEFAULT_ENV_TEMPLATE_PATH))
        catalog_keys = {field.name for field in FIELDS}

        self.assertEqual(template_keys - catalog_keys, set())

    def test_env_document_preserves_comments_and_writes_secure_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env"
            path.write_text("# storage\nS3_BUCKET_NAME=old\n")
            document = EnvDocument.load(path)

            document.set("S3_BUCKET_NAME", "new bucket")
            document.set("S3_SECRET_KEY", "secret$value")
            document.save(path)

            self.assertIn("# storage", path.read_text())
            self.assertEqual(dotenv_values(path)["S3_BUCKET_NAME"], "new bucket")
            self.assertEqual(dotenv_values(path)["S3_SECRET_KEY"], "secret$value")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_install_builds_env_from_template_interactively(self):
        normal_answers = iter(
            [
                "", "", "", "", "", "", "",
                "libsql://database.example", "",
                "https://account.r2.cloudflarestorage.com", "records", "",
                "", "", "",
            ]
        )
        secret_answers = iter(["turso-token", "r2-access", "r2-secret", "", "", ""])
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env"

            result = install(
                path,
                skip_checks=True,
                input_function=lambda _prompt: next(normal_answers),
                secret_input_function=lambda _prompt: next(secret_answers),
            )

            values = dotenv_values(path)
            self.assertEqual(result, 0)
            self.assertEqual(values["TURSO_DATABASE_URL"], "libsql://database.example")
            self.assertEqual(values["TURSO_AUTH_TOKEN"], "turso-token")
            self.assertEqual(values["S3_BUCKET_NAME"], "records")
            self.assertNotIn("AI_TEXT_ANALYZE_API_KEY", values)

    def test_configure_selects_and_changes_one_value(self):
        answers = iter(["2", "1", "libsql://new.example", "n"])
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env"
            path.write_text("TURSO_DATABASE_URL=libsql://old.example\n")

            result = configure(path, skip_checks=True, input_function=lambda _prompt: next(answers))

            self.assertEqual(result, 0)
            self.assertEqual(dotenv_values(path)["TURSO_DATABASE_URL"], "libsql://new.example")


if __name__ == "__main__":
    unittest.main()
