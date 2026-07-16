import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from ina_device_hub import cli
from ina_device_hub.configuration_cli import (
    DEFAULT_ENV_TEMPLATE_PATH,
    FIELDS,
    EnvDocument,
    _check_mqtt,
    _check_turso,
    _effective_values,
    check_configuration,
    configure,
    install,
)
from ina_device_hub.mqtt_contract import MQTT_KEEPALIVE_SECONDS, MQTT_PROTOCOL, MQTT_TRANSPORT


class ConfigurationCLITest(unittest.TestCase):
    def test_backup_defaults_to_the_configured_work_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            work_dir = root / "custom-work"
            env_path.write_text(f"WORK_DIR={work_dir}\nHUB_BACKUP_RETENTION=7\n")
            archive = work_dir / "backups" / "ina-hub-state-test.tar.gz"

            with patch.object(cli, "create_state_backup", return_value=archive) as create_backup:
                result = cli.main(["backup", "--env-file", str(env_path)])

            self.assertEqual(result, 0)
            create_backup.assert_called_once_with(str(work_dir), str(work_dir / "backups"), retention=7)

    def test_mqtt_check_uses_the_runtime_wire_contract(self):
        client = unittest.mock.MagicMock()

        class AcceptedReasonCode:
            is_failure = False

        def report_connected():
            client.on_connect(client, None, None, AcceptedReasonCode(), None)

        client.loop_start.side_effect = report_connected
        values = {
            "MQTT_BROKER_URL": "broker.example",
            "MQTT_BROKER_PORT": "1883",
            "MQTT_BROKER_USERNAME": "",
            "MQTT_BROKER_PASSWORD": "ignored-without-username",
        }

        with patch("ina_device_hub.configuration_cli.mqtt.Client", return_value=client) as client_factory:
            result = _check_mqtt(values)

        client_factory.assert_called_once_with(
            unittest.mock.ANY,
            client_id="ina-hub-configuration-check",
            protocol=MQTT_PROTOCOL,
            transport=MQTT_TRANSPORT,
        )
        client.username_pw_set.assert_not_called()
        client.connect.assert_called_once_with("broker.example", 1883, keepalive=MQTT_KEEPALIVE_SECONDS)
        client.disconnect.assert_called_once_with()
        client.loop_stop.assert_called_once_with()
        self.assertEqual(result, "MQTTブローカーへの接続を確認しました")

    def test_turso_check_removes_replica_and_all_sidecars(self):
        replica_directories = []

        class FakeCursor:
            def fetchone(self):
                return (1,)

        class FakeConnection:
            def __init__(self, path):
                self.path = Path(path)

            def sync(self):
                self.path.write_bytes(b"database")
                self.path.with_name(f"{self.path.name}-info").write_bytes(b"metadata")
                self.path.with_name(f"{self.path.name}-wal").write_bytes(b"wal")
                replica_directories.append(self.path.parent)

            def execute(self, _query):
                return FakeCursor()

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary_directory:
            values = {
                "WORK_DIR": temporary_directory,
                "TURSO_DATABASE_URL": "libsql://database.example",
                "TURSO_AUTH_TOKEN": "token",
                "TURSO_SYNC_INTERVAL": "600",
            }
            with patch("ina_device_hub.configuration_cli.libsql.connect", side_effect=lambda path, **_kwargs: FakeConnection(path)):
                result = _check_turso(values)

            self.assertEqual(result, "Tursoへの接続と同期を確認しました")
            self.assertEqual(len(replica_directories), 1)
            self.assertFalse(replica_directories[0].exists())

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
        def normal_answer(prompt):
            if "TURSO_DATABASE_URL" in prompt:
                return "libsql://database.example"
            if "S3_ENDPOINT_URL" in prompt:
                return "https://account.r2.cloudflarestorage.com"
            if "S3_BUCKET_NAME" in prompt:
                return "records"
            return ""

        def secret_answer(prompt):
            if "TURSO_AUTH_TOKEN" in prompt:
                return "turso-token"
            if "S3_ACCESS_KEY" in prompt:
                return "r2-access"
            if "S3_SECRET_KEY" in prompt:
                return "r2-secret"
            return ""

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env"

            result = install(
                path,
                skip_checks=True,
                input_function=normal_answer,
                secret_input_function=secret_answer,
            )

            values = dotenv_values(path)
            self.assertEqual(result, 0)
            self.assertEqual(values["TURSO_DATABASE_URL"], "libsql://database.example")
            self.assertEqual(values["TURSO_AUTH_TOKEN"], "turso-token")
            self.assertEqual(values["S3_BUCKET_NAME"], "records")
            self.assertNotIn("AI_TEXT_ANALYZE_API_KEY", values)

    def test_production_check_requires_private_loopback_access_configuration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / ".env"
            document = EnvDocument.load(path)
            production_values = {
                "WORK_DIR": str(root / "work"),
                "LOCAL_STORAGE_BASE_DIR": str(root / "storage"),
                "HUB_HTTP_HOST": "127.0.0.1",
                "HUB_HTTP_SERVER": "waitress",
                "HUB_AUTH_MODE": "cloudflare_access",
                "HUB_ADMIN_EMAILS": "admin@example.com",
                "TURSO_DATABASE_URL": "local",
                "TURSO_AUTH_TOKEN": "token",
                "S3_ENDPOINT_URL": "https://storage.example",
                "S3_BUCKET_NAME": "records",
                "S3_ACCESS_KEY": "access",
                "S3_SECRET_KEY": "secret",
                "MQTT_BROKER_URL": "localhost",
                "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://team.cloudflareaccess.com",
                "CLOUDFLARE_ACCESS_POLICY_AUD": "audience",
                "CLOUDFLARE_TUNNEL_ORIGIN_URL": "http://localhost:39151",
            }
            for key, value in production_values.items():
                document.set(key, value)
            document.save(path)

            result = check_configuration(path, production=True, skip_connections=True)

            self.assertEqual(result, 0)

            document = EnvDocument.load(path)
            document.set("HUB_HTTP_HOST", "0.0.0.0")
            document.save(path)

            self.assertEqual(check_configuration(path, production=True, skip_connections=True), 0)

    def test_check_accepts_env_created_before_http_security_settings_existed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / ".env"
            path.write_text(
                "\n".join(
                    (
                        f"WORK_DIR={root / 'work'}",
                        "TURSO_DATABASE_URL=local",
                        "TURSO_AUTH_TOKEN=token",
                        "S3_ENDPOINT_URL=https://storage.example",
                        "S3_BUCKET_NAME=records",
                        "S3_BUCKET_REGION=auto",
                        "S3_ACCESS_KEY=access",
                        "S3_SECRET_KEY=secret",
                        "MQTT_BROKER_URL=localhost",
                        "MQTT_BROKER_PORT=1883",
                        "MQTT_BROKER_USERNAME=",
                        "MQTT_BROKER_PASSWORD=",
                        "TIMELAPSE_INTERVAL=600",
                    )
                )
                + "\n"
            )
            path.chmod(0o600)

            self.assertEqual(check_configuration(path, skip_connections=True), 0)
            values = _effective_values(EnvDocument.load(path))
            self.assertEqual(values["HUB_HTTP_HOST"], "0.0.0.0")
            self.assertEqual(values["HUB_HTTP_SERVER"], "flask")
            self.assertEqual(values["HUB_AUTH_MODE"], "local")
            self.assertEqual(values["MQTT_BROKER_URL"], "localhost")
            self.assertEqual(values["MQTT_BROKER_PORT"], "1883")
            self.assertNotIn("MQTT_TLS_ENABLED", values)

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
