import os
import tempfile
import unittest

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

from ina_device_hub.discord_notification_service import DISCORD_CONTENT_LIMIT, format_mqtt_activity  # noqa: E402


class DiscordNotificationServiceTest(unittest.TestCase):
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

    def test_format_mqtt_activity_caps_discord_message_length(self):
        content = format_mqtt_activity("received", "unknown/topic", payload={"value": "x" * 5000})

        self.assertLessEqual(len(content), DISCORD_CONTENT_LIMIT)
        self.assertIn("省略", content)


if __name__ == "__main__":
    unittest.main()
