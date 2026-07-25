import json
import os
import tempfile
import unittest
from pathlib import Path

from ina_edge_runtime import NodeType, parse_node_id

from ina_edge_gateway.config import load_gateway_config
from ina_edge_gateway.identity import bootstrap_development_identity, load_edge_identity

ROOT = Path(__file__).resolve().parents[1]


class ConfigAndIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.identity_path = self.root / "identity.json"
        self.token_path = self.root / "parent-token"
        self.token_path.write_text("test-token", encoding="utf-8")
        os.chmod(self.token_path, 0o600)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_development_identity_is_created_once_as_edge_gateway(self):
        first = bootstrap_development_identity(self.identity_path)
        second = bootstrap_development_identity(self.identity_path)

        self.assertEqual(first, second)
        self.assertEqual(load_edge_identity(self.identity_path), first)
        self.assertEqual(parse_node_id(first).node_type, NodeType.EDGE_GATEWAY)
        self.assertEqual(self.identity_path.stat().st_mode & 0o777, 0o600)

    def test_loads_strict_config_without_secret_values(self):
        bootstrap_development_identity(self.identity_path)
        config_path = self._write_config()

        config = load_gateway_config(config_path)

        self.assertEqual(config.identity_file, self.identity_path)
        self.assertEqual(config.store_path, self.root / "edge.db")
        self.assertEqual(config.parent.exchange_url("INAEG-node"), "https://parent.example/sync/v1/nodes/INAEG-node/exchange")
        self.assertEqual(config.capabilities, ("mqtt", "wifi_ap", "ntp"))

    def test_rejects_unknown_routing_and_non_https_remote_parent(self):
        document = self._config_document()
        document["tenant_id"] = "caller-must-not-route"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            load_gateway_config(self._write_document(document))

        document = self._config_document()
        document["parent"]["base_url"] = "http://parent.example"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            load_gateway_config(self._write_document(document))

    def test_rejects_credentials_embedded_in_parent_url(self):
        document = self._config_document()
        document["parent"]["base_url"] = "https://node:secret@parent.example"

        with self.assertRaisesRegex(ValueError, "must not embed credentials"):
            load_gateway_config(self._write_document(document))

    def test_parent_requires_node_bearer_even_when_mtls_is_configured(self):
        document = self._config_document()
        document["parent"]["bearer_token_file"] = None
        document["parent"]["client_certificate_file"] = str(self.root / "client.crt")
        document["parent"]["client_key_file"] = str(self.root / "client.key")

        with self.assertRaisesRegex(ValueError, "node bearer token file"):
            load_gateway_config(self._write_document(document))

    def test_repository_example_is_schema_valid_and_starts_unclaimed(self):
        config = load_gateway_config(ROOT / "config" / "edge-gateway.example.json")

        self.assertIsNone(config.parent)
        self.assertEqual(config.mqtt.host, "192.168.50.1")
        self.assertNotIn("device_ota", config.capabilities)

    def _write_config(self):
        return self._write_document(self._config_document())

    def _write_document(self, document):
        path = self.root / "edge-gateway.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def _config_document(self):
        return {
            "schema_version": 1,
            "data_directory": str(self.root),
            "identity_file": str(self.identity_path),
            "hardware_profile_id": "egw-rpi5-development-r0",
            "software_version": "0.1.0",
            "capabilities": ["mqtt", "wifi_ap", "ntp"],
            "mqtt": {
                "host": "127.0.0.1",
                "port": 1883,
                "username_file": None,
                "password_file": None,
                "keepalive_seconds": 60,
            },
            "parent": {
                "base_url": "https://parent.example",
                "bearer_token_file": str(self.token_path),
                "ca_file": None,
                "client_certificate_file": None,
                "client_key_file": None,
                "timeout_seconds": 20,
                "max_response_bytes": 1048576,
                "allow_insecure_http": False,
            },
            "health": {"bind_host": "127.0.0.1", "port": 0},
        }


if __name__ == "__main__":
    unittest.main()
