import copy
import threading
from datetime import date

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.crop_knowledge_provider import crop_knowledge_provider
from ina_device_hub.field_layout_repository import field_layout_repository
from ina_device_hub.field_repository import field_repository
from ina_device_hub.general_log import logger
from ina_device_hub.plant_management_repository import plant_management_repository

RECENT_WORK_LOG_LIMIT = 12
RECENT_QUESTION_LIMIT = 8


class PlantCalendarGenerationTask:
    def __init__(self, *, plant_repository, field_repository, layout_repository, ai_service, knowledge_provider=None):
        self.plant_repository = plant_repository
        self.field_repository = field_repository
        self.layout_repository = layout_repository
        self.ai_service = ai_service
        self.knowledge_provider = knowledge_provider
        self._wake_event = threading.Event()
        self._worker_thread = None

    def start(self):
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        recovered = self.plant_repository.recover_interrupted_calendar_generations()
        if recovered:
            logger.info(f"Recovered {len(recovered)} interrupted plant calendar generation task(s)")
        self._worker_thread = threading.Thread(target=self._run, name="plant-calendar-generation", daemon=True)
        self._worker_thread.start()
        self.wake()
        logger.info(f"Start {self.__class__.__name__}")

    def wake(self):
        self._wake_event.set()

    def enqueue(self, planting_id: str, *, kind: str, start_date: str, planning_notes: str = "", audience: dict | None = None, mode: str = "automatic"):
        task = self.plant_repository.enqueue_calendar_generation(
            planting_id,
            kind=kind,
            start_date=start_date,
            planning_notes=planning_notes,
            audience=audience,
            mode=mode,
        )
        self.wake()
        return task

    def process_next(self):
        task = self.plant_repository.claim_next_calendar_generation()
        if task is None:
            return None
        try:
            context = self._generation_context(task)
            planting = context["planting"]
            guidance = self.plant_repository.guidance_examples(planting["crop_name"])
            if self.knowledge_provider is not None:
                try:
                    context["crop_knowledge"] = self.knowledge_provider.get(context)
                except Exception:  # noqa: BLE001
                    logger.exception("Crop knowledge provider failed; continuing with the general cultivation baseline")
                    context["crop_knowledge"] = {
                        "status": "error",
                        "summary": [],
                        "assumptions": [],
                        "sources": [],
                    }
            generated = self.ai_service.generate_plant_calendar(context, guidance_examples=guidance)
            return self.plant_repository.complete_calendar_generation(task["id"], generated)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Plant calendar generation failed: task_id={task['id']}, planting_id={task['planting_id']}")
            self.plant_repository.fail_calendar_generation(task["id"], str(exc))
            return None

    def _run(self):
        while True:
            try:
                if self.process_next() is not None:
                    continue
            except Exception:  # noqa: BLE001
                logger.exception("Plant calendar generation worker loop failed")
            self._wake_event.wait(timeout=1)
            self._wake_event.clear()

    def _generation_context(self, task: dict):
        planting = self.plant_repository.get_planting(task["planting_id"])
        if planting is None:
            raise RuntimeError("planting not found")
        field = self.field_repository.get(planting["field_id"])
        if field is None:
            raise RuntimeError("field not found")
        layout = self.layout_repository.get(field["id"], field_name=field.get("name", ""))
        space = next((item for item in layout["spaces"] if item["id"] == planting["space_id"]), None)
        placement = next((item for item in (space or {}).get("placements", []) if item["id"] == planting["placement_id"]), None)
        if space is None or placement is None:
            raise RuntimeError("planting placement was not found in the field layout")
        context = build_plant_generation_context(field, layout, space, placement, planting)
        requested_start = date.fromisoformat(task["start_date"])
        current_date = date.today()
        effective_start = max(requested_start, current_date)
        planted_on = date.fromisoformat(planting["planted_on"])
        context["audience"] = task.get("audience") or {}
        context["planning"] = {
            "start_date": effective_start.isoformat(),
            "requested_start_date": requested_start.isoformat(),
            "current_date": current_date.isoformat(),
            "elapsed_days_since_planting": max(0, (current_date - planted_on).days),
            "existing_planting": planted_on < current_date,
            "exclude_past_actions": True,
            "horizon_months": 12,
            "notes": task.get("planning_notes") or "",
        }
        context["fertilizer_history"] = self.plant_repository.fertilizer_effect_context(
            planting["id"],
            as_of=effective_start,
        )
        context["fertilizer_catalog"] = self.plant_repository.list_fertilizer_materials()
        # These are bounded, textual history snapshots. The AI prompt treats every
        # user-entered string as data, never as an instruction.
        context["recent_work_logs"] = [
            _work_log_generation_snapshot(item) for item in self.plant_repository.recent_work_logs(planting["id"], limit=RECENT_WORK_LOG_LIMIT)
        ]
        question_page = self.plant_repository.list_questions(
            planting["id"],
            page=1,
            page_size=RECENT_QUESTION_LIMIT,
        )
        context["recent_questions"] = [_question_generation_snapshot(item) for item in question_page.get("items") or []]
        existing_calendar = self.plant_repository.get_calendar(planting["id"])
        context["existing_calendar"] = (
            {
                "actions": [_calendar_action_generation_snapshot(action) for action in existing_calendar.get("actions") or []],
                "care_profile": copy.deepcopy(existing_calendar.get("care_profile") or {}),
                "task_rules": copy.deepcopy(existing_calendar.get("task_rules") or []),
            }
            if existing_calendar
            else None
        )
        context["planning"]["regeneration_mode"] = task.get("mode") or "automatic"
        return context


