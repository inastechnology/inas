import os
import tempfile
import unittest
from pathlib import Path

from ina_edge_gateway.mqtt_client import _read_credential_file
from ina_edge_gateway.sync_client import _read_secret


class CredentialFileTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_node_token_requires_exact_url_safe_shape(self):
        token_file = self._private_file("node-token", "A" * 43)
        self.assertEqual(_read_secret(token_file), "A" * 43)

        local_token = f"inas_sync_v1_{'B' * 43}"
        token_file.write_text(local_token, encoding="utf-8")
        self.assertEqual(_read_secret(token_file), local_token)

        token_file.write_text("short-token", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cloud token"):
            _read_secret(token_file)

        token_file.write_text(("A" * 43) + (" " * 200), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "too large"):
            _read_secret(token_file)

    def test_node_token_rejects_group_access(self):
        token_file = self._private_file("node-token", "A" * 43)
        os.chmod(token_file, 0o640)

        with self.assertRaises(PermissionError):
            _read_secret(token_file)

    def test_node_and_mqtt_credentials_reject_symbolic_links(self):
        target = self._private_file("credential-target", "A" * 43)
        link = self.root / "credential-link"
        link.symlink_to(target)

        with self.assertRaises(OSError):
            _read_secret(link)
        with self.assertRaises(OSError):
            _read_credential_file(link, field_name="MQTT password")

    def test_mqtt_credential_requires_regular_private_file(self):
        with self.assertRaisesRegex(ValueError, "regular file"):
            _read_credential_file(self.root, field_name="MQTT password")

        credential_file = self._private_file("mqtt-password", "secret")
        self.assertEqual(
            _read_credential_file(credential_file, field_name="MQTT password"),
            "secret",
        )
        credential_file.write_text("x" * 5000, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "too large"):
            _read_credential_file(credential_file, field_name="MQTT password")

    def _private_file(self, name: str, value: str) -> Path:
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
        return path


if __name__ == "__main__":
    unittest.main()
