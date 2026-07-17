import os
import struct
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
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

from ina_device_hub import discord_notification_service  # noqa: E402
from ina_device_hub.discord_notification_service import DISCORD_CONTENT_LIMIT, format_health_alert, format_mqtt_activity, format_new_device  # noqa: E402


class DiscordNotificationServiceTest(unittest.TestCase):
    def test_singleton_accessor_reuses_one_service(self):
        previous = discord_notification_service.__dict__["__instance"]
        service = object()
        discord_notification_service.__dict__["__instance"] = None
        try:
            with patch.object(discord_notification_service, "DiscordNotificationService", return_value=service) as constructor:
                first = discord_notification_service.discord_notification_service()
                second = discord_notification_service.discord_notification_service()

            self.assertIs(first, service)
            self.assertIs(second, service)
            constructor.assert_called_once_with()
        finally:
            discord_notification_service.__dict__["__instance"] = previous

    def test_format_mqtt_activity_shows_config_request_in_japanese(self):
        content = format_mqtt_activity(
            "received",
            "/INADS-00000000-0000-4000-8000-000000000001/kinds/config/request",
            payload=b'{"request":"runtime_config"}',
        )

        self.assertIn("【設定要求】デバイスが runtime config を要求しました", content)
        self.assertIn("デバイス: INADS-00000000-0000-4000-8000-000000000001", content)
        self.assertIn("要求: runtime_config", content)
        self.assertIn("topic: /INADS-00000000-0000-4000-8000-000000000001/kinds/config/request", content)

    def test_format_mqtt_activity_shows_config_reply_summary(self):
        content = format_mqtt_activity(
            "publish",
            "/INADS-00000000-0000-4000-8000-000000000001/kinds/config/reply",
            payload={
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 35,
                "force_watering": True,
                "schedules": [{"hour": 6, "minute": 30, "duration_sec": 20, "channel_mask": 1}],
            },
            mqtt_rc=0,
        )

        self.assertIn("【設定返信】Hub が runtime config を送信しました", content)
        self.assertIn("MQTT結果: 成功", content)
        self.assertIn("NTP: pool.ntp.org", content)
        self.assertIn("灌水しきい値: 35%", content)
        self.assertIn("強制灌水: はい", content)
        self.assertIn("スケジュール: 06:30 / 20秒 / ch=1", content)

    def test_format_mqtt_activity_shows_status_summary(self):
        content = format_mqtt_activity(
            "received",
            "/INADS-00000000-0000-4000-8000-000000000001/kinds/agri/immediate",
            payload=b'{"seq":994,"config_received":true,"time_synced":true,"watering_due":true,"watering_started":false,"last_soil_moisture":49,"next_sleep_sec":60,"threshold":35}',
        )

        self.assertIn("【状態通知】デバイスの稼働状態を受信しました", content)
        self.assertIn("設定受信: はい", content)
        self.assertIn("時刻同期: はい", content)
        self.assertIn("灌水開始: いいえ", content)
        self.assertIn("土壌水分: 49%", content)
        self.assertIn("次回起床: ", content)
        self.assertIn("JST (60 秒後)", content)

    def test_format_mqtt_activity_decodes_debug_log_binary_payload(self):
        payload = bytearray(16)
        payload[0:3] = b"DLG"
        payload[3] = 1
        struct.pack_into("<IHHH", payload, 4, 888, 3, 3, 0)
        payload[14] = 13
        payload[15] = 0
        payload.extend(struct.pack("<BHBBii", 2, 256, 2, 34, -72, 0))
        payload.extend(struct.pack("<BHBBii", 4, 120, 1, 71, 35 | (45 << 8), 3))
        payload.extend(struct.pack("<BHBBii", 1, 150, 1, 15, 60, 0))

        content = format_mqtt_activity(
            "received",
            "/INADS-00000000-0000-4000-8000-000000000001/kinds/debug/log",
            payload=bytes(payload),
        )

        self.assertIn("【Debug Log】デバイスの起床ログを受信しました", content)
        self.assertIn("Debug seq: 888", content)
        self.assertIn("Records: 3/3 sent, dropped=0", content)
        self.assertIn("[WARNING] Wi-Fi 接続成功 (WIFI_CONNECTED) @ NETWORK:256", content)
        self.assertIn("rssi=-72 dBm", content)
        self.assertIn("[INFO] 灌水判定 (WATERING_DECISION) @ WATERING:120", content)
        self.assertIn("soil=35%, threshold=45%, force_watering=いいえ, output_mask=3", content)
        self.assertIn("[INFO] 次回 sleep 計画 (SLEEP_PLANNED) @ APP:150", content)
        self.assertNotIn("```json", content)

    def test_format_mqtt_activity_caps_discord_message_length(self):
        content = format_mqtt_activity("received", "unknown/topic", payload={"value": "x" * 5000})

        self.assertLessEqual(len(content), DISCORD_CONTENT_LIMIT)
        self.assertIn("省略", content)

    def test_format_new_device_shows_device_metadata(self):
        content = format_new_device(
            "INADS-00000000-0000-4000-8000-000000000005",
            {
                "state": "pending",
                "first_seen_at": "2026-07-01T09:01:40+00:00",
                "device_kind": "WTR",
                "firmware_version": "0.0.0-dev",
                "firmware_build_id": "Jul  1 2026 13:29:43",
            },
            "status",
            payload={"seq": 366, "time_synced": True, "last_soil_moisture": 100, "next_sleep_sec": 60},
        )

        self.assertIn("【新規デバイス検出】未登録デバイスが接続しました", content)
        self.assertIn("デバイス: INADS-00000000-0000-4000-8000-000000000005", content)
        self.assertIn("状態: pending", content)
        self.assertIn("検出元: status", content)
        self.assertIn("種別: WTR", content)
        self.assertIn("FW: 0.0.0-dev", content)
        self.assertIn("土壌水分: 100%", content)

    def test_format_health_alert_shows_offline_details(self):
        content = format_health_alert(
            "device_offline",
            "INADS-00000000-0000-4000-8000-000000000006",
            {"state": "active", "name": "north bed", "location": "greenhouse", "device_kind": "WTR"},
            {"last_seen_at": "2026-07-04 06:32:13 JST", "offline_hours": 12.5, "offline_threshold_hours": 12},
        )

        self.assertIn("【死活監視】デバイスの接続が途絶えています", content)
        self.assertIn("名前: north bed", content)
        self.assertIn("場所: greenhouse", content)
        self.assertIn("未接続時間: 12.5 時間", content)


if __name__ == "__main__":
    unittest.main()
