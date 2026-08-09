import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta, timezone

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOCAL_STORAGE_BASE_DIR", tempfile.mkdtemp())
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
os.environ["HUB_AUTH_MODE"] = "local"

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.device_config_repository import DeviceConfigRepository  # noqa: E402
from ina_device_hub.device_config_service import DeviceConfigService  # noqa: E402
from ina_device_hub.ota_update_service import FirmwareArtifactRepository, OTAUpdateService  # noqa: E402
from ina_device_hub.setting import setting  # noqa: E402


class _DeviceRemoval:
    def __init__(self, repository):
        self.repository = repository

    def delete(self, device_id, deleted_by="unknown"):
        del deleted_by
        return self.repository.delete(device_id)


class _CameraManagement:
    def __init__(self):
        self.records = {}
        self.test_payloads = []

    def list(self, query=""):
        return [
            record for record in self.records.values() if not query or query.casefold() in f"{record['id']} {record['name']} {record['camera_type']}".casefold()
        ]

    def get(self, device_id):
        return self.records.get(device_id)

    def create(self, payload):
        device_id = "INACD-created"
        record = {
            "id": device_id,
            "name": payload["name"],
            "camera_type": payload["camera_type"],
            "ip_address": payload["ip_address"],
            "port": int(payload.get("port") or 554),
            "channel": int(payload.get("channel") or 1),
            "stream": payload.get("stream") or "main",
            "rtsp_path": payload.get("rtsp_path") or "",
            "timelapse": bool(payload.get("timelapse")),
            "username": payload.get("username") or "",
            "credentials_configured": True,
            "preview_url": f"/camera/{device_id}/preview",
            "images_url": f"/camera/{device_id}/images",
        }
        self.records[device_id] = record
        return record

    def update(self, device_id, payload):
        self.records[device_id] = {**self.records[device_id], **payload, "id": device_id}
        self.records[device_id].pop("password", None)
        return self.records[device_id]

    def test_connection(self, payload, device_id=None):
        self.test_payloads.append((device_id, payload))
        return {"ok": True, "message": "RTSP映像から静止画を取得できました"}

    def delete(self, device_id, deleted_by="unknown"):
        del deleted_by
        return self.records.pop(device_id, None)


