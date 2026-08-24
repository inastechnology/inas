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
from ina_device_hub.discord_notification_service import (  # noqa: E402
    DISCORD_CONTENT_LIMIT,
    cloudflare_public_base_url,
    format_health_alert,
    format_health_alert_notification,
    format_mqtt_activity,
    format_new_device,
    format_new_device_notification,
    format_operations_security_alert,
    format_plant_task_digest,
)


class DiscordNotificationServiceTest(unittest.TestCase):
    def test_operations_security_alert_contains_safe_request_metadata_only(self):
        payload = format_operations_security_alert(
            "Cloudflare Access service is not allowed",
            {
                "method": "POST",
                "path": "/operations/api/v1/devices/firmware-rollouts",
                "client_ip": "203.0.113.10",
                "cf_ray": "ray-123",
                "user_agent": "inas-hub-operations/1.0",
                "client_secret": "must-not-appear",
            },
        )

        rendered = str(payload)
        self.assertIn("認証を拒否", rendered)
        self.assertIn("203.0.113.10", rendered)
        self.assertIn("ray-123", rendered)
        self.assertNotIn("must-not-appear", rendered)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_operations_security_alert_suppresses_duplicate_fingerprint(self):
        service = discord_notification_service.DiscordNotificationService(webhook_url="https://discord.example/webhook")
        service.discord_settings = {"enabled": True, "notify_operations_security_alerts": True, "security_alert_cooldown_sec": 300}
        details = {"method": "GET", "path": "/operations/api/v1/health", "client_ip": "203.0.113.10"}

        with (
            patch.object(discord_notification_service.threading, "Thread") as thread,
            patch.object(discord_notification_service.time, "monotonic", side_effect=[1000, 1001]),
        ):
            first = service.notify_operations_security_alert("invalid JWT", details)
            second = service.notify_operations_security_alert("invalid JWT", details)

        self.assertTrue(first)
        self.assertFalse(second)
        thread.assert_called_once()

    def test_plant_task_digest_uses_visual_embed_groups(self):
        item = {
            "field_id": "field-1",
            "planting_id": "plant-1",
            "field_name": "西条圃場1",
            "crop_name": "ライチ",
            "cultivar": "ジャカパット",
            "placement_name": "植木鉢1",
            "is_new": True,
            "action": {
                "id": "action-1",
                "title": "防寒対策",
                "action_type": "winter_care",
                "reason": "最低気温が下がる前に鉢を保護します。",
                "window_start": "2026-11-01",
                "window_end": "2026-11-08",
            },
        }

        payload = format_plant_task_digest(
            {
                "date": "2026-10-25",
                "due": [],
                "upcoming": [item],
                "new": [],
                "reminder": {"days_before": 7},
            },
            base_url="https://hub.example.com",
        )

        self.assertEqual(payload["username"], "INA Device Hub")
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        summary, card = payload["embeds"]
        self.assertEqual(summary["title"], "🌿 今日の栽培作業")
        self.assertIn("⏳ 事前に確認する作業 1件", summary["description"])
        self.assertIn("開始7日前の1回", summary["footer"]["text"])
        self.assertIn("🧣 防寒対策", card["title"])
        self.assertIn("🆕", card["title"])
        self.assertIn("西条圃場1｜ライチ（ジャカパット）", card["description"])
        self.assertEqual(
            card["url"],
            "https://hub.example.com/fields/field-1/calendar?planting=plant-1&action=action-1",
        )
        self.assertNotIn("localhost", str(payload))

    def test_cloudflare_public_base_url_only_accepts_https_hostnames(self):
        self.assertEqual(
            cloudflare_public_base_url(
                {
                    "CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME": "hub.inas-technologies.com",
                    "CLOUDFLARE_TUNNEL_HOSTNAME": "fallback.example.com",
                }
            ),
            "https://hub.inas-technologies.com",
        )
        self.assertEqual(
            cloudflare_public_base_url({"CLOUDFLARE_TUNNEL_HOSTNAME": "https://tunnel.example.com/"}),
            "https://tunnel.example.com",
        )
        for value in ("http://hub.example.com", "localhost", "hub.local", "192.168.1.2", "https://example.com/path"):
            with self.subTest(value=value):
                self.assertEqual(cloudflare_public_base_url({"CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME": value}), "")

    def test_plant_task_digest_caps_cards_and_embed_characters(self):
        items = []
        for index in range(20):
            items.append(
                {
                    "field_id": "field-1",
                    "planting_id": "plant-1",
                    "field_name": "西条圃場1",
                    "crop_name": "ライチ",
                    "placement_name": "植木鉢1",
                    "action": {
                        "id": f"action-{index}",
                        "title": f"観察作業 {index}",
                        "reason": "樹勢と葉色の変化を確認します。" * 20,
                        "window_start": "2026-07-21",
                        "window_end": "2026-07-28",
                    },
                }
            )

        payload = format_plant_task_digest(
            {"date": "2026-07-21", "due": items, "upcoming": [], "new": []},
            base_url="https://hub.example.com",
        )
        embeds = payload["embeds"]
        character_count = sum(
            len(str(embed.get("title") or "")) + len(str(embed.get("description") or "")) + len(str((embed.get("footer") or {}).get("text") or ""))
            for embed in embeds
        )

        self.assertLessEqual(len(embeds), 7)
        self.assertLessEqual(character_count, 6000)
        self.assertIn("年間栽培カレンダー", embeds[0]["description"])

    def test_new_device_card_links_to_device_overview(self):
        payload = format_new_device_notification(
            "device / 1",
            {"name": "苗床の水やり", "device_kind": "WTR", "firmware_version": "1.2.3"},
            "status",
            base_url="https://hub.example.com",
        )

        card = payload["embeds"][0]
        self.assertEqual(card["title"], "🆕 新しい機器が見つかりました")
        self.assertEqual(card["url"], "https://hub.example.com/mqtt-devices/device%20%2F%201?tab=overview")
        self.assertIn("機器を確認して登録する", card["description"])

    def test_health_alert_card_opens_the_relevant_screen(self):
        payload = format_health_alert_notification(
            "device_offline",
            "device-1",
            {"name": "ハウス北側", "location": "第1圃場"},
            {"last_seen_at": "2026-07-21 03:40 JST"},
            base_url="https://hub.example.com",
        )

        card = payload["embeds"][0]
        self.assertEqual(card["url"], "https://hub.example.com/mqtt-devices/device-1?tab=maintenance")
        self.assertIn("電源、通信環境", card["description"])
        self.assertNotIn("topic:", str(payload))

    def test_post_watering_moisture_card_links_to_selected_sensor(self):
        payload = format_health_alert_notification(
            "post_watering_moisture_low",
            "watering-1",
            {"name": "北畝の潅水機", "location": "1号ハウス"},
            {
                "sensor_device_id": "soil / 1",
                "sensor_device_name": "北畝の水分計",
                "measured_percent": 43.5,
                "minimum_percent": 50.0,
                "watered_at": "2026-08-24T01:00:00+00:00",
            },
            base_url="https://hub.example.com",
        )

        card = payload["embeds"][0]
        self.assertEqual(card["url"], "https://hub.example.com/mqtt-devices/soil%20%2F%201?tab=monitoring")
        self.assertIn("潅水後の土壌水分が下限に届いていません", card["title"])
        self.assertIn("43.5%", str(card["fields"]))
        self.assertIn("50%", str(card["fields"]))
        self.assertIn("北畝の水分計", str(card["fields"]))

    def test_operational_error_card_shows_failure_reason(self):
        payload = format_health_alert_notification(
            "device_operational_error",
            "device-fgt",
            {"name": "潅水デバイス", "location": "ライチ圃場"},
            {
                "reasons": ["journal_error", "recovery_required"],
                "reason_labels": ["運転履歴を読み取れません", "安全確認後の復旧待ちです"],
                "batch_skip_reason": "recovery_required",
            },
            base_url="https://hub.example.com",
        )

        card = payload["embeds"][0]
        self.assertEqual(card["url"], "https://hub.example.com/mqtt-devices/device-fgt?tab=maintenance")
        self.assertIn("予定動作を実行できませんでした", card["title"])
        self.assertIn("運転履歴を読み取れません", str(card["fields"]))

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
