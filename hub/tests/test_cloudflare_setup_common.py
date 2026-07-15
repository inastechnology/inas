import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_PATH = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_PATH))

from cloudflare_setup_common import (  # noqa: E402
    ScriptError,
    merged_env,
    parse_env_file,
    quote_env_value,
    require_any_value,
    require_value,
    upsert_env_file,
)


class CloudflareSetupCommonTest(unittest.TestCase):
    def test_parse_env_file_accepts_export_and_quoted_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text(
                "# comment\nexport ACCOUNT_ID=account-1\nDISPLAY_NAME=\"Ina Hub\"\nIGNORED\n",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_env_file(env_file),
                {"ACCOUNT_ID": "account-1", "DISPLAY_NAME": "Ina Hub"},
            )

    def test_merged_env_prefers_process_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text("ACCOUNT_ID=file-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"ACCOUNT_ID": "process-value"}, clear=False):
                self.assertEqual(merged_env(env_file)["ACCOUNT_ID"], "process-value")

    def test_upsert_env_file_preserves_comments_and_updates_exports(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text("# Cloudflare\nexport ACCOUNT_ID=old\nKEEP=value\n", encoding="utf-8")

            upsert_env_file(env_file, {"ACCOUNT_ID": "new value", "HOSTNAME": "hub.example.com"})

            self.assertEqual(
                env_file.read_text(encoding="utf-8"),
                '# Cloudflare\nACCOUNT_ID="new value"\nKEEP=value\n\nHOSTNAME=hub.example.com\n',
            )

    def test_required_values_report_missing_keys(self):
        self.assertEqual(require_value({"ACCOUNT_ID": " value "}, "ACCOUNT_ID"), "value")
        self.assertEqual(require_any_value({"TOKEN_B": " token "}, ["TOKEN_A", "TOKEN_B"]), "token")
        with self.assertRaisesRegex(ScriptError, "ACCOUNT_ID"):
            require_value({}, "ACCOUNT_ID")
        with self.assertRaisesRegex(ScriptError, "TOKEN_A, TOKEN_B"):
            require_any_value({}, ["TOKEN_A", "TOKEN_B"])

    def test_quote_env_value_only_quotes_when_required(self):
        self.assertEqual(quote_env_value("hub.example.com"), "hub.example.com")
        self.assertEqual(quote_env_value("Ina Hub"), '"Ina Hub"')


if __name__ == "__main__":
    unittest.main()
