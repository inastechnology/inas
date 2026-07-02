import hashlib
import os
import tempfile
import unittest

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("FIRMWARE_BASE_URL", "http://127.0.0.1:39151")
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
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

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.device_config_repository import DeviceConfigRepository  # noqa: E402
from ina_device_hub.device_config_service import DeviceConfigService  # noqa: E402
from ina_device_hub.ota_update_service import FirmwareArtifactRepository, OTAUpdateService  # noqa: E402


class WebServerOTATest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

        self.device_repository = DeviceConfigRepository()
        self.device_repository.device_config_path = os.path.join(self.tmp_dir.name, ".device_configs.json")
        self.device_repository.device_configs = {}
        self.device_repository.save()

        self.artifact_repository = FirmwareArtifactRepository()
        self.artifact_repository.artifact_path = os.path.join(self.tmp_dir.name, ".firmware_artifacts.json")
        self.artifact_repository.firmware_root = os.path.join(self.tmp_dir.name, "firmware")
        self.artifact_repository.artifacts = {}
        self.artifact_repository.save()

        self.device_service = DeviceConfigService(repository=self.device_repository)
        self.service = OTAUpdateService(repository=self.device_repository, artifact_repository=self.artifact_repository)
        self.original_device_config_service = web_server.device_config_service
        self.original_ota_update_service = web_server.ota_update_service
        self.original_list_device_events = web_server.list_device_events
        web_server.device_config_service = lambda: self.device_service
        web_server.ota_update_service = lambda: self.service
        web_server.list_device_events = lambda *args, **kwargs: []
        self.client = web_server.app.test_client()

    def tearDown(self):
        web_server.device_config_service = self.original_device_config_service
        web_server.ota_update_service = self.original_ota_update_service
        web_server.list_device_events = self.original_list_device_events
        self.tmp_dir.cleanup()

    def test_upload_registers_and_serves_firmware_binary(self):
        firmware = b"test-firmware-binary"

        response = self.client.post(
            "/local/api/firmware-artifacts/WTR/1.1.0/upload?build_id=2026-07-01T00:00:00Z%2Babcdef0",
            data=firmware,
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 201)
        artifact = response.get_json()
        self.assertEqual(artifact["device_kind"], "WTR")
        self.assertEqual(artifact["version"], "1.1.0")
        self.assertEqual(artifact["url"], "http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin")
        self.assertEqual(artifact["size"], len(firmware))
        self.assertEqual(artifact["sha256"], hashlib.sha256(firmware).hexdigest())

        download = self.client.get("/firmware/WTR/1.1.0/firmware.bin")

        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, firmware)
        self.assertEqual(download.content_type, "application/octet-stream")
        download.close()

    def test_upload_rejects_invalid_boolean_form_value(self):
        response = self.client.post(
            "/local/api/firmware-artifacts/WTR/1.1.0/upload?force=maybe",
            data=b"test-firmware-binary",
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("force must be a boolean", response.get_json()["error"])

    def test_mqtt_devices_page_exposes_existing_device_and_ota_operations(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000201"
        self.device_service.update_config(
            device_id,
            {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 40,
                "force_watering": False,
                "schedules": [{"hour": 7, "minute": 30, "duration_sec": 60, "channel_mask": 1}],
            },
        )
        self.device_service.set_state(device_id, "active", approved_by="operator")
        self.device_repository.record_status(device_id, {"seq": 1, "device_kind": "WTR", "firmware_version": "1.0.0"})
        self.device_repository.record_ota_status(
            device_id,
            {
                "schema_version": 1,
                "device_kind": "WTR",
                "update_id": "watering-device-1.1.0-aaaaaaaa",
                "state": "started",
                "from_version": "1.0.0",
                "to_version": "1.1.0",
            },
        )
        self.artifact_repository.upsert(
            "1.1.0",
            {
                "device_kind": "WTR",
                "url": "http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin",
                "size": 10,
                "sha256": "a" * 64,
                "build_id": "2026-07-01T00:00:00Z+abcdef0",
            },
        )

        response = self.client.get(f"/mqtt-devices?device_id={device_id}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-state-action="approve"', html)
        self.assertIn('id="metadata-form"', html)
        self.assertIn('id="runtime-config-json"', html)
        self.assertIn('id="save-push-runtime-config"', html)
        self.assertIn('id="firmware-target-form"', html)
        self.assertIn('id="firmware-upload-form"', html)
        self.assertIn("/local/api/firmware-artifacts/", html)
        self.assertIn("OTA Status History", html)
        self.assertIn("watering-device-1.1.0-aaaaaaaa", html)
        self.assertIn("http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin", html)


if __name__ == "__main__":
    unittest.main()
