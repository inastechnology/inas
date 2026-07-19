import os
import tempfile
import unittest
from datetime import date, timedelta

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")

from ina_device_hub.field_layout_repository import FieldLayoutRepository  # noqa: E402
from ina_device_hub.field_repository import FieldRepository  # noqa: E402
from ina_device_hub.plant_calendar_generation_task import PlantCalendarGenerationTask  # noqa: E402
from ina_device_hub.plant_management_repository import PlantManagementRepository  # noqa: E402


class FakeAIService:
    def __init__(self, error=None):
        self.error = error
        self.contexts = []

    def generate_plant_calendar(self, context, guidance_examples=None):
        self.contexts.append(context)
        if self.error:
            raise self.error
        return {
            "growth_targets": {"soil_moisture_percent": {"min": 34, "max": 64}},
            "actions": [
                {
                    "action_type": "observation",
                    "title": "新梢を確認",
                    "window_start": context["planning"]["start_date"],
                    "window_end": "2026-07-31",
                }
            ],
            "generation": {"source": "test"},
        }


class FakeKnowledgeProvider:
    def __init__(self):
        self.contexts = []

    def get(self, context):
        self.contexts.append(context)
        return {
            "status": "available",
            "summary": ["公的資料の要点"],
            "sources": [{"title": "農研機構資料", "url": "https://www.naro.go.jp/manual"}],
        }


class FailingKnowledgeProvider:
    def get(self, context):
        raise RuntimeError("search unavailable")


class PlantCalendarGenerationTaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.field_repository = FieldRepository()
        self.field_repository.field_repo_path = os.path.join(self.tmp_dir.name, ".fields.json")
        self.field_repository.fields = {}
        self.field_repository.save()
        self.layout_repository = FieldLayoutRepository()
        self.layout_repository.layout_repo_path = os.path.join(self.tmp_dir.name, ".field_layouts.json")
        self.layout_repository.layouts = {}
        self.layout_repository.save()
        self.plant_repository = PlantManagementRepository()
        self.plant_repository.repository_path = os.path.join(self.tmp_dir.name, ".plant_management.json")
        self.plant_repository.data = {
            "schema_version": 1,
            "plantings": {},
            "calendars": {},
            "generation_tasks": [],
            "feedback": [],
            "work_logs": [],
            "questions": [],
        }
        self.plant_repository.save()
        self.field = self.field_repository.upsert(None, {"name": "果樹圃場"})
        layout = self.layout_repository.get(self.field["id"], field_name=self.field["name"])
        layout["spaces"][0]["placements"].append({"id": "pot-a", "preset": "pot", "name": "鉢A", "x": 1, "y": 1, "width": 1, "height": 1})
        self.layout_repository.upsert(self.field["id"], layout, field_name=self.field["name"])
        self.planting = self.plant_repository.create_planting(
            self.field["id"],
            {
                "space_id": "space-root",
                "placement_id": "pot-a",
                "placement_name": "鉢A",
                "crop_name": "ブルーベリー",
                "planted_on": "2026-07-14",
                "plant_count": 1,
            },
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _task(self, ai_service, knowledge_provider=None):
        return PlantCalendarGenerationTask(
            plant_repository=self.plant_repository,
            field_repository=self.field_repository,
            layout_repository=self.layout_repository,
            ai_service=ai_service,
            knowledge_provider=knowledge_provider,
        )

    def test_process_next_builds_context_and_completes_calendar(self):
        ai_service = FakeAIService()
        task_runner = self._task(ai_service)
        self.plant_repository.create_fertilizer_application(
            self.planting["id"],
            {
                "applied_on": "2026-07-14",
                "material_kind": "cattle_manure",
                "material_name": "牛ふん堆肥",
                "amount_kg": 20,
                "nutrient_percent": {"n": 2, "p2o5": 1, "k2o": 1},
                "annual_available_percent": 10,
                "effect_years": 2,
            },
        )
        requested_start = (date.today() + timedelta(days=3)).isoformat()
        queued = task_runner.enqueue(
            self.planting["id"],
            kind="initial",
            start_date=requested_start,
            planning_notes="週末だけ作業",
            audience={"experience_level": "beginner"},
        )

        result = task_runner.process_next()

        self.assertEqual(result["task"]["id"], queued["id"])
        self.assertEqual(result["task"]["status"], "succeeded")
        self.assertEqual(result["calendar"]["actions"][0]["title"], "新梢を確認")
        self.assertEqual(ai_service.contexts[0]["fertilizer_history"]["applications"][0]["material_name"], "牛ふん堆肥")
        self.assertIn("builtin:compound-8-8-8", {item["id"] for item in ai_service.contexts[0]["fertilizer_catalog"]})
        self.assertGreater(ai_service.contexts[0]["fertilizer_history"]["effect_summary"]["nutrients"]["n"]["remaining_kg"], 0)
        self.assertEqual(ai_service.contexts[0]["placement"]["name"], "鉢A")
        self.assertEqual(ai_service.contexts[0]["planning"]["start_date"], requested_start)
        self.assertEqual(ai_service.contexts[0]["planning"]["current_date"], date.today().isoformat())
        self.assertEqual(ai_service.contexts[0]["planning"]["notes"], "週末だけ作業")
        self.assertEqual(ai_service.contexts[0]["audience"]["experience_level"], "beginner")

    def test_process_next_adds_public_crop_knowledge_before_ai_generation(self):
        ai_service = FakeAIService()
        knowledge_provider = FakeKnowledgeProvider()
        task_runner = self._task(ai_service, knowledge_provider)
        task_runner.enqueue(self.planting["id"], kind="initial", start_date=date.today().isoformat())

        task_runner.process_next()

        self.assertEqual(len(knowledge_provider.contexts), 1)
        self.assertEqual(ai_service.contexts[0]["crop_knowledge"]["status"], "available")
        self.assertEqual(ai_service.contexts[0]["crop_knowledge"]["sources"][0]["title"], "農研機構資料")

    def test_crop_knowledge_failure_does_not_fail_calendar_generation(self):
        ai_service = FakeAIService()
        task_runner = self._task(ai_service, FailingKnowledgeProvider())
        task_runner.enqueue(self.planting["id"], kind="initial", start_date=date.today().isoformat())

        result = task_runner.process_next()

        self.assertEqual(result["task"]["status"], "succeeded")
        self.assertEqual(ai_service.contexts[0]["crop_knowledge"]["status"], "error")

    def test_process_next_persists_failure_without_creating_calendar(self):
        task_runner = self._task(FakeAIService(RuntimeError("AI unavailable")))
        task_runner.enqueue(self.planting["id"], kind="initial", start_date="2026-07-20")

        result = task_runner.process_next()

        self.assertIsNone(result)
        bundle = self.plant_repository.field_bundle(self.field["id"])
        self.assertEqual(bundle["generation_tasks"][0]["status"], "failed")
        self.assertEqual(bundle["generation_tasks"][0]["error"], "AI unavailable")
        self.assertEqual(bundle["calendars"], {})

    def test_past_requested_start_is_kept_as_history_but_effective_start_is_today(self):
        ai_service = FakeAIService()
        task_runner = self._task(ai_service)
        task_runner.enqueue(self.planting["id"], kind="initial", start_date="2026-03-24")

        task_runner.process_next()

        planning = ai_service.contexts[0]["planning"]
        self.assertEqual(planning["requested_start_date"], "2026-03-24")
        self.assertEqual(planning["start_date"], date.today().isoformat())
        self.assertTrue(planning["exclude_past_actions"])
        self.assertGreater(planning["elapsed_days_since_planting"], 0)


if __name__ == "__main__":
    unittest.main()
