import hashlib
import os
import tempfile
import unittest
from datetime import timedelta, timezone

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

from ina_device_hub import web_server  # noqa: E402
from ina_device_hub.device_config_repository import DeviceConfigRepository  # noqa: E402
from ina_device_hub.device_config_service import DeviceConfigService  # noqa: E402
from ina_device_hub.ota_update_service import FirmwareArtifactRepository, OTAUpdateService  # noqa: E402
from ina_device_hub.setting import setting  # noqa: E402


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
        self.original_ota_update_service = web_server.ota_update_service
        self.original_list_device_events = web_server.list_device_events
        web_server.device_config_service = lambda: self.device_service
        web_server.ota_update_service = lambda: self.service
        web_server.list_device_events = lambda *args, **kwargs: []
        self.client = web_server.app.test_client()

    def tearDown(self):
        setting().settings["firmware"] = self.original_firmware_settings
        web_server.device_config_service = self.original_device_config_service
        web_server.ota_update_service = self.original_ota_update_service
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

    def test_upload_rejects_invalid_boolean_form_value(self):
        response = self.client.post(
            "/local/api/firmware-artifacts/WTR/1.1.0/upload?force=maybe",
            data=b"test-firmware-binary",
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("force must be a boolean", response.get_json()["error"])

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
        self.assertIn("水やり機一覧", html)
        self.assertIn("圃場ビュー", html)
        self.assertIn("灌水中", html)
        self.assertIn("42%", html)
        self.assertIn(f'href="/mqtt-devices/{device_id}"', html)
        self.assertNotIn("灌水推移", html)
        self.assertNotIn('id="metadata-form"', html)

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

        response = self.client.get(f"/mqtt-devices/{device_id}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Hub 管理パネル", html)
        self.assertIn("機器一覧へ戻る", html)
        self.assertNotIn("圃場ビュー", html)
        self.assertNotIn("デバイス API", html)
        self.assertNotIn("イベント API", html)
        self.assertIn('role="tablist"', html)
        self.assertIn('data-tab-target="tab-overview"', html)
        self.assertIn('data-tab-target="tab-monitoring"', html)
        self.assertIn('data-tab-target="tab-config"', html)
        self.assertIn('data-tab-target="tab-firmware"', html)
        self.assertIn('data-tab-target="tab-diagnostics"', html)
        self.assertIn(">計測・稼働</button>", html)
        self.assertIn(">動作設定</button>", html)
        self.assertIn(">F/W更新</button>", html)
        self.assertIn(">履歴・診断</button>", html)
        self.assertIn("設置ビュー", html)
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
        self.assertIn("次回起床", html)
        self.assertIn("起動・通信履歴", html)
        self.assertIn("動作設定", html)
        self.assertIn(f'href="/mqtt-devices/{device_id}?tab=settings"', html)
        self.assertIn(f'aria-label="{device_id}の動作設定"', html)
        self.assertIn('data-state-action="approve"', html)
        self.assertIn('id="metadata-form"', html)
        self.assertIn('id="runtime-config-json"', html)
        self.assertIn('id="save-push-runtime-config"', html)
        self.assertIn('id="firmware-target-form"', html)
        self.assertIn('<select id="target-firmware-version">', html)
        self.assertIn('id="firmware-upload-form"', html)
        self.assertIn('id="firmware-version" name="version" type="text" value="" readonly', html)
        self.assertIn('id="inspect-firmware-manifest"', html)
        self.assertIn("firmware.bin を選択すると", html)
        self.assertIn("2026-07-01T00:00:00Z+abcdef0", html)
        self.assertIn("/local/api/firmware-artifacts/", html)
        self.assertIn("OTA Status History", html)
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
        self.assertIn('const tabAliases = { irrigation: "monitoring", config: "settings", maintenance: "diagnostics" };', html)

        charts_response = self.client.get(f"/local/api/mqtt-devices/{device_id}/charts")
        self.assertEqual(charts_response.status_code, 200)
        charts = charts_response.get_json()
        self.assertIn("Plotly.newPlot", charts["air_temperature"])
        self.assertIn("Plotly.newPlot", charts["air_humidity"])
        self.assertIn("Plotly.newPlot", charts["par"])
        self.assertIsNone(charts["watering"])

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
        self.assertIn("機器一覧へ戻る", html)
        self.assertNotIn("圃場ビュー", html)
        self.assertNotIn("デバイス API", html)
        self.assertIn('role="tablist"', html)
        self.assertIn("設置ビュー", html)
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


if __name__ == "__main__":
    unittest.main()
