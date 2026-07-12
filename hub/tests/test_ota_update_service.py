import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import call, patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("FIRMWARE_BASE_URL", "http://127.0.0.1:39151")
os.environ["FIRMWARE_HOSTNAME"] = ""
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
from ina_device_hub.ota_update_service import OTA_UPDATE_REPLY_RETRY_DELAYS_SEC, FirmwareArtifactRepository, OTAUpdateService  # noqa: E402
from ina_device_hub.setting import setting  # noqa: E402


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
        self.original_firmware_settings = dict(setting().settings.get("firmware") or {})
        setting().settings["firmware"] = {
            **self.original_firmware_settings,
            "base_url": "http://127.0.0.1:39151",
            "hostname": "",
            "port": 39151,
            "root_dir": os.path.join(self.tmp_dir.name, "firmware"),
        }
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
        setting().settings["firmware"] = self.original_firmware_settings
        self.tmp_dir.cleanup()

    def test_active_device_with_target_and_artifact_receives_update_offer(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000101"
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        self.artifact_repository.upsert("1.1.0", _artifact())

        with patch("ina_device_hub.ota_update_service.time.sleep") as sleep_mock:
            handled = self.service.handle_mqtt_message(None, _ota_request_message(device_id, firmware_version="1.0.0"))

        self.assertTrue(handled)
        self.assertEqual(len(self.mqtt_client.published), 2 + len(OTA_UPDATE_REPLY_RETRY_DELAYS_SEC))
        sleep_mock.assert_has_calls([call(delay) for delay in OTA_UPDATE_REPLY_RETRY_DELAYS_SEC])
        self.assertEqual(self.mqtt_client.published[0]["topic"], f"/{device_id}/kinds/ota/reply")
        self.assertEqual(self.mqtt_client.published[0]["qos"], 0)
        self.assertFalse(self.mqtt_client.published[0]["retain"])
        self.assertEqual(self.mqtt_client.published[1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertEqual(self.mqtt_client.published[1]["qos"], 0)
        self.assertTrue(self.mqtt_client.published[1]["retain"])
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

        self.assertEqual(len(self.mqtt_client.published), 2)
        payload = json.loads(self.mqtt_client.published[0]["payload"])
        self.assertEqual(payload, {"schema_version": 1, "action": "none", "reason": "already_target"})
        self.assertEqual(self.mqtt_client.published[1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertEqual(self.mqtt_client.published[1]["payload"], "")
        self.assertTrue(self.mqtt_client.published[1]["retain"])

    def test_set_firmware_target_publishes_retained_offer_without_device_request(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000108"
        self.repository.record_status(
            device_id,
            {
                "device_kind": "WTR",
                "firmware_version": "1.0.0",
                "firmware_build_id": "2026-07-01T00:00:00Z+0000000",
            },
        )
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.artifact_repository.upsert("1.1.0", _artifact())

        record = self.service.set_firmware_target(device_id, "1.1.0")

        self.assertEqual(record["target_firmware_version"], "1.1.0")
        self.assertEqual(self.mqtt_client.published[-1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertTrue(self.mqtt_client.published[-1]["retain"])
        payload = json.loads(self.mqtt_client.published[-1]["payload"])
        self.assertEqual(payload["action"], "update")
        self.assertEqual(payload["url"], "http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin")

    def test_attach_mqtt_client_syncs_existing_retained_offers(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000109"
        self.repository.record_status(device_id, {"device_kind": "WTR", "firmware_version": "1.0.0"})
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.repository.set_firmware_target(device_id, "1.1.0")
        self.artifact_repository.upsert("1.1.0", _artifact())
        new_mqtt_client = _MqttClient()

        self.service.attach_mqtt_client(new_mqtt_client)

        self.assertEqual(new_mqtt_client.published[-1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertTrue(new_mqtt_client.published[-1]["retain"])
        self.assertEqual(json.loads(new_mqtt_client.published[-1]["payload"])["action"], "update")

    def test_confirmed_status_clears_retained_offer_when_reported_version_matches(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000110"
        self.repository.record_status(device_id, {"device_kind": "WTR", "firmware_version": "1.0.0"})
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.artifact_repository.upsert("1.1.0", _artifact())
        self.service.set_firmware_target(device_id, "1.1.0")
        self.mqtt_client.published = []

        handled = self.service.handle_mqtt_message(None, _ota_status_message(device_id, "confirmed", firmware_version="1.1.0", to_version="1.1.0"))

        self.assertTrue(handled)
        self.assertEqual(self.mqtt_client.published[-1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertEqual(self.mqtt_client.published[-1]["payload"], "")
        self.assertTrue(self.mqtt_client.published[-1]["retain"])
        record = self.repository.get(device_id)
        self.assertEqual(record["firmware_version"], "1.1.0")
        self.assertIsNone(record["ota_error"])

    def test_confirmed_status_keeps_retained_offer_when_reported_version_mismatches(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000111"
        self.repository.record_status(device_id, {"device_kind": "WTR", "firmware_version": "1.0.0"})
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.artifact_repository.upsert("1.1.0", _artifact())
        self.service.set_firmware_target(device_id, "1.1.0")
        self.mqtt_client.published = []

        handled = self.service.handle_mqtt_message(None, _ota_status_message(device_id, "confirmed", firmware_version="0.0.0-dev", to_version="1.1.0"))

        self.assertTrue(handled)
        self.assertEqual(self.mqtt_client.published[-1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertTrue(self.mqtt_client.published[-1]["retain"])
        payload = json.loads(self.mqtt_client.published[-1]["payload"])
        self.assertEqual(payload["action"], "update")
        self.assertEqual(payload["version"], "1.1.0")
        record = self.repository.get(device_id)
        self.assertEqual(record["firmware_version"], "0.0.0-dev")
        self.assertEqual(record["ota_error"], "confirmed_version_mismatch")

    def test_already_running_skip_is_treated_as_confirmed(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000112"
        self.repository.record_status(device_id, {"device_kind": "WTR", "firmware_version": "1.1.0"})
        self.repository.set_state(device_id, "active", approved_by="operator")
        self.artifact_repository.upsert("1.1.0", _artifact())
        self.service.set_firmware_target(device_id, "1.1.0")
        self.mqtt_client.published = []

        handled = self.service.handle_mqtt_message(
            None,
            _ota_status_message(
                device_id,
                "skipped",
                firmware_version="1.1.0",
                to_version="1.1.0",
                error="already_running",
            ),
        )

        self.assertTrue(handled)
        self.assertEqual(self.mqtt_client.published[-1]["topic"], f"/kinds/WTR/devices/{device_id}/ota/offer")
        self.assertEqual(self.mqtt_client.published[-1]["payload"], "")
        self.assertTrue(self.mqtt_client.published[-1]["retain"])
        record = self.repository.get(device_id)
        self.assertEqual(record["firmware_version"], "1.1.0")
        self.assertEqual(record["ota_state"], "confirmed")
        self.assertIsNone(record["ota_error"])
        self.assertIsNotNone(record["ota_confirmed_at"])

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
        firmware = _firmware_binary(device_kind="WTR", version="1.1.0", build_id="2026-07-01T00:00:00Z+abcdef0")
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
        self.assertEqual(artifact["build_id"], "2026-07-01T00:00:00Z+abcdef0")
        self.assertEqual(artifact["firmware_metadata"]["project"], "watering-device")
        self.assertEqual(artifact["firmware_metadata"]["target"], "seeed_xiao_esp32s3")

    def test_uploaded_firmware_binary_requires_embedded_manifest(self):
        with self.assertRaisesRegex(ValueError, "manifest marker"):
            self.service.upsert_firmware_binary("WTR", "1.1.0", b"test-firmware-binary")

    def test_uploaded_firmware_binary_rejects_device_kind_mismatch(self):
        firmware = _firmware_binary(device_kind="CAM", version="1.1.0")

        with self.assertRaisesRegex(ValueError, "device_kind mismatch"):
            self.service.upsert_firmware_binary("WTR", "1.1.0", firmware)

    def test_uploaded_firmware_binary_rejects_version_mismatch(self):
        firmware = _firmware_binary(device_kind="WTR", version="1.2.0")

        with self.assertRaisesRegex(ValueError, "version mismatch"):
            self.service.upsert_firmware_binary("WTR", "1.1.0", firmware)

    def test_uploaded_firmware_binary_rejects_build_id_mismatch(self):
        firmware = _firmware_binary(device_kind="WTR", version="1.1.0", build_id="2026-07-01T00:00:00Z+abcdef0")

        with self.assertRaisesRegex(ValueError, "build_id mismatch"):
            self.service.upsert_firmware_binary(
                "WTR",
                "1.1.0",
                firmware,
                metadata={"build_id": "2026-07-01T00:00:00Z+different"},
            )

    def test_firmware_base_url_can_be_generated_from_hostname(self):
        original_firmware_settings = dict(setting().settings.get("firmware") or {})
        setting().settings["firmware"] = {
            "base_url": "",
            "hostname": "",
            "port": "",
            "root_dir": os.path.join(self.tmp_dir.name, "firmware"),
        }
        try:
            with patch.dict(
                os.environ,
                {
                    "FIRMWARE_BASE_URL": "",
                    "FIRMWARE_HOSTNAME": "",
                    "HOSTNAME": "hub-device.local",
                    "HUB_HTTP_PORT": "39151",
                },
            ):
                self.assertEqual(
                    self.artifact_repository.public_firmware_url("WTR", "1.1.0"),
                    "http://hub-device.local:39151/firmware/WTR/1.1.0/firmware.bin",
                )
        finally:
            setting().settings["firmware"] = original_firmware_settings

    def test_generated_firmware_base_url_uses_mdns_for_single_label_hostname(self):
        original_firmware_settings = dict(setting().settings.get("firmware") or {})
        setting().settings["firmware"] = {
            "base_url": "",
            "hostname": "",
            "port": "",
            "root_dir": os.path.join(self.tmp_dir.name, "firmware"),
        }
        try:
            with patch.dict(
                os.environ,
                {
                    "FIRMWARE_BASE_URL": "",
                    "FIRMWARE_HOSTNAME": "",
                    "HOSTNAME": "hub-device",
                    "HUB_HTTP_PORT": "39151",
                },
            ):
                self.assertEqual(
                    self.artifact_repository.public_firmware_url("WTR", "1.1.0"),
                    "http://hub-device.local:39151/firmware/WTR/1.1.0/firmware.bin",
                )
        finally:
            setting().settings["firmware"] = original_firmware_settings

    def test_generated_firmware_base_url_keeps_ip_address(self):
        original_firmware_settings = dict(setting().settings.get("firmware") or {})
        setting().settings["firmware"] = {
            "base_url": "",
            "hostname": "",
            "port": "",
            "root_dir": os.path.join(self.tmp_dir.name, "firmware"),
        }
        try:
            with patch.dict(
                os.environ,
                {
                    "FIRMWARE_BASE_URL": "",
                    "FIRMWARE_HOSTNAME": "192.168.1.140",
                    "HOSTNAME": "",
                    "HUB_HTTP_PORT": "39151",
                },
            ):
                self.assertEqual(
                    self.artifact_repository.public_firmware_url("WTR", "1.1.0"),
                    "http://192.168.1.140:39151/firmware/WTR/1.1.0/firmware.bin",
                )
        finally:
            setting().settings["firmware"] = original_firmware_settings

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


def _firmware_binary(
    *,
    device_kind: str,
    version: str,
    build_id: str = "2026-07-01T00:00:00Z+abcdef0",
    project: str = "watering-device",
    target: str = "seeed_xiao_esp32s3",
    framework: str = "arduino",
):
    manifest = (
        "INAS_FW_MANIFEST_V1_BEGIN\n"
        "schema=1\n"
        f"project={project}\n"
        f"device_kind={device_kind}\n"
        f"version={version}\n"
        f"build_id={build_id}\n"
        f"target={target}\n"
        f"framework={framework}\n"
        "INAS_FW_MANIFEST_V1_END\n"
    ).encode("ascii")
    return b"\xe9ESP32BIN" + manifest + b"\x00firmware-body"


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


def _ota_status_message(device_id: str, state: str, firmware_version: str, to_version: str, error: str | None = None):
    payload = {
        "schema_version": 1,
        "device_kind": "WTR",
        "update_id": "watering-device-1.1.0-aaaaaaaa",
        "state": state,
        "from_version": "1.0.0",
        "to_version": to_version,
        "firmware_version": firmware_version,
        "firmware_build_id": "2026-07-01T00:00:00Z+0000000",
        "progress": 100,
    }
    if error is not None:
        payload["error"] = error
    return {
        "message_type": "device_config",
        "device_id": device_id,
        "category": "ota",
        "action": "status",
        "payload": json.dumps(payload).encode("utf-8"),
    }


if __name__ == "__main__":
    unittest.main()
