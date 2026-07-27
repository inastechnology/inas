import json
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

from ina_device_hub.plant_management_repository import (  # noqa: E402
    PlantManagementConflictError,
    PlantManagementRepository,
    PlantManagementValidationError,
)


class GuidedWorkRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repository = PlantManagementRepository()
        self.repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.repository.data = {
            "schema_version": 2,
            "plantings": {},
            "calendars": {},
            "generation_tasks": [],
            "feedback": [],
            "work_logs": [],
            "questions": [],
            "fertilizer_applications": [],
            "fertilizer_materials": [],
            "work_routes": {},
            "work_route_runs": {},
        }
        self.repository.save()
        self.planting = self.repository.create_planting(
            "field-1",
            {
                "space_id": "root",
                "placement_id": "bed-1",
                "placement_name": "畝1",
                "crop_name": "トマト",
                "planted_on": "2026-04-01",
                "plant_count": 10,
            },
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _route(self, title="施肥判断"):
        return self.repository.create_work_route(
            self.planting["id"],
            {
                "action_id": "action-1",
                "title": title,
                "summary": "必要性を確かめてから施肥する",
                "entry_step_id": "measure",
                "steps": [
                    {
                        "id": "measure",
                        "type": "measure",
                        "title": "土壌ECを確認",
                        "metric": "soil_ec_us_cm",
                        "next_step_id": "decide",
                        "missing_step_id": "observe",
                    },
                    {"id": "observe", "type": "observe", "title": "葉色を目視確認", "next_step_id": "decide"},
                    {
                        "id": "decide",
                        "type": "decide",
                        "title": "施肥が必要か判断",
                        "choices": [
                            {"id": "yes", "label": "必要", "next_step_id": "perform"},
                            {"id": "no", "label": "不要", "next_step_id": ""},
                        ],
                    },
                    {"id": "perform", "type": "perform", "title": "液肥を施用"},
                ],
            },
        )

    def test_missing_measurement_falls_back_and_decision_completes(self):
        route = self._route()
        self.assertEqual("action-1", route["action_id"])
        run = self.repository.start_work_route(self.planting["id"], route["id"])
        run = self.repository.answer_work_route_step(
            self.planting["id"], run["id"], "measure", {"outcome": "missing", "note": "センサー未設置"}
        )
        self.assertEqual("observe", run["current_step_id"])
        run = self.repository.answer_work_route_step(self.planting["id"], run["id"], "observe", {})
        run = self.repository.answer_work_route_step(
            self.planting["id"], run["id"], "decide", {"choice_id": "no"}
        )
        self.assertEqual("completed", run["status"])
        self.assertEqual("", run["current_step_id"])

    def test_dependency_blocks_start_until_previous_route_is_complete(self):
        first = self._route("状態確認")
        second = self.repository.create_work_route(
            self.planting["id"],
            {
                "title": "施肥",
                "entry_step_id": "perform",
                "steps": [{"id": "perform", "type": "perform", "title": "施肥する"}],
                "dependencies": [{"route_id": first["id"], "type": "completed", "label": "状態確認を先に完了"}],
            },
        )
        with self.assertRaises(PlantManagementConflictError):
            self.repository.start_work_route(self.planting["id"], second["id"])
        run = self.repository.start_work_route(self.planting["id"], first["id"])
        run = self.repository.answer_work_route_step(self.planting["id"], run["id"], "measure", {"outcome": "completed", "value": 540})
        run = self.repository.answer_work_route_step(self.planting["id"], run["id"], "decide", {"choice_id": "no"})
        self.assertEqual("completed", run["status"])
        self.assertEqual("in_progress", self.repository.start_work_route(self.planting["id"], second["id"])["status"])

    def test_loop_is_rejected(self):
        with self.assertRaises(PlantManagementValidationError):
            self.repository.create_work_route(
                self.planting["id"],
                {
                    "title": "循環",
                    "entry_step_id": "a",
                    "steps": [
                        {"id": "a", "type": "perform", "title": "A", "next_step_id": "b"},
                        {"id": "b", "type": "verify", "title": "B", "next_step_id": "a"},
                    ],
                },
            )

    def test_rewind_restores_previous_step_and_removes_its_result(self):
        route = self._route()
        run = self.repository.start_work_route(self.planting["id"], route["id"])
        run = self.repository.answer_work_route_step(
            self.planting["id"], run["id"], "measure", {"outcome": "completed", "value": 510, "note": "潅水前"}
        )
        self.assertEqual("decide", run["current_step_id"])
        result = self.repository.rewind_work_route_step(self.planting["id"], run["id"])
        self.assertEqual("measure", result["run"]["current_step_id"])
        self.assertEqual([], result["run"]["history"])
        self.assertEqual("510.0", result["restored_result"]["value"])
        self.assertEqual("潅水前", result["restored_result"]["note"])

    def test_schema_upgrade_retires_pending_actions_and_keeps_audit_data(self):
        path = self.repository.repository_path
        legacy = {
            **self.repository.data,
            "schema_version": 1,
            "calendars": {
                "calendar-1": {
                    "id": "calendar-1",
                    "planting_id": self.planting["id"],
                    "field_id": "field-1",
                    "actions": [{
                        "id": "old-task",
                        "action_type": "other",
                        "title": "旧作業",
                        "window_start": "2026-07-01",
                        "window_end": "2026-07-02",
                    }],
                }
            },
            "work_logs": [{"id": "history-1", "field_id": "field-1", "planting_id": self.planting["id"]}],
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(legacy, file)
        reloaded = PlantManagementRepository()
        reloaded.repository_path = path
        reloaded.load()
        self.assertIn("work_routes", reloaded.data)
        self.assertIn("work_route_runs", reloaded.data)
        self.assertEqual([], reloaded.data["calendars"]["calendar-1"]["actions"])
        self.assertEqual("history-1", reloaded.data["work_logs"][0]["id"])


if __name__ == "__main__":
    unittest.main()
