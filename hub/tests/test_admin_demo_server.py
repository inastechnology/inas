import importlib.util
import os
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_admin_demo_server.py"
SPEC = importlib.util.spec_from_file_location("run_admin_demo_server", SCRIPT_PATH)
run_admin_demo_server = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(run_admin_demo_server)


class AdminDemoServerTest(unittest.TestCase):
    def test_documentation_setup_fixture_matches_firmware_fields_without_credentials(self):
        html = run_admin_demo_server._docs_demo_device_setup_page("unconfigured")

        self.assertIn("INA Water Controller Setup", html)
        self.assertIn('id="ssid"', html)
        self.assertIn('id="mqtt_broker"', html)
        self.assertIn('id="mqtt_port"', html)
        self.assertIn('value="1883"', html)
        self.assertIn("Connection settings are not configured yet.", html)
        self.assertNotIn("production", html.lower())
        self.assertNotIn("password-token", html)

    def test_documentation_setup_fixture_exposes_safe_failure_state(self):
        html = run_admin_demo_server._docs_demo_device_setup_page("wifi_failure", populated=True)

        self.assertIn("Wi-Fi connection failed before reaching the MQTT broker.", html)
        self.assertIn('value="INAS-Demo-2G"', html)
        self.assertIn('value="192.0.2.10"', html)
        self.assertIn('value="demo-device"', html)
        self.assertNotIn('value="wifi_failure"', html)

    def test_documentation_demo_index_links_to_stable_screen_states(self):
        html = run_admin_demo_server._docs_demo_index_page()

        self.assertIn("/docs-demo/device-setup?reason=unconfigured", html)
        self.assertIn(f"/fields/{run_admin_demo_server.DEMO_FIELD_ID}/layout?space=", html)
        self.assertIn(f"/fields/{run_admin_demo_server.DEMO_FIELD_ID}/calendar?view=crop&amp;review=ai", html)
        self.assertIn("運用データとは分離されています", html)

    def test_demo_date_requires_an_iso_date(self):
        with patch.dict(os.environ, {"HUB_DEMO_TODAY": "2026-07-24"}, clear=True):
            self.assertEqual(run_admin_demo_server._demo_today(), date(2026, 7, 24))

        with patch.dict(os.environ, {"HUB_DEMO_TODAY": "24/07/2026"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "YYYY-MM-DD"):
                run_admin_demo_server._demo_today()

    def test_documentation_demo_connection_history_is_safe_and_explains_normal_sleep(self):
        events = []
        now = datetime(2026, 7, 24, 6, 30, tzinfo=UTC)

        run_admin_demo_server._seed_demo_connection_history(
            lambda event_type, direction, device_id, **details: events.append(
                {"event_type": event_type, "direction": direction, "device_id": device_id, **details}
            ),
            now=now,
        )

        self.assertEqual([event["event_type"] for event in events], ["mqtt_client_connected", "mqtt_client_disconnected"])
        self.assertTrue(all(event["device_id"] == "INADS-DEMO-WTR-003" for event in events))
        self.assertEqual(events[0]["action"], "connect")
        self.assertEqual(events[1]["payload"]["reason"], "disconnect")
        self.assertNotIn("password", str(events).lower())

    def test_empty_demo_layout_gets_complete_greenhouse_fixture(self):
        empty = {
            "schema_version": 3,
            "id": "layout-demo-strawberry-field",
            "field_id": "demo-strawberry-field",
            "name": "イチゴ実証圃場",
            "root_space_id": "space-root",
            "spaces": [
                {
                    "id": "space-root",
                    "name": "イチゴ実証圃場",
                    "space_type": "field",
                    "north_angle_deg": 0,
                    "grid": {"columns": 40, "rows": 28, "cell_size_m": 0.5},
                    "placements": [],
                }
            ],
            "revision": 0,
        }

        seeded = run_admin_demo_server._demo_layout_payload(empty)

        self.assertEqual(len(seeded["spaces"]), 2)
        root = seeded["spaces"][0]
        greenhouse = next(item for item in root["placements"] if item["preset"] == "greenhouse")
        self.assertEqual(greenhouse["child_space_id"], run_admin_demo_server.DEMO_GREENHOUSE_SPACE_ID)
        house = seeded["spaces"][1]
        self.assertEqual(len([item for item in house["placements"] if item["preset"] == "ridge"]), 3)
        watering = next(item for item in house["placements"] if item["preset"] == "watering_device")
        self.assertIn(run_admin_demo_server.DEMO_PRIMARY_RIDGE_ID, watering["binding"]["target_placement_ids"])

    def test_populated_demo_layout_is_not_overwritten(self):
        existing = {
            "root_space_id": "space-root",
            "spaces": [{"id": "space-root", "placements": [{"id": "user-placement"}]}],
        }

        self.assertIs(run_admin_demo_server._demo_layout_payload(existing), existing)

    def test_demo_calendar_adds_operable_status_examples_and_yearly_work(self):
        today = date(2026, 7, 19)
        generated = [
            {
                "action_type": action_type,
                "title": title,
                "window_start": "2026-07-19",
                "window_end": "2026-07-26",
            }
            for action_type, title in (
                ("observation", "生育確認"),
                ("fertilization", "追肥判断"),
                ("pest_control", "病害虫確認"),
            )
        ]

        actions = run_admin_demo_server._prepare_demo_calendar_actions(generated, today)

        self.assertEqual(actions[0]["window_end"], "2026-07-16")
        self.assertEqual(actions[1]["window_start"], "2026-07-18")
        self.assertEqual(actions[2]["window_start"], "2026-07-21")
        self.assertTrue(any(item["action_type"] == "watering" for item in actions))
        self.assertTrue(any(item["action_type"] == "pollination" for item in actions))
        harvest = next(item for item in actions if item["action_type"] == "harvest")
        self.assertEqual(harvest["window_end"], "2027-05-15")

    def test_demo_cultivation_source_contains_public_evidence_fixture(self):
        source = Path(run_admin_demo_server.__file__).read_text(encoding="utf-8")

        self.assertIn('"crop_knowledge": {', source)
        self.assertIn("https://www.maff.go.jp/j/seisan/kankyo/hozen_type/h_sehi_kizyun/index.html", source)
        self.assertIn("https://www.naro.go.jp/laboratory/ncss/saibaishiken/manual/index.html", source)

    def test_documentation_ai_review_payload_adds_a_visible_proposal_without_mutating_calendar(self):
        calendar = {
            "actions": [
                {
                    "id": "action-planned",
                    "action_type": "observation",
                    "title": "葉色を確認",
                    "priority": "recommended",
                    "window_start": "2026-07-25",
                    "window_end": "2026-07-30",
                    "reason": "現在の理由",
                    "instructions": "現在の手順",
                    "tags": ["葉色"],
                    "status": "planned",
                },
                {
                    "id": "action-completed",
                    "action_type": "watering",
                    "title": "完了済み潅水",
                    "window_start": "2026-07-20",
                    "window_end": "2026-07-20",
                    "status": "completed",
                },
            ],
            "care_profile": {"irrigation": {"summary": "点滴潅水"}},
            "task_rules": [{"id": "weekly-observation"}],
        }
        planting = {"growth_targets": {"soil_moisture_percent": {"min": 35, "max": 60}}}

        payload = run_admin_demo_server._demo_ai_review_payload(calendar, planting, today=date(2026, 7, 24))

        self.assertEqual(calendar["actions"][0]["reason"], "現在の理由")
        self.assertEqual(payload["actions"][0]["id"], "action-planned")
        self.assertIn("AI見直し", payload["actions"][0]["tags"])
        proposal = next(item for item in payload["actions"] if item["title"] == "果実肥大と着色を定点確認")
        self.assertEqual(proposal["window_start"], "2026-07-31")
        self.assertEqual(proposal["source"], "ai_replanned")
        self.assertFalse(any(item.get("id") == "action-completed" for item in payload["actions"]))

    def test_demo_environment_does_not_inherit_external_turso_or_ai(self):
        inherited = {
            "TURSO_DATABASE_URL": "libsql://production.example",
            "TURSO_AUTH_TOKEN": "production-token",
            "S3_ENDPOINT_URL": "https://production-storage.example",
            "S3_ACCESS_KEY": "production-storage-key",
            "S3_SECRET_KEY": "production-storage-secret",
            "MQTT_BROKER_URL": "production-mqtt.example",
            "MQTT_BROKER_USERNAME": "production-mqtt-user",
            "MQTT_BROKER_PASSWORD": "production-mqtt-password",
            "AI_ENABLED": "true",
            "AI_IMAGE_ANALYZE_API_KEY": "production-image-key",
            "AI_TEXT_ANALYZE_API_KEY": "production-text-key",
            "AI_TEXT_ANALYZE_BASE_URL": "https://production-ai.example",
            "DISCORD_ENABLED": "true",
            "DISCORD_WEBHOOK_URL": "https://discord.example/production",
            "INSTAGRAM_ACCESS_TOKEN": "production-instagram-token",
            "HUB_SYNC_PARENT_BASE_URL": "https://production-parent.example",
            "HUB_BACKUP_DIR": "/production/backups",
            "DEVICE_CONFIG_DEFAULT_NTP_SERVER": "production-hub.internal",
            "WEATHER_LATITUDE": "1.2345",
            "WEATHER_LONGITUDE": "6.7890",
            "WEATHER_FORECAST_URL": "https://production-weather.example",
            "INSTAGRAM_WEATHER_FORECAST_URL": "https://production-instagram-weather.example",
            "SWITCHBOT_BASE_URL": "https://production-switchbot.example",
            "CLOUDFLARE_ACCESS_ALLOWED_EMAILS": "production@example.com",
            "CLOUDFLARE_TUNNEL_HOSTNAME": "production.example.com",
        }
        with patch.dict(os.environ, inherited, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "local-demo")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "local-demo")
            self.assertEqual(os.environ["S3_ENDPOINT_URL"], "http://127.0.0.1:9")
            self.assertEqual(os.environ["S3_ACCESS_KEY"], "demo")
            self.assertEqual(os.environ["S3_SECRET_KEY"], "demo")
            self.assertEqual(os.environ["MQTT_BROKER_URL"], "localhost")
            self.assertEqual(os.environ["MQTT_BROKER_USERNAME"], "")
            self.assertEqual(os.environ["MQTT_BROKER_PASSWORD"], "")
            self.assertEqual(os.environ["AI_ENABLED"], "false")
            self.assertEqual(os.environ["AI_IMAGE_ANALYZE_API_KEY"], "")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_BASE_URL"], "")
            self.assertEqual(os.environ["DISCORD_ENABLED"], "false")
            self.assertEqual(os.environ["DISCORD_WEBHOOK_URL"], "")
            self.assertEqual(os.environ["INSTAGRAM_ACCESS_TOKEN"], "")
            self.assertEqual(os.environ["HUB_SYNC_PARENT_BASE_URL"], "")
            self.assertEqual(os.environ["HUB_BACKUP_DIR"], "/tmp/ina-device-hub-demo/work/backups")
            self.assertEqual(os.environ["DEVICE_CONFIG_DEFAULT_NTP_SERVER"], "192.0.2.10")
            self.assertEqual(os.environ["WEATHER_LATITUDE"], "36.0")
            self.assertEqual(os.environ["WEATHER_LONGITUDE"], "138.0")
            self.assertEqual(os.environ["WEATHER_FORECAST_URL"], "https://www.data.jma.go.jp/developer/xml/feed/regular.xml")
            self.assertEqual(os.environ["INSTAGRAM_WEATHER_FORECAST_URL"], "https://www.data.jma.go.jp/developer/xml/feed/regular.xml")
            self.assertEqual(os.environ["SWITCHBOT_BASE_URL"], "https://api.switch-bot.com/v1.1")
            self.assertEqual(os.environ["CLOUDFLARE_ACCESS_ALLOWED_EMAILS"], "")
            self.assertEqual(os.environ["CLOUDFLARE_TUNNEL_HOSTNAME"], "")

    def test_demo_specific_values_require_explicit_prefix(self):
        overrides = {
            "HUB_DEMO_TURSO_DATABASE_URL": "libsql://demo.example",
            "HUB_DEMO_TURSO_AUTH_TOKEN": "demo-token",
            "HUB_DEMO_S3_ENDPOINT_URL": "https://demo-storage.example",
            "HUB_DEMO_MQTT_BROKER_URL": "demo-mqtt.example",
            "HUB_DEMO_AI_TEXT_ANALYZE_API_KEY": "demo-ai-key",
        }
        with patch.dict(os.environ, overrides, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "libsql://demo.example")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "demo-token")
            self.assertEqual(os.environ["S3_ENDPOINT_URL"], "https://demo-storage.example")
            self.assertEqual(os.environ["MQTT_BROKER_URL"], "demo-mqtt.example")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "demo-ai-key")


if __name__ == "__main__":
    unittest.main()
