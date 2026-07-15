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

from ina_device_hub.field_layout_repository import (  # noqa: E402
    FieldLayoutConflictError,
    FieldLayoutRepository,
    FieldLayoutValidationError,
)


class FieldLayoutRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = FieldLayoutRepository()
        self.repository.layout_repo_path = os.path.join(self.tmp_dir.name, ".field_layouts.json")
        self.repository.layouts = {}
        self.repository.save()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_get_returns_unsaved_default_layout(self):
        layout = self.repository.get("field-1", "イチゴ圃場")

        self.assertEqual(layout["schema_version"], 3)
        self.assertEqual(layout["revision"], 0)
        self.assertEqual(layout["root_space_id"], "space-root")
        self.assertEqual(layout["spaces"][0]["name"], "イチゴ圃場")
        self.assertEqual(layout["spaces"][0]["north_angle_deg"], 0)
        self.assertEqual(layout["spaces"][0]["grid"], {"columns": 40, "rows": 28, "cell_size_m": 0.5})
        self.assertEqual(self.repository.layouts, {})

    def test_upsert_saves_nested_space_and_device_binding(self):
        layout = self.repository.get("field-1", "イチゴ圃場")
        layout["spaces"].append(
            {
                "id": "space-house-1",
                "name": "1号ハウス",
                "space_type": "greenhouse",
                "north_angle_deg": 135,
                "grid": {"columns": 24, "rows": 12, "cell_size_m": 0.5},
                "placements": [
                    {
                        "id": "ridge-east",
                        "preset": "ridge",
                        "name": "東畝",
                        "x": 6,
                        "y": 2,
                        "width": 8,
                        "height": 2,
                    },
                    {
                        "id": "placement-wrs-1",
                        "preset": "watering_device",
                        "name": "東側潅水機",
                        "x": 2,
                        "y": 2,
                        "width": 2,
                        "height": 2,
                        "binding": {
                            "device_id": "INADS-WRS-001",
                            "resource_type": "mosfet_switch",
                            "resource_id": "watering-1",
                            "target_placement_ids": ["ridge-east"],
                        },
                    },
                ],
            }
        )
        layout["spaces"][0]["placements"].append(
            {
                "id": "placement-house-1",
                "preset": "greenhouse",
                "name": "1号ハウス",
                "x": 3,
                "y": 4,
                "width": 20,
                "height": 10,
                "child_space_id": "space-house-1",
            }
        )

        saved = self.repository.upsert("field-1", layout, field_name="イチゴ圃場")
        loaded = self.repository.get("field-1", "イチゴ圃場")

        self.assertEqual(saved["revision"], 1)
        self.assertEqual(loaded["spaces"][0]["placements"][0]["child_space_id"], "space-house-1")
        self.assertEqual(loaded["spaces"][1]["north_angle_deg"], 135)
        self.assertEqual(
            loaded["spaces"][1]["placements"][1]["binding"],
            {
                "device_id": "INADS-WRS-001",
                "resource_type": "mosfet_switch",
                "resource_id": "watering-1",
                "target_placement_ids": ["ridge-east"],
            },
        )

    def test_upsert_rejects_placement_outside_grid(self):
        layout = self.repository.get("field-1", "圃場")
        layout["spaces"][0]["placements"].append(
            {
                "id": "ridge-1",
                "preset": "ridge",
                "name": "1番畝",
                "x": 39,
                "y": 0,
                "width": 4,
                "height": 2,
            }
        )

        with self.assertRaises(FieldLayoutValidationError):
            self.repository.upsert("field-1", layout)

    def test_upsert_rejects_stale_revision(self):
        layout = self.repository.get("field-1", "圃場")
        saved = self.repository.upsert("field-1", layout)
        saved["revision"] = 0

        with self.assertRaises(FieldLayoutConflictError):
            self.repository.upsert("field-1", saved)

    def test_upsert_rejects_north_angle_outside_supported_range(self):
        layout = self.repository.get("field-1", "圃場")
        layout["spaces"][0]["north_angle_deg"] = 360

        with self.assertRaises(FieldLayoutValidationError):
            self.repository.upsert("field-1", layout)

    def test_sensor_can_target_space_across_nested_spaces(self):
        layout = self.repository.get("field-1", "圃場")
        layout["spaces"].append(
            {
                "id": "space-house-1",
                "name": "1号ハウス",
                "space_type": "greenhouse",
                "north_angle_deg": 0,
                "grid": {"columns": 20, "rows": 12, "cell_size_m": 0.5},
                "placements": [
                    {
                        "id": "sensor-house-1",
                        "preset": "sensor",
                        "name": "ハウス環境センサー",
                        "x": 2,
                        "y": 2,
                        "width": 2,
                        "height": 2,
                        "binding": {
                            "device_id": "ENV-001",
                            "resource_type": "sensor",
                            "resource_id": "environment",
                            "target_placement_ids": ["open-field-1", "shade-1"],
                        },
                    }
                ],
            }
        )
        layout["spaces"][0]["placements"].extend(
            [
                {
                    "id": "house-1",
                    "preset": "greenhouse",
                    "name": "1号ハウス",
                    "x": 2,
                    "y": 2,
                    "width": 15,
                    "height": 9,
                    "child_space_id": "space-house-1",
                },
                {"id": "open-field-1", "preset": "open_field", "name": "露地A", "x": 20, "y": 2, "width": 12, "height": 10},
                {"id": "shade-1", "preset": "shade_area", "name": "軒下", "x": 20, "y": 14, "width": 10, "height": 6},
                {"id": "fan-1", "preset": "fan", "name": "循環扇", "x": 1, "y": 18, "width": 2, "height": 2},
            ]
        )

        saved = self.repository.upsert("field-1", layout)

        sensor = saved["spaces"][1]["placements"][0]
        self.assertEqual(sensor["binding"]["target_placement_ids"], ["open-field-1", "shade-1"])


if __name__ == "__main__":
    unittest.main()
