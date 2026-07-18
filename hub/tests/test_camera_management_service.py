import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")

from ina_device_hub.camera_connector import CameraConnector  # noqa: E402
from ina_device_hub.camera_credential_repository import CameraCredentialRepository  # noqa: E402
from ina_device_hub.camera_device_repository import CameraDeviceRepository  # noqa: E402
from ina_device_hub.camera_management_service import (  # noqa: E402
    CameraManagementService,
    CameraRemovalConflictError,
    CameraValidationError,
)


class _Fields:
    def __init__(self, records=None):
        self.records = records or []

    def list(self):
        return self.records


class _Layouts:
    def __init__(self, layouts=None):
        self.layouts = layouts or {}

    def get(self, field_id, field_name=""):
        del field_name
        return self.layouts.get(field_id, {"spaces": []})


class _Settings:
    def __init__(self, camera_id=""):
        self.camera_id = camera_id

    def get(self, section):
        return {"camera_id": self.camera_id} if section == "instagram" else {}


class CameraManagementServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = CameraDeviceRepository()
        self.repository.camera_device_repo_path = os.path.join(self.tmp_dir.name, ".camera_device_list.json")
        self.repository.camera_dict = {}
        self.repository.save()
        self.credentials = CameraCredentialRepository()
        self.credentials.credential_path = os.path.join(self.tmp_dir.name, ".camera_credentials.json")
        self.credentials.credentials = {}
        self.events = []
        self.tested = []
        self.service = self._service()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _service(self, *, fields=None, layouts=None, camera_id=""):
        def tester(info):
            self.tested.append(info)
            return {"ok": True, "message": "connected"}

        return CameraManagementService(
            repository=self.repository,
            credential_repository=self.credentials,
            field_repo=_Fields(fields),
            layout_repo=_Layouts(layouts),
            settings=_Settings(camera_id),
            connection_tester=tester,
            event_writer=lambda *args, **kwargs: self.events.append((args, kwargs)),
        )

    @staticmethod
    def _payload(**overrides):
        return {
            "name": "ハウス東側",
            "camera_type": "reolink",
            "ip_address": "192.168.1.84",
            "port": 554,
            "username": "camera-user",
            "password": "camera-password",
            "channel": 1,
            "stream": "main",
            "timelapse": True,
            **overrides,
        }

    def test_create_separates_credentials_and_redacts_password(self):
        created = self.service.create(self._payload())

        metadata = self.repository.get(created["id"])
        stored_credentials = self.credentials.get(created["id"])
        self.assertEqual(created["username"], "camera-user")
        self.assertNotIn("password", created)
        self.assertNotIn("username", metadata)
        self.assertNotIn("password", metadata)
        self.assertEqual(stored_credentials, {"username": "camera-user", "password": "camera-password"})
        self.assertEqual(os.stat(self.credentials.credential_path).st_mode & 0o777, 0o600)

    def test_update_with_blank_password_keeps_secret_and_migrates_legacy_record(self):
        device_id = "INACD-legacy"
        self.repository.upsert(
            device_id,
            {
                "id": device_id,
                "name": "legacy",
                "camera_type": "reolink",
                "ip_address": "192.168.1.84",
                "username": "legacy-user",
                "password": "legacy-password",
            },
        )

        updated = self.service.update(device_id, {"name": "renamed", "password": ""})

        self.assertEqual(updated["name"], "renamed")
        self.assertEqual(updated["username"], "legacy-user")
        self.assertEqual(self.credentials.get(device_id)["password"], "legacy-password")
        self.assertNotIn("password", self.repository.get(device_id))
        self.assertNotIn("username", self.repository.get(device_id))

    def test_connection_test_uses_existing_password_without_returning_it(self):
        created = self.service.create(self._payload())

        result = self.service.test_connection({**self._payload(name="changed"), "password": ""}, device_id=created["id"])

        self.assertEqual(result, {"ok": True, "message": "connected"})
        self.assertEqual(self.tested[-1]["password"], "camera-password")

    def test_delete_is_blocked_by_field_layout_and_instagram_references(self):
        created = self.service.create(self._payload())
        device_id = created["id"]
        self.service = self._service(
            fields=[{"id": "field-1", "name": "東圃場", "camera_device_ids": [device_id]}],
            layouts={
                "field-1": {
                    "spaces": [
                        {
                            "id": "space-1",
                            "name": "ハウス",
                            "placements": [{"id": "camera-placement", "name": "定点", "binding": {"resource_type": "camera", "device_id": device_id}}],
                        }
                    ]
                }
            },
            camera_id=device_id,
        )

        with self.assertRaises(CameraRemovalConflictError) as raised:
            self.service.delete(device_id)

        self.assertEqual({item["type"] for item in raised.exception.references}, {"field", "layout", "instagram"})
        self.assertIsNotNone(self.repository.get(device_id))

    def test_custom_camera_requires_rtsp_path(self):
        with self.assertRaises(CameraValidationError):
            self.service.create(self._payload(camera_type="custom", rtsp_path=""))

    def test_public_record_never_contains_password_from_legacy_json(self):
        device_id = "INACD-legacy"
        self.repository.upsert(device_id, {**self._payload(), "id": device_id})

        record = self.service.get(device_id)
        serialized = json.dumps(record)

        self.assertNotIn("camera-password", serialized)
        self.assertNotIn('"password"', serialized)