def build_plant_generation_context(field, layout, space, placement, planting):
    return {
        "planting": planting,
        "placement": {
            "id": placement.get("id"),
            "name": placement.get("name"),
            "preset": placement.get("preset"),
            "space_id": space.get("id"),
            "space_name": space.get("name"),
            "space_type": space.get("space_type"),
            "grid_cell_size_m": (space.get("grid") or {}).get("cell_size_m"),
        },
        "field": {
            "id": field.get("id"),
            "name": field.get("name"),
            "location": field.get("location") or {},
            "crop_profile": field.get("crop_profile") or {},
            "cultivation_context": field.get("cultivation_context") or {},
            "growth_targets": field.get("growth_targets") or {},
            "control_policy": field.get("control_policy") or {},
        },
        "layout": {
            "space_type": space.get("space_type"),
            "root_space_id": layout.get("root_space_id"),
        },
    }


def _calendar_action_generation_snapshot(action):
    work_plan = action.get("work_plan") if isinstance(action.get("work_plan"), dict) else {}
    return {
        key: copy.deepcopy(action.get(key))
        for key in (
            "id",
            "rule_id",
            "action_type",
            "title",
            "priority",
            "window_start",
            "window_end",
            "timing_label",
            "reason",
            "instructions",
            "tags",
            "status",
            "source",
            "required_people",
            "estimated_minutes",
            "completion",
            "skip_decision",
        )
    } | {
        "work_plan": {
            key: copy.deepcopy(work_plan.get(key) or []) for key in ("targets", "checkpoints", "start_conditions", "skip_conditions", "completion_criteria")
        }
    }


def _work_log_generation_snapshot(work_log):
    work_details = work_log.get("work_details") if isinstance(work_log.get("work_details"), dict) else {}
    execution = work_details.get("execution") if isinstance(work_details.get("execution"), dict) else {}
    execution_snapshot = {
        key: _generation_text(execution.get(key), 300)
        for key in ("target", "method_label", "method_type", "material_name", "amount_or_rate", "custom_method")
        if _generation_text(execution.get(key), 300)
    }
    follow_up_days = execution.get("follow_up_days")
    if isinstance(follow_up_days, int) and not isinstance(follow_up_days, bool):
        execution_snapshot["follow_up_days"] = follow_up_days
    attachments = work_log.get("attachments") if isinstance(work_log.get("attachments"), list) else []
    return {
        "performed_on": _generation_text(work_log.get("performed_on"), 10),
        "action_type": _generation_text(work_log.get("action_type"), 80),
        "title": _generation_text(work_log.get("title"), 180),
        "note": _generation_text(work_log.get("note"), 600),
        "rating": work_log.get("rating") if isinstance(work_log.get("rating"), int) else None,
        "execution": execution_snapshot,
        "attachment_count": min(len(attachments), 5),
    }


def _question_generation_snapshot(question):
    return {
        "created_at": _generation_text(question.get("created_at"), 40),
        "question": _generation_text(question.get("question"), 600),
        "previous_answer": _generation_text(question.get("answer"), 1200),
    }


def _generation_text(value, limit):
    return str(value or "").strip()[:limit]


__instance = None


def plant_calendar_generation_task():
    global __instance
    if not __instance:
        __instance = PlantCalendarGenerationTask(
            plant_repository=plant_management_repository(),
            field_repository=field_repository(),
            layout_repository=field_layout_repository(),
            ai_service=ai_content_service(),
            knowledge_provider=crop_knowledge_provider(),
        )
    return __instance
