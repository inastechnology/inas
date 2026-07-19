import importlib.util
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_admin_demo_server.py"
SPEC = importlib.util.spec_from_file_location("run_admin_demo_server", SCRIPT_PATH)
run_admin_demo_server = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(run_admin_demo_server)


class AdminDemoServerTest(unittest.TestCase):
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

    def test_demo_environment_does_not_inherit_external_turso_or_ai(self):
        inherited = {
            "TURSO_DATABASE_URL": "libsql://production.example",
            "TURSO_AUTH_TOKEN": "production-token",
            "AI_ENABLED": "true",
            "AI_IMAGE_ANALYZE_API_KEY": "production-image-key",
            "AI_TEXT_ANALYZE_API_KEY": "production-text-key",
        }
        with patch.dict(os.environ, inherited, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "local-demo")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "local-demo")
            self.assertEqual(os.environ["AI_ENABLED"], "false")
            self.assertEqual(os.environ["AI_IMAGE_ANALYZE_API_KEY"], "")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "")

    def test_demo_specific_values_require_explicit_prefix(self):
        overrides = {
            "HUB_DEMO_TURSO_DATABASE_URL": "libsql://demo.example",
            "HUB_DEMO_TURSO_AUTH_TOKEN": "demo-token",
            "HUB_DEMO_AI_TEXT_ANALYZE_API_KEY": "demo-ai-key",
        }
        with patch.dict(os.environ, overrides, clear=True), patch.object(run_admin_demo_server, "load_dotenv"):
            run_admin_demo_server._prepare_env()

            self.assertEqual(os.environ["TURSO_DATABASE_URL"], "libsql://demo.example")
            self.assertEqual(os.environ["TURSO_AUTH_TOKEN"], "demo-token")
            self.assertEqual(os.environ["AI_TEXT_ANALYZE_API_KEY"], "demo-ai-key")


if __name__ == "__main__":
    unittest.main()
