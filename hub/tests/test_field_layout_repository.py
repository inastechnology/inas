import os
import tempfile
import threading
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

        with self.assertRaises(FieldLayoutConflictError) as raised:
            self.repository.upsert("field-1", saved)

        self.assertEqual(raised.exception.current["revision"], 1)

    def test_two_repository_instances_serialize_writes_and_reject_one_stale_revision(self):
        second_repository = FieldLayoutRepository()
        second_repository.layout_repo_path = self.repository.layout_repo_path
        first_layout = self.repository.get("field-1", "圃場")
        second_layout = second_repository.get("field-1", "圃場")
        first_layout["name"] = "画面A"
        second_layout["name"] = "画面B"
        barrier = threading.Barrier(2)
        results = []

        def save(repository, layout, actor):
            barrier.wait()
            try:
                results.append(("saved", repository.upsert("field-1", layout, updated_by=actor)))
            except FieldLayoutConflictError as error:
                results.append(("conflict", error.current))

        threads = [
            threading.Thread(target=save, args=(self.repository, first_layout, "a@example.com")),
            threading.Thread(target=save, args=(second_repository, second_layout, "b@example.com")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(result[0] for result in results), ["conflict", "saved"])
        self.assertEqual({result[1]["revision"] for result in results}, {1})
        self.assertIn(self.repository.get("field-1")["updated_by"], {"a@example.com", "b@example.com"})

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

    def test_camera_can_target_multiple_monitored_areas(self):
        layout = self.repository.get("field-1", "果樹園")
        layout["spaces"][0]["placements"] = [
            {"id": "tree-east", "preset": "tree", "name": "東側ライチ", "x": 4, "y": 4, "width": 3, "height": 3},
            {"id": "tree-west", "preset": "tree", "name": "西側ライチ", "x": 12, "y": 4, "width": 3, "height": 3},
            {
                "id": "camera-garden",
                "preset": "camera",
                "name": "庭カメラ",
                "x": 2,
                "y": 2,
                "width": 2,
                "height": 2,
                "binding": {
                    "device_id": "INACD-garden",
                    "resource_type": "camera",
                    "resource_id": "",
                    "target_placement_ids": ["tree-east", "tree-west"],
                },
            },
        ]

        saved = self.repository.upsert("field-1", layout)
        camera = saved["spaces"][0]["placements"][2]

        self.assertEqual(camera["preset"], "camera")
        self.assertEqual(camera["binding"]["resource_type"], "camera")
        self.assertEqual(camera["binding"]["target_placement_ids"], ["tree-east", "tree-west"])


if __name__ == "__main__":
    unittest.main()