class WebServerOTATest(unittest.TestCase):
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
        self.original_device_removal_service = web_server.device_removal_service
        self.original_ota_update_service = web_server.ota_update_service
        self.original_camera_management_service = web_server.camera_management_service
        self.original_list_device_events = web_server.list_device_events
        web_server.device_config_service = lambda: self.device_service
        web_server.device_removal_service = lambda: _DeviceRemoval(self.device_repository)
        web_server.ota_update_service = lambda: self.service
        self.camera_management = _CameraManagement()
        web_server.camera_management_service = lambda: self.camera_management
        web_server.list_device_events = lambda *args, **kwargs: []
        self.client = web_server.app.test_client()

    def tearDown(self):
        setting().settings["firmware"] = self.original_firmware_settings
        web_server.device_config_service = self.original_device_config_service
        web_server.device_removal_service = self.original_device_removal_service
        web_server.ota_update_service = self.original_ota_update_service
        web_server.camera_management_service = self.original_camera_management_service
        web_server.list_device_events = self.original_list_device_events
        self.tmp_dir.cleanup()

    def test_upload_registers_and_serves_firmware_binary(self):
        firmware = _firmware_binary(device_kind="WTR", version="1.1.0", build_id="2026-07-01T00:00:00Z+abcdef0")

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
        self.assertEqual(artifact["build_id"], "2026-07-01T00:00:00Z+abcdef0")
        self.assertEqual(artifact["firmware_metadata"]["target"], "seeed_xiao_esp32s3")

        download = self.client.get("/firmware/WTR/1.1.0/firmware.bin")

        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, firmware)
        self.assertEqual(download.content_type, "application/octet-stream")
        download.close()

    def test_inspect_firmware_artifact_reads_embedded_manifest(self):
        firmware = _firmware_binary(device_kind="WTR", version="1.2.0", build_id="2026-07-03T10:31:34+0900+f31d9e6")

        response = self.client.post(
            "/local/api/firmware-artifacts/inspect",
            data=firmware,
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 200)
        metadata = response.get_json()
        self.assertEqual(metadata["device_kind"], "WTR")
        self.assertEqual(metadata["version"], "1.2.0")
        self.assertEqual(metadata["build_id"], "2026-07-03T10:31:34+0900+f31d9e6")
        self.assertEqual(metadata["project"], "watering-device")
        self.assertEqual(metadata["upload_format"], "bin")

    def test_inspect_inasfw_reads_only_embedded_firmware_manifest(self):
        firmware = _firmware_binary(device_kind="FGT", version="0.2.0", project="fertigation-device", target="seeed_xiao_esp32c6")
        release_module = _inasfw(firmware, device_kind="FGT", version="0.2.0")

        response = self.client.post(
            "/local/api/firmware-artifacts/inspect",
            data={"firmware": (io.BytesIO(release_module), "fertigation-device-0.2.0.inasfw")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        metadata = response.get_json()
        self.assertEqual(metadata["device_kind"], "FGT")
        self.assertEqual(metadata["version"], "0.2.0")
        self.assertEqual(metadata["project"], "fertigation-device")
        self.assertEqual(metadata["upload_format"], "inasfw")

    def test_upload_inasfw_registers_and_serves_only_embedded_firmware_binary(self):
        firmware = _firmware_binary(device_kind="FGT", version="0.2.2", project="fertigation-device", target="seeed_xiao_esp32c6")
        release_module = _inasfw(firmware, device_kind="FGT", version="0.2.2")

        response = self.client.post(
            "/local/api/firmware-artifacts/FGT/0.2.2/upload",
            data={"firmware": (io.BytesIO(release_module), "fertigation-device-0.2.2.inasfw")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201)
        artifact = response.get_json()
        self.assertEqual(artifact["device_kind"], "FGT")
        self.assertEqual(artifact["version"], "0.2.2")
        self.assertEqual(artifact["size"], len(firmware))
        self.assertEqual(artifact["sha256"], hashlib.sha256(firmware).hexdigest())

        download = self.client.get("/firmware/FGT/0.2.2/firmware.bin")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, firmware)
        download.close()

    def test_upload_rejects_invalid_boolean_form_value(self):
        response = self.client.post(
            "/local/api/firmware-artifacts/WTR/1.1.0/upload?force=maybe",
            data=b"test-firmware-binary",
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("force must be a boolean", response.get_json()["error"])

    def test_firmware_upload_rejects_payload_above_configured_limit(self):
        original_security = dict(setting().settings.get("security") or {})
        setting().settings["security"] = {**original_security, "firmware_max_upload_bytes": 4}
        try:
            response = self.client.post(
                "/local/api/firmware-artifacts/inspect",
                data=b"12345",
                content_type="application/octet-stream",
            )
        finally:
            setting().settings["security"] = original_security

        self.assertEqual(response.status_code, 413)
        self.assertIn("4-byte limit", response.get_json()["error"])

    def test_home_page_is_field_selector_without_device_navigation(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("圃場を選択", html)
        self.assertIn('role="search"', html)
        self.assertIn('id="open-field-create"', html)
        self.assertNotIn('href="/mqtt-devices"', html)
        self.assertNotIn('href="/demo/mqtt-devices"', html)
        self.assertNotIn("MQTT Devices", html)

    def test_mqtt_devices_list_links_to_device_detail(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000201"
        self.device_service.set_state(device_id, "active", approved_by="operator")
        self.device_repository.record_status(
            device_id,
            {
                "seq": 1,
                "device_kind": "WTR",
                "firmware_version": "1.0.0",
                "watering_due": True,
                "watering_started": True,
                "last_soil_moisture": 42,
                "threshold": 40,
                "next_sleep_sec": 120,
            },
        )

        response = self.client.get("/mqtt-devices")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("機器一覧", html)
        self.assertIn("圃場ビュー", html)
        self.assertIn("灌水中", html)
        self.assertIn("42%", html)
        self.assertIn(f'href="/mqtt-devices/{device_id}"', html)
        self.assertIn(f'data-delete-device="{device_id}"', html)
        self.assertNotIn("灌水推移", html)
        self.assertNotIn('id="metadata-form"', html)
        self.assertNotIn('href="/demo/mqtt-devices"', html)
        self.assertNotIn("UIデモを開く", html)
        self.assertNotIn('class="developer-tools"', html)

    def test_mqtt_devices_list_shows_registered_camera_and_registration_link(self):
        camera_id = "INACD-00000000-0000-4000-8000-000000000301"
        self.camera_management.records[camera_id] = {
            "id": camera_id,
            "name": "ハウス東側",
            "camera_type": "reolink",
            "ip_address": "192.168.1.84",
            "port": 554,
            "channel": 1,
            "stream": "main",
            "rtsp_path": "",
            "timelapse": True,
            "username": "camera-user",
            "credentials_configured": True,
            "preview_url": f"/camera/{camera_id}/preview",
            "images_url": f"/camera/{camera_id}/images",
        }

        response = self.client.get("/mqtt-devices")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("ハウス東側", html)
        self.assertIn("ネットワークカメラ / reolink", html)
        self.assertIn(f'href="/camera/{camera_id}#settings"', html)
        self.assertIn('href="/cameras/new"', html)
        self.assertNotIn("camera-user", html)

    def test_camera_form_and_api_support_registration_and_connection_test(self):
        form_response = self.client.get("/cameras/new")
        created = self.client.post(
            "/local/api/cameras",
            json={
                "name": "ハウス東側",
                "camera_type": "reolink",
                "ip_address": "192.168.1.84",
                "username": "camera-user",
                "password": "secret",
            },
        )
        tested = self.client.post(
            "/local/api/cameras/test-connection",
            json={
                "name": "ハウス東側",
                "camera_type": "reolink",
                "ip_address": "192.168.1.84",
                "username": "camera-user",
                "password": "secret",
            },
        )

        self.assertEqual(form_response.status_code, 200)
        self.assertIn('id="camera-address"', form_response.get_data(as_text=True))
        self.assertIn('id="test-camera"', form_response.get_data(as_text=True))
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("password", created.get_json())
        self.assertEqual(tested.status_code, 200)
        self.assertTrue(tested.get_json()["ok"])

    def test_mqtt_device_can_be_deleted_without_recreating_detail_record(self):
        device_id = "INADS-OLD-FIRMWARE-ID"
        self.device_repository.get_or_create(device_id, self.device_service.default_config())

        deleted = self.client.delete(f"/local/api/mqtt-devices/{device_id}")
        detail = self.client.get(f"/mqtt-devices/{device_id}")
        deleted_again = self.client.delete(f"/local/api/mqtt-devices/{device_id}")

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json(), {"deleted": True, "device_id": device_id})
        self.assertEqual(detail.status_code, 404)
        self.assertIsNone(self.device_repository.get(device_id))
        self.assertEqual(deleted_again.status_code, 404)

    def test_mqtt_device_delete_returns_references_when_bound(self):
        device_id = "INADS-BOUND-DEVICE"
        self.device_repository.get_or_create(device_id, self.device_service.default_config())

        class _BoundRemoval:
            def delete(self, _device_id, deleted_by="unknown"):
                del deleted_by
                raise web_server.DeviceRemovalConflictError([{"type": "field", "field_id": "field-1", "field_name": "西条圃場"}])

        bound_removal = _BoundRemoval()
        web_server.device_removal_service = lambda: bound_removal
        try:
            response = self.client.delete(f"/local/api/mqtt-devices/{device_id}")
        finally:
            web_server.device_removal_service = lambda: _DeviceRemoval(self.device_repository)

        self.assertEqual(response.status_code, 409)
        self.assertIn("参照されているため削除できません", response.get_json()["error"])
        self.assertEqual(response.get_json()["references"][0]["field_name"], "西条圃場")
        self.assertIsNotNone(self.device_repository.get(device_id))

    def test_mqtt_devices_detail_exposes_existing_device_and_ota_operations(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000201"
        self.device_service.update_config(
            device_id,
            {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 40,
                "force_watering": False,
                "schedules": [{"hour": 7, "minute": 30, "duration_sec": 60, "channel_mask": 1}],
                "mosfet_switches": [
                    {
                        "switch_id": "irr1",
                        "name": "潅水1系",
                        "enabled": True,
                        "role": "irrigation",
                        "terminal": "IRR1",
                        "channel_mask": 1,
                        "controlled_load": "A区画",
                    },
                    {
                        "switch_id": "legacy_aux",
                        "name": "既存補助出力",
                        "enabled": False,
                        "role": "auxiliary",
                        "terminal": "AUX",
                        "channel_mask": 4,
                        "controlled_load": "旧設備",
                    },
                ],
            },
        )
        self.device_service.set_state(device_id, "active", approved_by="operator")
        self.device_repository.record_status(
            device_id,
            {
                "seq": 1,
                "device_kind": "WTR",
                "firmware_version": "1.0.0",
                "config_received": True,
                "time_synced": True,
                "watering_due": True,
                "watering_started": True,
                "watering_duration_sec": 45,
                "channel_mask": 1,
                "last_soil_moisture": 42,
                "threshold": 40,
                "next_sleep_sec": 120,
            },
        )
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
        self.connection_events = [
            {
                "occurred_at": datetime.now(UTC).isoformat(),
                "event_type": "mqtt_client_connected",
                "direction": "broker",
                "device_id": device_id,
                "topic": "$SYS/broker/log/N",
                "action": "connect",
                "payload": {"client_id": device_id, "remote_address": "192.0.2.24:51411"},
            }
        ]
        web_server.list_device_events = lambda *args, **kwargs: self.connection_events if kwargs.get("connection_events_only") else []

        response = self.client.get(f"/mqtt-devices/{device_id}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Hub 管理パネル", html)
        self.assertNotIn("機器一覧へ戻る", html)
        self.assertEqual(html.count('href="/mqtt-devices"'), 1)
        self.assertNotIn("圃場ビュー", html)
        self.assertNotIn("デバイス API", html)
        self.assertNotIn("イベント API", html)
        self.assertIn('role="tablist"', html)
        self.assertIn('data-tab-target="tab-overview"', html)
        self.assertIn('data-tab-target="tab-monitoring"', html)
        self.assertIn('data-tab-target="tab-config"', html)
        self.assertIn('data-tab-target="tab-firmware"', html)
        self.assertIn('data-tab-target="tab-maintenance"', html)
        self.assertIn(">現在値・履歴</button>", html)
        self.assertIn(">動作設定</button>", html)
        self.assertIn(">機器を更新</button>", html)
        self.assertIn(">保守・管理</button>", html)
        self.assertIn("設置場所・関連先", html)
        self.assertNotIn("<h2>設置ビュー</h2>", html)
        self.assertIn("現在の潅水判断", html)
        self.assertIn("次の潅水", html)
        self.assertIn("土壌水分しきい値", html)
        self.assertIn("水やり機", html)
        self.assertIn("潅水推移", html)
        self.assertIn("土壌水分推移", html)
        self.assertNotIn("Plotly.newPlot", html)
        self.assertIn("潅水推移を読み込み中", html)
        self.assertIn('"/local/api/mqtt-devices/"', html)
        self.assertIn("直近3日", html)
        self.assertIn("2週間", html)
        self.assertIn("1か月", html)
        self.assertIn("全期間", html)
        self.assertIn("カスタム", html)
        self.assertIn("灌水中", html)
        self.assertIn("45秒", html)
        self.assertIn("系統1", html)
        self.assertIn("土壌水分", html)
        self.assertIn("42%", html)
        self.assertIn("次回の通信予定", html)
        self.assertIn("詳しい通信履歴", html)
        self.assertIn('id="connection-help"', html)
        self.assertIn('aria-label="困ったときのヘルプを開く"', html)
        self.assertIn("困ったとき：通信を確認する", html)
        self.assertIn("Hubが最後に確認", html)
        self.assertIn("Hubへの接続", html)
        self.assertIn("Hubへの接続に成功", html)
        self.assertIn("機器からHubの入口まで通信できました。", html)
        self.assertIn("通信・接続履歴", html)
        self.assertIn("管理者向けの技術データ", html)
        self.assertIn("動作設定", html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=settings"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=settings#watering-rules" aria-label="土壌水分しきい値の設定を変更"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=monitoring#soil-moisture-chart" aria-label="現在の土壌水分の履歴を見る"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=monitoring#watering-trend-chart" aria-label="現在の潅水状態の履歴を見る"', html)
        self.assertIn(f'aria-label="{device_id}の動作設定"', html)
        self.assertIn('data-state-action="disable"', html)
        self.assertNotIn('data-state-action="approve"', html)
        self.assertNotIn('data-state-action="retire"', html)
        self.assertIn('id="metadata-form"', html)
        self.assertIn('id="runtime-config-json"', html)
        self.assertIn('id="save-push-runtime-config"', html)
        self.assertIn('id="firmware-target-form"', html)
        self.assertIn(
            '<select id="target-firmware-version" aria-label="更新する機器ソフトウェアのバージョン" data-searchable-select',
            html,
        )
        self.assertIn("/static/searchable-select.css", html)
        self.assertIn('id="firmware-upload-form"', html)
        self.assertIn('id="firmware-dropzone"', html)
        self.assertIn(".inasfw ファイルをここへドロップ", html)
        self.assertIn("INAS更新ファイル（.inasfw）", html)
        self.assertIn('accept=".inasfw,application/zip"', html)
        self.assertNotIn("firmware.bin / .inasfw をここへドロップ", html)
        self.assertIn("/static/ui-illustrations/firmware-care.png", html)
        self.assertIn('id="firmware-version" name="version" type="hidden"', html)
        self.assertIn('id="inspect-firmware-manifest"', html)
        self.assertIn("INAS更新ファイル（.inasfw）を置くと、対応機種とバージョンを自動で読み取ります", html)
        self.assertIn('id="firmware-artifact-rows"', html)
        self.assertIn('id="firmware-artifact-count"', html)
        self.assertIn("配信ファイルを開く", html)
        self.assertIn("2026-07-01T00:00:00Z+abcdef0", html)
        self.assertIn("/local/api/firmware-artifacts/", html)
        self.assertIn("OTA Status History", html)
        self.assertIn('id="output-connection-map"', html)
        self.assertIn('id="open-output-settings"', html)
        self.assertIn('role="button" tabindex="0" aria-haspopup="dialog" aria-controls="output-settings-dialog"', html)
        self.assertIn('aria-label="現在の水やりルートを変更"', html)
        self.assertIn("クリックして変更", html)
        self.assertIn('id="output-settings-dialog"', html)
        self.assertIn("水やりルートを組み立てる", html)
        self.assertIn("設備をつなぐ", html)
        self.assertIn("水やりを決める", html)
        self.assertIn("センサーを合わせる", html)
        self.assertIn("動かす設備を絵から選ぶ", html)
        self.assertIn("data-equipment-type", html)
        self.assertIn("接続口 1", html)
        self.assertNotIn("接続口 2", html)
        self.assertIn("A区画", html)
        self.assertIn("既存値は維持されます", html)
        self.assertIn("&#34;switch_id&#34;: &#34;legacy_aux&#34;", html)
        self.assertNotIn("内部ID", html)
        self.assertNotIn("系統番号（mask）", html)
        self.assertNotIn("MOSFET", html)
        self.assertIn("組み立てた設定を機器へ送る", html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=settings#watering-schedules"', html)
        self.assertIn('id="soil-calibration-guide"', html)
        self.assertIn("乾いた基準を記録する", html)
        self.assertIn("湿った基準を記録する", html)
        self.assertIn("/static/ui-illustrations/controller-flow.png", html)
        self.assertIn('aria-label="動作確認"', html)
        self.assertIn("watering-device-1.1.0-aaaaaaaa", html)
        self.assertIn("http://127.0.0.1:39151/firmware/WTR/1.1.0/firmware.bin", html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("Plotly.newPlot", charts["watering"])
        self.assertIn("Plotly.newPlot", charts["soil_moisture"])

    def test_environment_device_detail_has_environment_charts_and_settings_link(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000202"
        self.device_service.update_metadata(device_id, {"name": "1号ハウス環境センサー", "location": "1号ハウス"})
        self.device_service.set_state(device_id, "active", approved_by="operator")
        self.device_repository.record_status(
            device_id,
            {
                "seq": 1,
                "device_kind": "ENV",
                "firmware_version": "2.0.0",
                "air_temperature_c": 24.6,
                "air_humidity_percent": 68.0,
                "par_umol_m2_s": 920,
            },
        )

        response = self.client.get(f"/mqtt-devices/{device_id}?tab=monitoring")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("1号ハウス環境センサー", html)
        self.assertIn("24.6 ℃", html)
        self.assertIn("68.0 %", html)
        self.assertIn('data-chart-kind="air_temperature"', html)
        self.assertIn('data-chart-kind="air_humidity"', html)
        self.assertIn('data-chart-kind="par"', html)
        self.assertNotIn('data-chart-kind="watering"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=settings"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=monitoring#air-temperature-chart" aria-label="気温の履歴を見る"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=monitoring#air-humidity-chart" aria-label="湿度の履歴を見る"', html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=monitoring#par-chart" aria-label="光合成に使える光の履歴を見る"', html)
        self.assertIn("つないだセンサー", html)
        self.assertIn('data-env-sensor-card="par"', html)
        self.assertIn('data-env-sensor-card="soil"', html)
        self.assertIn('id="env-calibration-dialog"', html)
        self.assertIn('id="env-calibration-workbench"', html)
        self.assertIn('id="env-calibration-reference-value" type="range"', html)
        self.assertIn('data-env-calibration-summary="par_umol_m2_s">未調整', html)
        self.assertIn('data-env-calibration-summary="soil_ph">未調整', html)
        self.assertIn('id="env-par-slave" type="hidden"', html)
        self.assertIn('id="env-soil-slave" type="hidden"', html)
        self.assertIn("上級者設定", html)
        self.assertNotIn("センサー番号", html)
        self.assertNotIn("読み取り方式", html)
        self.assertNotIn("読み取り位置", html)
        self.assertNotIn("読み取り開始位置", html)
        self.assertIn(".sensor-device-card[hidden], .sensor-device-body[hidden], [data-env-sensor-advanced][hidden] { display: none !important; }", html)
        self.assertIn('const tabAliases = { irrigation: "monitoring", config: "settings", diagnostics: "maintenance" };', html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("Plotly.newPlot", charts["air_temperature"])
        self.assertIn("Plotly.newPlot", charts["air_humidity"])
        self.assertIn("Plotly.newPlot", charts["par"])
        self.assertIsNone(charts["watering"])

    def test_fgt_hides_unsupported_ph_and_npk_from_old_firmware_status(self):
        device_id = "INADS-00000000-0000-4000-8000-00000000020f"
        self.device_repository.record_status(
            device_id,
            {
                "seq": 1,
                "device_kind": "FGT",
                "firmware_version": "0.2.0",
                "soil_rs485_ok": True,
                "soil_moisture_percent": 26.7,
                "soil_temperature_c": 25.0,
                "soil_ec_us_cm": 81,
                "soil_ph": 4.4,
                "soil_n_mg_kg": 40,
                "soil_p_mg_kg": 0,
                "soil_k_mg_kg": 0,
            },
        )

        response = self.client.get(f"/mqtt-devices/{device_id}?tab=monitoring")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("26.7 %", html)
        self.assertIn("25.0 ℃", html)
        self.assertIn("81 µS/cm", html)
        self.assertIn('data-chart-kind="watering"', html)
        self.assertNotIn('data-chart-kind="soil_ph"', html)
        self.assertNotIn('data-chart-kind="soil_n"', html)
        self.assertNotIn('data-chart-kind="soil_p"', html)
        self.assertNotIn('data-chart-kind="soil_k"', html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("soil_moisture", charts)
        self.assertIn("soil_temperature", charts)
        self.assertIn("soil_ec", charts)
        self.assertIsNone(charts["watering"])
        self.assertNotIn("soil_ph", charts)
        self.assertNotIn("soil_n", charts)
        self.assertNotIn("soil_p", charts)
        self.assertNotIn("soil_k", charts)

    def test_fgt_detail_and_charts_show_every_registered_rs485_sensor(self):
        device_id = "INADS-00000000-0000-4000-8000-00000000022f"
        for seq, north, south in ((1, 25.1, 26.8), (2, 36.8, 63.2)):
            self.device_repository.record_status(
                device_id,
                {
                    "seq": seq,
                    "device_kind": "FGT",
                    "firmware_version": "0.2.3",
                    "soil_rs485_ok": True,
                    "soil_moisture_percent": north,
                    "soil_temperature_c": 30.2,
                    "soil_ec_us_cm": 109,
                    "par_ok": True,
                    "par_umol_m2_s": 840,
                    "rs485_devices": [
                        {
                            "index": 0,
                            "enabled": True,
                            "attempted": True,
                            "bus_ready": True,
                            "ok": True,
                            "type": "soil",
                            "name": "土壌センサー1",
                            "location": "ライチ北",
                            "moisture_percent": north,
                            "temperature_c": 30.2,
                            "ec_us_cm": 109,
                        },
                        {
                            "index": 1,
                            "enabled": True,
                            "attempted": True,
                            "bus_ready": True,
                            "ok": True,
                            "type": "soil",
                            "name": "土壌センサー2",
                            "location": "ライチ南",
                            "moisture_percent": south,
                            "temperature_c": 34.9,
                            "ec_us_cm": 174,
                        },
                        {
                            "index": 2,
                            "enabled": True,
                            "attempted": True,
                            "bus_ready": True,
                            "ok": True,
                            "type": "par",
                            "name": "光センサー",
                            "location": "納屋",
                            "par_umol_m2_s": 840,
                        },
                    ],
                },
            )

        response = self.client.get(f"/mqtt-devices/{device_id}?tab=monitoring")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("接続センサーの現在値", html)
        self.assertIn("土壌センサー1", html)
        self.assertIn("ライチ北", html)
        self.assertIn("土壌センサー2", html)
        self.assertIn("ライチ南", html)
        self.assertIn("63.2 %", html)
        self.assertIn("光センサー", html)
        self.assertIn("840 µmol/m²/s", html)
        self.assertIn("3 台", html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        north_label = json.dumps("土壌センサー1（ライチ北）", ensure_ascii=True)[1:-1]
        south_label = json.dumps("土壌センサー2（ライチ南）", ensure_ascii=True)[1:-1]
        par_label = json.dumps("光センサー（納屋）", ensure_ascii=True)[1:-1]
        self.assertIn(north_label, charts["soil_moisture"])
        self.assertIn(south_label, charts["soil_moisture"])
        self.assertIn("63.2", charts["soil_moisture"])
        self.assertIn(south_label, charts["soil_temperature"])
        self.assertIn(south_label, charts["soil_ec"])
        self.assertIn(par_label, charts["par"])

    def test_fgt_timed_operation_shows_duration_history_without_calibrated_ml(self):
        device_id = "INADS-00000000-0000-4000-8000-00000000021f"
        self.device_repository.record_status(
            device_id,
            {
                "seq": 1,
                "device_kind": "FGT",
                "firmware_version": "0.2.3",
                "batch_due": True,
                "batch_started": True,
                "batch_completed": True,
                "fgt_batch_elapsed_ms": 120000,
                "fgt_operation_mode": "timed_outputs",
                "fgt_timed_output": "irrigation",
                "inlet_water_ml": 0,
            },
        )

        response = self.client.get(f"/mqtt-devices/{device_id}?tab=monitoring")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        watering_chart_marker = 'data-chart-kind="watering"'
        ml_chart_marker = 'data-chart-kind="batch_water"'
        self.assertIn(watering_chart_marker, html)
        self.assertIn(ml_chart_marker, html)
        self.assertLess(html.index(watering_chart_marker), html.index(ml_chart_marker))
        self.assertIn("直近の灌水記録", html)
        self.assertIn("実行時間: 2分", html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("Plotly.newPlot", charts["watering"])
        self.assertIn('"y":[2.0]', charts["watering"])

    def test_single_purpose_sensor_pages_show_only_supported_equipment_cards(self):
        soil_device_id = "INADS-00000000-0000-4000-8000-000000000207"
        self.device_repository.record_status(
            soil_device_id,
            {
                "seq": 1,
                "device_kind": "SOI",
                "soil_moisture_percent": 43.0,
                "soil_temperature_c": 19.5,
            },
        )
        soil_html = self.client.get(f"/mqtt-devices/{soil_device_id}?tab=settings").get_data(as_text=True)
        self.assertIn('data-env-sensor-card="par" hidden', soil_html)
        self.assertIn('data-env-sensor-card="soil" hidden', soil_html)
        self.assertIn('id="soil-moisture-reference" class="setup-stage calibration-stage">', soil_html)
        self.assertIn("土壌水分計の基準合わせ", soil_html)
        self.assertIn(f'href="/mqtt-devices/{soil_device_id}?tab=monitoring#soil-moisture-chart" aria-label="土壌水分の履歴を見る"', soil_html)

        light_device_id = "INADS-00000000-0000-4000-8000-000000000208"
        self.device_repository.record_status(
            light_device_id,
            {
                "seq": 1,
                "device_kind": "PAR",
                "par_umol_m2_s": 880,
            },
        )
        light_html = self.client.get(f"/mqtt-devices/{light_device_id}?tab=settings").get_data(as_text=True)
        self.assertIn('data-env-sensor-card="par">', light_html)
        self.assertIn('data-env-sensor-card="soil" hidden', light_html)
        self.assertIn(f'href="/mqtt-devices/{light_device_id}?tab=monitoring#par-chart" aria-label="光合成に使える光の履歴を見る"', light_html)

    def test_retired_device_is_read_only_in_ui_and_mutation_apis(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000203"
        self.device_service.get_record(device_id)
        self.device_service.set_state(device_id, "retired")

        detail_response = self.client.get(f"/mqtt-devices/{device_id}?tab=settings")
        self.assertEqual(detail_response.status_code, 200)
        html = detail_response.get_data(as_text=True)
        self.assertIn('id="metadata-form" data-stateful-form', html)
        self.assertIn('data-blocked-message="廃止済みの機器情報は変更できません。"', html)
        self.assertIn('data-blocked-message="廃止済みの動作設定は変更できません。"', html)
        self.assertIn('data-blocked-message="廃止済みの更新予約は変更できません。"', html)

        metadata_response = self.client.patch(
            f"/local/api/mqtt-devices/{device_id}",
            json={"name": "変更不可"},
        )
        self.assertEqual(metadata_response.status_code, 409)
        config_response = self.client.put(
            f"/local/api/mqtt-devices/{device_id}/runtime-config",
            json=self.device_service.default_config(),
        )
        self.assertEqual(config_response.status_code, 409)
        target_response = self.client.put(
            f"/local/api/mqtt-devices/{device_id}/firmware-target",
            json={"target_firmware_version": "2.0.0"},
        )
        self.assertEqual(target_response.status_code, 409)

    def test_irrigation_schedule_spacing_warning_is_rendered_and_api_blocks_save(self):
        device_id = "INADS-WTR-SPACING-001"
        self.device_service.get_record(device_id)
        self.device_repository.record_status(device_id, {"seq": 1, "device_kind": "WTR"})

        html = self.client.get(f"/mqtt-devices/{device_id}?tab=settings").get_data(as_text=True)

        self.assertIn('id="schedule-spacing-warning"', html)
        self.assertIn("予約の間には、運転時間＋5分の余裕が必要です", html)
        self.assertIn("橙色の予約時刻または運転時間を直してください", html)

        config = self.device_service.default_config()
        config["schedules"] = [
            {"hour": 6, "minute": 0, "duration_sec": 600, "channel_mask": 1, "frequency": {"mode": "daily"}},
            {"hour": 6, "minute": 14, "duration_sec": 60, "channel_mask": 1, "frequency": {"mode": "daily"}},
        ]
        response = self.client.put(f"/local/api/mqtt-devices/{device_id}/runtime-config", json=config)

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertEqual(body["code"], "irrigation_schedule_spacing")
        self.assertEqual(body["details"][0]["shortage_sec"], 60)
        self.assertIn("次の予約を 06:15 以降", body["error"])

    def test_mqtt_device_times_are_rendered_in_local_time(self):
        utc_received_at = "2026-07-02T21:30:15+00:00"
        original_local_timezone = web_server._local_timezone
        web_server._local_timezone = lambda: timezone(timedelta(hours=9), "JST")
        self.addCleanup(lambda: setattr(web_server, "_local_timezone", original_local_timezone))

        self.assertEqual(web_server._format_datetime(utc_received_at), "2026-07-03 06:30 JST")

        statuses = [
            {
                "received_at": utc_received_at,
                "payload": {
                    "watering_due": True,
                    "watering_started": True,
                    "watering_duration_sec": 120,
                    "channel_mask": 1,
                    "last_soil_moisture": 42,
                    "threshold": 40,
                },
            }
        ]

        chart_html = web_server._build_watering_trend_chart(statuses)

        self.assertIn("2026-07-03T06:30:15", chart_html)
        self.assertNotIn("2026-07-02T21:30:15", chart_html)

        deferred_html = web_server._build_watering_trend_chart(statuses, deferred=True)
        self.assertIn('data-plotly-chart="watering-trend-chart"', deferred_html)
        self.assertIn('type="application/json"', deferred_html)
        self.assertNotIn("Plotly.newPlot", deferred_html)

    def test_mqtt_devices_query_device_id_redirects_to_detail_path(self):
        device_id = "INADS-00000000-0000-4000-8000-000000000201"

        response = self.client.get(f"/mqtt-devices?device_id={device_id}")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/mqtt-devices/{device_id}")

    def test_mqtt_devices_demo_list_renders_fixture_cards_without_detail(self):
        response = self.client.get("/demo/mqtt-devices")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("デモデータ表示中", html)
        self.assertIn("操作は保存されません", html)
        self.assertIn('href="/mqtt-devices">実データへ戻る</a>', html)
        self.assertIn("圃場ビュー", html)
        self.assertIn("北ハウス 1号", html)
        self.assertIn("南ハウス 2号", html)
        self.assertIn("西ハウス 予備機", html)
        self.assertIn("灌水中", html)
        self.assertIn('href="/demo/mqtt-devices/INADS-DEMO-WTR-002"', html)
        self.assertNotIn("灌水推移", html)
        self.assertNotIn("demo-hub.local:39151/firmware/WTR/1.1.0/firmware.bin", html)
        self.assertIn("const demoMode = true;", html)

    def test_mqtt_devices_demo_detail_renders_fixture_history(self):
        response = self.client.get("/demo/mqtt-devices/INADS-DEMO-WTR-001")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("デモデータ表示中", html)
        self.assertIn("操作は保存されません", html)
        self.assertNotIn("機器一覧へ戻る", html)
        self.assertIn('href="/mqtt-devices">実データへ戻る</a>', html)
        self.assertNotIn("圃場ビュー", html)
        self.assertNotIn("デバイス API", html)
        self.assertIn('role="tablist"', html)
        self.assertIn("設置場所・関連先", html)
        self.assertNotIn("<h2>設置ビュー</h2>", html)
        self.assertIn("高設ベッドA", html)
        self.assertIn("北ハウス 1号", html)
        self.assertIn("潅水推移", html)
        self.assertIn("土壌水分推移", html)
        self.assertNotIn("Plotly.newPlot", html)
        self.assertIn("潅水推移を読み込み中", html)
        self.assertIn("/demo/local/api/mqtt-devices/", html)
        self.assertIn("直近3日", html)
        self.assertIn("2週間", html)
        self.assertIn("1か月", html)
        self.assertIn("全期間", html)
        self.assertIn("カスタム", html)
        self.assertIn("灌水中", html)
        self.assertIn("1分", html)
        self.assertIn("系統1・系統2", html)
        self.assertIn("demo-hub.local:39151/firmware/WTR/1.1.0/firmware.bin", html)
        self.assertIn("const demoMode = true;", html)

        charts_response = self.client.get("/demo/local/api/mqtt-devices/INADS-DEMO-WTR-001/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("Plotly.newPlot", charts["watering"])
        self.assertIn("Plotly.newPlot", charts["soil_moisture"])

    def test_next_watering_schedule_uses_device_timezone_and_rolls_to_tomorrow(self):
        config = {
            "timezone_offset_sec": 32400,
            "schedules": [
                {"hour": 6, "minute": 30, "duration_sec": 90, "channel_mask": 1},
                {"hour": 17, "minute": 45, "duration_sec": 60, "channel_mask": 2},
            ],
            "mosfet_switches": [
                {"name": "潅水1系", "enabled": True, "channel_mask": 1},
                {"name": "潅水2系", "enabled": True, "channel_mask": 2},
            ],
        }

        before_evening = web_server._next_watering_schedule(config, datetime(2026, 7, 16, 7, 0, tzinfo=UTC))
        after_evening = web_server._next_watering_schedule(config, datetime(2026, 7, 16, 10, 0, tzinfo=UTC))

        self.assertEqual(before_evening["label"], "今日 17:45")
        self.assertEqual(before_evening["hint"], "潅水2系 / 1分")
        self.assertEqual(after_evening["label"], "明日 06:30")
        self.assertEqual(after_evening["hint"], "潅水1系 / 1分30秒")


def _firmware_binary(
    *,
    device_kind: str = "WTR",
    version: str = "1.1.0",
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


def _inasfw(firmware: bytes, *, device_kind: str, version: str):
    manifest = {
        "schema_version": 1,
        "module_type": "inas-device-firmware",
        "module_id": "test-device",
        "device_kind": device_kind,
        "firmware_version": version,
        "regions": [{"id": "app0", "file": "firmware.bin"}],
        "checksums": {"firmware.bin": hashlib.sha256(firmware).hexdigest()},
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("test-device/release-module.json", json.dumps(manifest))
        archive.writestr("test-device/firmware.bin", firmware)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