class CameraConnectorTest(unittest.TestCase):
    def test_reolink_url_supports_port_and_escapes_credentials(self):
        url = CameraConnector.get_rtsp_url("192.168.1.84", "camera user", "p@ss", port=8554, camera_type="reolink", channel=2, stream="sub")

        self.assertEqual(url, "rtsp://camera%20user:p%40ss@192.168.1.84:8554/Preview_02_sub")

    @patch("ina_device_hub.camera_connector.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("ina_device_hub.camera_connector.subprocess.run")
    @patch("ina_device_hub.camera_connector.socket.getaddrinfo")
    def test_connection_test_fetches_one_frame_from_private_address(self, getaddrinfo, run, _which):
        getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.84", 554))]
        run.return_value = subprocess.CompletedProcess([], 0, stdout=b"jpeg", stderr=b"")
        connector = CameraConnector(camera_repository=object(), credential_repository=object())

        result = connector.test_connection_info(CameraManagementServiceTest._payload(id="INACD-test"))

        self.assertTrue(result["ok"])
        self.assertNotIn("password", result)
        self.assertIn("-frames:v", run.call_args.args[0])

    @patch("ina_device_hub.camera_connector.socket.getaddrinfo")
    def test_connection_test_rejects_public_destination(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("8.8.8.8", 554))]
        connector = CameraConnector(camera_repository=object(), credential_repository=object())

        result = connector.test_connection_info(CameraManagementServiceTest._payload(ip_address="camera.example"))

        self.assertFalse(result["ok"])
        self.assertIn("LAN内", result["message"])

    @patch("ina_device_hub.camera_connector.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("ina_device_hub.camera_connector.subprocess.run")
    def test_take_picture_uses_a_bounded_ffmpeg_process(self, run, _which):
        repository = unittest.mock.Mock()
        repository.get.return_value = CameraManagementServiceTest._payload(id="INACD-test")
        credentials = unittest.mock.Mock()
        credentials.get.return_value = {"username": "camera-user", "password": "camera-password"}
        run.return_value = subprocess.CompletedProcess([], 0, stdout=b"jpeg", stderr=b"")
        connector = CameraConnector(camera_repository=repository, credential_repository=credentials)
        connector.construct_rtsp_url = unittest.mock.Mock(return_value="rtsp://redacted")

        frame = connector.take_picture("INACD-test", timeout_seconds=7)

        self.assertEqual(frame, b"jpeg")
        self.assertEqual(run.call_args.kwargs["timeout"], 7)
        self.assertIn("-frames:v", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
