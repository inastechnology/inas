import os
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "local")
os.environ.setdefault("TURSO_AUTH_TOKEN", "local")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub import ina_db_connector  # noqa: E402


class InaDBConnectorTest(unittest.TestCase):
    def test_singleton_accessor_reuses_one_connector(self):
        previous = ina_db_connector.__dict__["__instance"]
        connector = object()
        ina_db_connector.__dict__["__instance"] = None
        try:
            with patch.object(ina_db_connector, "InaDBConnector", return_value=connector) as constructor:
                first = ina_db_connector.ina_db_connector()
                second = ina_db_connector.ina_db_connector()

            self.assertIs(first, connector)
            self.assertIs(second, connector)
            constructor.assert_called_once_with()
        finally:
            ina_db_connector.__dict__["__instance"] = previous

    def test_user_note_insert_uses_bound_parameters(self):
        connector = object.__new__(ina_db_connector.InaDBConnector)
        connector._operation_lock = threading.RLock()
        connector.conn = MagicMock()

        connector.insert_user_note('device"; DROP TABLE user_note; --', 'note"')

        connector.conn.execute.assert_called_once_with(
            "INSERT INTO user_note (device_id, note) VALUES (?, ?)",
            ('device"; DROP TABLE user_note; --', 'note"'),
        )

    def test_database_operations_share_one_lock(self):
        connector = object.__new__(ina_db_connector.InaDBConnector)
        connector._operation_lock = threading.RLock()
        connector.conn = MagicMock()
        started = threading.Event()
        completed = threading.Event()

        def insert_note():
            started.set()
            connector.insert_user_note("device", "note")
            completed.set()

        with connector.operation():
            worker = threading.Thread(target=insert_note)
            worker.start()
            self.assertTrue(started.wait(timeout=1))
            self.assertFalse(completed.wait(timeout=0.05))

        self.assertTrue(completed.wait(timeout=1))
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())

    def test_remote_replica_uses_configured_background_sync_interval(self):
        connection = object()
        with patch.object(ina_db_connector.libsql, "connect", return_value=connection) as connect:
            result = ina_db_connector._connect_database(
                "/tmp/ina.db",
                "libsql://database.example",
                "token",
                45,
            )

        self.assertIs(result, connection)
        connect.assert_called_once_with(
            "/tmp/ina.db",
            sync_url="libsql://database.example",
            auth_token="token",
            sync_interval=45,
        )

    def test_local_database_does_not_enable_replica_sync(self):
        connection = object()
        with patch.object(ina_db_connector.libsql, "connect", return_value=connection) as connect:
            result = ina_db_connector._connect_database("/tmp/ina.db", "local-demo", "unused", 45)

        self.assertIs(result, connection)
        connect.assert_called_once_with("/tmp/ina.db")


if __name__ == "__main__":
    unittest.main()
