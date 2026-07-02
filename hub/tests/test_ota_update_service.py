import hashlib
import json
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

from ina_device_hub.device_config_repository import DeviceConfigRepository  # noqa: E402
from ina_device_hub.ota_update_service import FirmwareArtifactRepository, OTAUpdateService  # noqa: E402


class _Result:
    rc = 0


class _MqttClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})
        return _Result()


class OTAUpdateServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = DeviceConfigRepository()
        self.repository.device_config_path = os.path.join(self.tmp_dir.name, ".device_configs.json")
        self.repository.device_configs = {}
        self.repository.save()
        self.artifact_repository = FirmwareArtifactRepository()
        self.artifact_repository.artifact_path = os.path.join(self.tmp_dir.name, ".firmware_artifacts.json")
        self.artifact_repository.artifacts = {}
        self.artifact_repository.save()
        self.service = OTAUpdateService(repository=self.repository, artifact_repository=self.artifact_repository)
        self.mqtt_client = _MqttClient()
        self.service.attach_mqtt_client(self.mqtt_client)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_active_device_with_target_and_artifact_receives_update_offer(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000101"
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        self.artifact_repository.upsert("1.1.0", _artifact())

        handled = self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0"))

        self.assertTrue(handled)
        self.assertEqual(self.mqtt_client.published[0]["topic"], f"/{device_id}/kinds/ota/reply")
        self.assertEqual(self.mqtt_client.published[0]["qos"], 0)
        self.assertFalse(self.mqtt_client.published[0]["retain"])
        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload["action"], "update")
        self.assertEqual(payload["device_kind"], "WTR")
        self.assertEqual(payload["version"], "1.1.0")
        self.assertEqual(payload["size"], 892704)
        self.assertEqual(payload["sha256"], "a" * 64)
        record = self.repository.get(device_id)
        self.assertEqual(record["firmware_version"], "1.0.0")
        self.assertEqual(record["device_kind"], "WTR")
        self.assertIsNotNone(record["last_ota_request_at"])

    def test_same_version_returns_none_offer(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000102"
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        self.artifact_repository.upsert("1.1.0", _artifact())

        self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.1.0"))

        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload, {"schema_version": 1, "action": "none", "reason": "already_target"})

    def test_pending_device_does_not_receive_update_offer(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000103"
        self.repository.set_firmware_target(device_id, "1.1.0")
        self.artifact_repository.upsert("1.1.0", _artifact())

        self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0"))

        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload["action"], "none")
        self.assertEqual(payload["reason"], "device_not_active")

    def test_paused_artifact_returns_none_offer(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000104"
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        artifact = _artifact()
        artifact["rollout_state"] = "paused"
        self.artifact_repository.upsert("1.1.0", artifact)

        self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0"))

        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload["action"], "none")
        self.assertEqual(payload["reason"], "artifact_paused")

    def test_artifact_for_other_device_kind_is_not_offered(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000106"
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        artifact = _artifact()
        artifact["device_kind"] = "CAM"
        self.artifact_repository.upsert("1.1.0", artifact)

        self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0"))

        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload["action"], "none")
        self.assertEqual(payload["reason"], "artifact_missing")

    def test_request_device_kind_must_match_existing_device_record(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000107"
        self.repository.record_ota_request(
            device_id,
            {
                "request": "firmware_update",
                "schema_version": 1,
                "device_kind": "WTR",
                "firmware_version": "1.0.0",
            },
        )
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        artifact = _artifact()
        artifact["device_kind"] = "CAM"
        self.artifact_repository.upsert("1.1.0", artifact)

        self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0", device_kind="CAM"))

        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload["action"], "none")
        self.assertEqual(payload["reason"], "device_kind_mismatch")
        self.assertEqual(self.repository.get(device_id)["device_kind"], "WTR")

    def test_ota_status_updates_device_record(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000105"

        handled = self.service.handle_mqtt_message(
            None,
            {
                "message_type": "device_config",
                "device_id": device_id,
                "category": "ota",
                "action": "status",
                "payload": b'{"schema_version":1,"device_kind":"WTR","update_id":"watering-device-1.1.0-aaaaaaaa","state":"started","from_version":"1.0.0","to_version":"1.1.0","firmware_version":"1.0.0"}',
            },
        )

        self.assertTrue(handled)
        record = self.repository.get(device_id)
        self.assertEqual(record["ota_update_id"], "watering-device-1.1.0-aaaaaaaa")
        self.assertEqual(record["ota_state"], "started")
        self.assertEqual(record["ota_attempt_count"], 1)
        self.assertEqual(record["firmware_version"], "1.0.0")
        self.assertEqual(record["device_kind"], "WTR")
        self.assertEqual(self.service.list_ota_statuses(device_id)[0]["payload"]["state"], "started")

    def test_uploaded_firmware_binary_is_saved_and_registered(self):
        firmware = b"test-firmware-binary"
        self.artifact_repository.firmware_root = os.path.join(self.tmp_dir.name, "firmware")

        artifact = self.service.upsert_firmware_binary(
            "WTR",
            "1.1.0",
            firmware,
            metadata={"build_id": "2026-07-01T00:00:00Z+abcdef0"},
        )

        firmware_path = os.path.join(self.tmp_dir.name, "firmware", "WTR", "1.1.0", "firmware.bin")
        with open(firmware_path, "rb") as file:
            self.assertEqual(file.read(), firmware)
        self.assertEqual(artifact["device_kind"], "WTR")
        self.assertEqual(artifact["version"], "1.1.0")
        self.assertEqual(artifact["url"], "http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin")
        self.assertEqual(artifact["size"], len(firmware))
        self.assertEqual(artifact["sha256"], hashlib.sha256(firmware).hexdigest())

    def test_https_firmware_artifact_url_is_rejected_until_device_supports_tls(self):
        artifact = _artifact()
        artifact["url"] = "https://example.test/firmware/WTR/1.1.0/firmware.bin"

        with self.assertRaisesRegex(ValueError, "HTTP URL"):
            self.artifact_repository.upsert("1.1.0", artifact)


def _artifact():
    return {
        "device_kind": "WTR",
        "url": "http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin",
        "size": 892704,
        "sha256": "a" * 64,
        "build_id": "2026-07-01T00:00:00Z+abcdef0",
    }


def _ota_request_message(device_id: str, firmware_version: str, device_kind: str = "WTR"):
    payload = {
        "request": "firmware_update",
        "schema_version": 1,
        "seq": 123,
        "device_kind": device_kind,
        "firmware_version": firmware_version,
        "firmware_build_id": "2026-07-01T00:00:00Z+0000000",
    }
    return {
        "message_type": "device_config",
        "device_id": device_id,
        "category": "ota",
        "action": "request",
        "payload": json.dumps(payload).encode("utf-8"),
    }


if __name__ == "__main__":
    unittest.main()
