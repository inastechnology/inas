import copy
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta

from ina_device_hub.collection_search import matches_search, paginate, search_terms
from ina_device_hub.fertilizer_effect import fertilizer_effect_summary
from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.plant_action_catalog import (
    is_known_plant_action_type,
    normalize_plant_action_type,
    plant_action_type_codes,
    plant_action_types,
)
from ina_device_hub.plant_work_catalog import default_action_work_plan
from ina_device_hub.setting import setting

MAX_PLANTINGS = 2000
MAX_ACTIONS_PER_CALENDAR = 100
MAX_FEEDBACK = 3000
MAX_WORK_LOGS = 5000
MAX_QUESTIONS = 1000
MAX_GENERATION_TASKS = 500
MAX_FERTILIZER_APPLICATIONS = 5000

VALID_PLANTING_STATUSES = {"active", "harvested", "removed"}
VALID_CROP_CATEGORIES = {"vegetable", "fruit_tree", "flower", "herb", "other"}
VALID_ACTION_STATUSES = {"planned", "in_progress", "completed", "skipped"}
VALID_GENERATION_TASK_STATUSES = {"queued", "running", "succeeded", "failed"}
ACTIVE_GENERATION_TASK_STATUSES = {"queued", "running"}
VALID_GENERATION_TASK_KINDS = {"initial", "regenerate"}
VALID_FERTILIZER_MATERIAL_KINDS = {
    "cattle_manure",
    "poultry_manure",
    "compost",
    "organic_fertilizer",
    "chemical_fertilizer",
    "custom",
}
ACTION_STATUS_TRANSITIONS = {
    "planned": {"in_progress", "skipped"},
    "in_progress": {"planned", "skipped"},
    "completed": set(),
    "skipped": {"planned"},
}
VALID_ACTION_PRIORITIES = {"required", "should", "recommended", "optional"}
VALID_WORK_METHOD_TYPES = {
    "observation",
    "manual",
    "device",
    "material_application",
    "chemical",
    "physical",
    "biological",
    "cultural",
    "other",
}
VALID_WORK_FREQUENCY_MODES = {"one_time", "as_needed", "interval", "seasonal", "continuous"}
VALID_RECURRENCE_TYPES = {"one_time", "interval_after_completion", "seasonal", "condition_based", "continuous_review"}
VALID_RECURRENCE_ANCHORS = {"planting_date", "completion_date", "calendar_date", "observation"}
VALID_ACTION_TYPES = plant_action_type_codes()
PLANTING_TARGET_RANGES = {
    "soil_moisture_percent": (0.0, 100.0),
    "soil_ec_us_cm": (0.0, 3000.0),
    "soil_ph": (0.0, 14.0),
    "air_humidity_percent": (0.0, 100.0),
    "par_umol_m2_s": (0.0, 2000.0),
}


class PlantManagementValidationError(ValueError):
    pass


class PlantManagementNotFoundError(ValueError):
    pass


class PlantManagementConflictError(ValueError):
    pass


class PlantManagementRepository:
    repository_path = os.path.join(setting().get_work_dir(), ".plant_management.json")

    def __init__(self):
        self.data = _empty_data()
        self.load()

    def load(self):
        if not os.path.exists(self.repository_path):
            atomic_write_json(self.repository_path, _empty_data())
        try:
            with open(self.repository_path, encoding="utf-8") as file:
                loaded = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            loaded = {}
        self.data = _normalize_data(loaded)

    def save(self):
        atomic_write_json(self.repository_path, self.data)

    @serialized_repository_write("repository_path")
    def create_planting(self, field_id: str, value: dict):
        if not isinstance(value, dict):
            raise PlantManagementValidationError("planting data must be an object")
        field_id = _required_string(field_id, "field_id", 120)
        placement_id = _required_string(value.get("placement_id"), "placement_id", 120)
        for planting in self.data["plantings"].values():
            if planting["field_id"] == field_id and planting["placement_id"] == placement_id and planting["status"] == "active":
                raise PlantManagementValidationError("an active planting already exists at this placement")

        now = _utc_now()
        planting_id = str(uuid.uuid4())
        crop_category = _crop_category(value.get("crop_category"), value.get("crop_name"))
        record = {
            "id": planting_id,
            "field_id": field_id,
            "space_id": _required_string(value.get("space_id"), "space_id", 120),
            "placement_id": placement_id,
            "placement_name": _required_string(value.get("placement_name"), "placement_name", 120),
            "crop_name": _required_string(value.get("crop_name"), "crop_name", 120),
            "cultivar": _clean_string(value.get("cultivar"))[:120],
            "crop_category": crop_category,
            "tree_age_years": _tree_age(value.get("tree_age_years"), crop_category),
            "planted_on": _date_string(value.get("planted_on"), "planted_on"),
            "plant_count": _bounded_int(value.get("plant_count"), 1, 1, 100000, "plant_count"),
            "cultivation_method": _clean_string(value.get("cultivation_method"))[:120],
            "conditions": _normalize_conditions(value.get("conditions")),
            "growth_targets": _normalize_growth_targets(value.get("growth_targets")),
            "memo": _clean_string(value.get("memo"))[:1000],
            "status": "active",
            "calendar_id": "",
            "created_at": now,
            "updated_at": now,
        }
        if len(self.data["plantings"]) >= MAX_PLANTINGS:
            raise PlantManagementValidationError("planting limit reached")
        self.data["plantings"][planting_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("repository_path")
    def update_planting(self, planting_id: str, value: dict):
        record = self._planting(planting_id)
        if not isinstance(value, dict):
            raise PlantManagementValidationError("planting data must be an object")
        for key in ("crop_name", "cultivar", "cultivation_method", "memo"):
            if key in value:
                record[key] = _clean_string(value.get(key))[: 1000 if key == "memo" else 120]
        if not record["crop_name"]:
            raise PlantManagementValidationError("crop_name is required")
        if "crop_category" in value:
            record["crop_category"] = _crop_category(value.get("crop_category"), record["crop_name"])
        if "tree_age_years" in value or "crop_category" in value:
            record["tree_age_years"] = _tree_age(value.get("tree_age_years", record.get("tree_age_years")), record["crop_category"])
        if "planted_on" in value:
            record["planted_on"] = _date_string(value.get("planted_on"), "planted_on")
        if "plant_count" in value:
            record["plant_count"] = _bounded_int(value.get("plant_count"), 1, 1, 100000, "plant_count")
        if "conditions" in value:
            record["conditions"] = _normalize_conditions(value.get("conditions"))
        if "growth_targets" in value:
            record["growth_targets"] = _normalize_growth_targets(value.get("growth_targets"))
        if "status" in value:
            status = _clean_string(value.get("status"))
            if status not in VALID_PLANTING_STATUSES:
                raise PlantManagementValidationError("unsupported planting status")
            record["status"] = status
        record["updated_at"] = _utc_now()
        self.data["plantings"][planting_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("repository_path")
    def create_calendar(
        self,
        planting_id: str,
        actions: list,
        generation: dict | None = None,
        *,
        care_profile: dict | None = None,
        task_rules: list | None = None,
    ):
        planting = self._planting(planting_id)
        if planting.get("calendar_id") and planting["calendar_id"] in self.data["calendars"]:
            raise PlantManagementValidationError("calendar already exists for this planting")
        if not isinstance(actions, list) or not actions:
            raise PlantManagementValidationError("calendar actions must be a non-empty array")
        if len(actions) > MAX_ACTIONS_PER_CALENDAR:
            raise PlantManagementValidationError(f"calendar actions must contain {MAX_ACTIONS_PER_CALENDAR} entries or less")

        calendar_id = str(uuid.uuid4())
        now = _utc_now()
        normalized_actions = [_normalize_action(action, index) for index, action in enumerate(actions)]
        record = {
            "id": calendar_id,
            "planting_id": planting_id,
            "field_id": planting["field_id"],
            "revision": 1,
            "actions": normalized_actions,
            "care_profile": _normalize_care_profile(care_profile),
            "task_rules": _normalize_task_rules(task_rules),
            "generation": _normalize_generation(generation),
            "created_at": now,
            "updated_at": now,
        }
        self.data["calendars"][calendar_id] = record
        planting["calendar_id"] = calendar_id
        planting["updated_at"] = now
        self.data["plantings"][planting_id] = planting
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("repository_path")
    def enqueue_calendar_generation(
        self,
        planting_id: str,
        *,
        kind: str,
        start_date: str,
        planning_notes: str = "",
        audience: dict | None = None,
    ):
        planting = self._planting(planting_id)
        kind = _clean_string(kind)
        if kind not in VALID_GENERATION_TASK_KINDS:
            raise PlantManagementValidationError("unsupported calendar generation kind")
        for task in self.data["generation_tasks"]:
            if task.get("planting_id") == planting_id and task.get("status") in ACTIVE_GENERATION_TASK_STATUSES:
                raise PlantManagementConflictError("calendar generation is already in progress")

        now = _utc_now()
        task = {
            "id": str(uuid.uuid4()),
            "field_id": planting["field_id"],
            "planting_id": planting_id,
            "kind": kind,
            "status": "queued",
            "start_date": _date_string(start_date, "start_date"),
            "planning_notes": _clean_string(planning_notes)[:2000],
            "audience": copy.deepcopy(audience) if isinstance(audience, dict) else {},
            "attempts": 0,
            "error": "",
            "created_at": now,
            "started_at": "",
            "finished_at": "",
            "updated_at": now,
        }
        self.data["generation_tasks"].append(task)
        self.data["generation_tasks"] = _trim_generation_tasks(self.data["generation_tasks"])
        self.save()
        return copy.deepcopy(task)

    @serialized_repository_write("repository_path")
    def claim_next_calendar_generation(self):
        queued = [task for task in self.data["generation_tasks"] if task.get("status") == "queued"]
        if not queued:
            return None
        task = min(queued, key=lambda item: (item.get("created_at") or "", item.get("id") or ""))
        now = _utc_now()
        task["status"] = "running"
        task["attempts"] = int(task.get("attempts") or 0) + 1
        task["started_at"] = now
        task["finished_at"] = ""
        task["error"] = ""
        task["updated_at"] = now
        self.save()
        return copy.deepcopy(task)

    @serialized_repository_write("repository_path")
    def recover_interrupted_calendar_generations(self):
        recovered = []
        now = _utc_now()
        for task in self.data["generation_tasks"]:
            if task.get("status") != "running":
                continue
            task["status"] = "queued"
            task["started_at"] = ""
            task["updated_at"] = now
            recovered.append(copy.deepcopy(task))
        if recovered:
            self.save()
        return recovered

    @serialized_repository_write("repository_path")
    def complete_calendar_generation(self, task_id: str, generated: dict):
        task = self._generation_task(task_id)
        if task.get("status") != "running":
            raise PlantManagementConflictError("calendar generation task is not running")
        if not isinstance(generated, dict):
            raise PlantManagementValidationError("generated calendar must be an object")
        actions = generated.get("actions")
        if not isinstance(actions, list) or not actions:
            raise PlantManagementValidationError("calendar actions must be a non-empty array")
        if len(actions) > MAX_ACTIONS_PER_CALENDAR:
            raise PlantManagementValidationError(f"calendar actions must contain {MAX_ACTIONS_PER_CALENDAR} entries or less")

        planting = self._planting(task["planting_id"])
        planting["growth_targets"] = _normalize_growth_targets(generated.get("growth_targets") or planting.get("growth_targets") or {})
        planting["updated_at"] = _utc_now()
        calendar = self.data["calendars"].get(planting.get("calendar_id"))
        if calendar is None:
            calendar_id = str(uuid.uuid4())
            now = _utc_now()
            calendar = {
                "id": calendar_id,
                "planting_id": planting["id"],
                "field_id": planting["field_id"],
                "revision": 1,
                "actions": [_normalize_action(action, index) for index, action in enumerate(actions)],
                "care_profile": _normalize_care_profile(generated.get("care_profile")),
                "task_rules": _normalize_task_rules(generated.get("task_rules")),
                "generation": _normalize_generation(generated.get("generation")),
                "created_at": now,
                "updated_at": now,
            }
            planting["calendar_id"] = calendar_id
        else:
            calendar = copy.deepcopy(calendar)
            preserved = [copy.deepcopy(action) for action in calendar["actions"] if action.get("status") != "planned"]
            regenerated = [_normalize_action(action, index) for index, action in enumerate(actions)]
            calendar["actions"] = preserved + regenerated
            calendar["care_profile"] = _normalize_care_profile(generated.get("care_profile"))
            calendar["task_rules"] = _normalize_task_rules(generated.get("task_rules"))
            calendar["generation"] = _normalize_generation(generated.get("generation"))
            calendar["revision"] += 1
            calendar["updated_at"] = _utc_now()

        self.data["plantings"][planting["id"]] = planting
        self.data["calendars"][calendar["id"]] = calendar
        task = self._generation_task(task_id)
        task["status"] = "succeeded"
        task["error"] = ""
        task["finished_at"] = _utc_now()
        task["updated_at"] = task["finished_at"]
        self._replace_generation_task(task)
        self.save()
        return {"task": copy.deepcopy(task), "planting": copy.deepcopy(planting), "calendar": copy.deepcopy(calendar)}

    @serialized_repository_write("repository_path")
    def fail_calendar_generation(self, task_id: str, error: str):
        task = self._generation_task(task_id)
        if task.get("status") not in ACTIVE_GENERATION_TASK_STATUSES:
            return copy.deepcopy(task)
        task["status"] = "failed"
        task["error"] = _clean_string(error)[:500] or "calendar generation failed"
        task["finished_at"] = _utc_now()
        task["updated_at"] = task["finished_at"]
        self._replace_generation_task(task)
        self.save()
        return copy.deepcopy(task)

    @serialized_repository_write("repository_path")
    def update_action(self, planting_id: str, action_id: str, value: dict, *, use_as_guidance: bool = False):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
        if not isinstance(value, dict):
            raise PlantManagementValidationError("action data must be an object")
        before = copy.deepcopy(action)
        if before["status"] == "completed" and value:
            raise PlantManagementValidationError("completed actions are read-only")

        for key in ("title", "reason", "instructions", "timing_label"):
            if key in value:
                action[key] = _clean_string(value.get(key))[: 1200 if key in {"reason", "instructions"} else 180]
        if not action["title"]:
            raise PlantManagementValidationError("action title is required")
        if "priority" in value:
            priority = _clean_string(value.get("priority"))
            if priority not in VALID_ACTION_PRIORITIES:
                raise PlantManagementValidationError("unsupported action priority")
            action["priority"] = priority
        if "action_type" in value:
            if not is_known_plant_action_type(value.get("action_type")):
                raise PlantManagementValidationError("unsupported action type")
            action["action_type"] = normalize_plant_action_type(value.get("action_type"))
        if "status" in value:
            status = _clean_string(value.get("status"))
            if status not in VALID_ACTION_STATUSES:
                raise PlantManagementValidationError("unsupported action status")
            if status != action["status"] and status not in ACTION_STATUS_TRANSITIONS[action["status"]]:
                raise PlantManagementValidationError(f"action status cannot change from {action['status']} to {status}")
            action["status"] = status
        if "window_start" in value:
            action["window_start"] = _date_string(value.get("window_start"), "window_start")
        if "window_end" in value:
            action["window_end"] = _date_string(value.get("window_end"), "window_end")
        if action["window_end"] < action["window_start"]:
            raise PlantManagementValidationError("window_end must be on or after window_start")
        if "tags" in value:
            action["tags"] = _clean_string_list(value.get("tags"), limit=20, item_length=60)
        if "required_people" in value:
            action["required_people"] = _bounded_int(value.get("required_people"), action["required_people"], 1, 100, "required_people")
        if "estimated_minutes" in value:
            action["estimated_minutes"] = _bounded_int(value.get("estimated_minutes"), action["estimated_minutes"], 1, 1440, "estimated_minutes")
        if "work_plan" in value:
            action["work_plan"] = _normalize_action_work_plan(value.get("work_plan"), action["action_type"])
        elif "pest_control" in value:
            action["work_plan"] = _normalize_action_work_plan(value.get("pest_control"), action["action_type"])
        elif action["action_type"] != before["action_type"]:
            action["work_plan"] = _normalize_action_work_plan(None, action["action_type"])
        action["source"] = "user_edited"

        changed = _dict_diff(before, action)
        if changed:
            feedback = {
                "id": str(uuid.uuid4()),
                "field_id": planting["field_id"],
                "planting_id": planting_id,
                "crop_name": planting["crop_name"],
                "action_id": action_id,
                "changed_at": _utc_now(),
                "changes": changed,
                "before": before,
                "after": copy.deepcopy(action),
                "use_as_guidance": bool(use_as_guidance),
            }
            self.data["feedback"].append(feedback)
            self.data["feedback"] = self.data["feedback"][-MAX_FEEDBACK:]
            calendar["revision"] += 1
            calendar["updated_at"] = _utc_now()
            self.data["calendars"][calendar["id"]] = calendar
            self.save()
        return copy.deepcopy(action)

    @serialized_repository_write("repository_path")
    def add_action(self, planting_id: str, value: dict):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        if len(calendar["actions"]) >= MAX_ACTIONS_PER_CALENDAR:
            raise PlantManagementValidationError("calendar action limit reached")
        action = _normalize_action(value, len(calendar["actions"]))
        action["source"] = "user_created"
        calendar["actions"].append(action)
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.save()
        return copy.deepcopy(action)

    @serialized_repository_write("repository_path")
    def delete_action(self, planting_id: str, action_id: str):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
        if action.get("status") != "planned":
            raise PlantManagementValidationError("only planned actions can be deleted")
        calendar["actions"] = [item for item in calendar["actions"] if item["id"] != action_id]
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.save()

    @serialized_repository_write("repository_path")
    def replace_calendar(
        self,
        planting_id: str,
        actions: list,
        generation: dict | None = None,
        *,
        care_profile: dict | None = None,
        task_rules: list | None = None,
    ):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        if not isinstance(actions, list) or not actions:
            raise PlantManagementValidationError("calendar actions must be a non-empty array")
        if len(actions) > MAX_ACTIONS_PER_CALENDAR:
            raise PlantManagementValidationError(f"calendar actions must contain {MAX_ACTIONS_PER_CALENDAR} entries or less")
        preserved = [copy.deepcopy(action) for action in calendar["actions"] if action.get("status") != "planned"]
        regenerated = [_normalize_action(action, index) for index, action in enumerate(actions)]
        calendar["actions"] = preserved + regenerated
        if care_profile is not None:
            calendar["care_profile"] = _normalize_care_profile(care_profile)
        if task_rules is not None:
            calendar["task_rules"] = _normalize_task_rules(task_rules)
        calendar["generation"] = _normalize_generation(generation)
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.save()
        return copy.deepcopy(calendar)

    @serialized_repository_write("repository_path")
    def append_generated_actions(self, planting_id: str, actions: list):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        if not isinstance(actions, list):
            raise PlantManagementValidationError("calendar actions must be an array")
        normalized = [_normalize_action(action, index) for index, action in enumerate(actions[:3])]
        existing_keys = {
            (action.get("rule_id"), action.get("window_start"), action.get("window_end"), action.get("title"))
            for action in calendar["actions"]
            if action.get("status") in {"planned", "in_progress"}
        }
        appended = []
        for action in normalized:
            key = (action.get("rule_id"), action.get("window_start"), action.get("window_end"), action.get("title"))
            if key in existing_keys:
                continue
            if len(calendar["actions"]) >= MAX_ACTIONS_PER_CALENDAR:
                break
            calendar["actions"].append(action)
            existing_keys.add(key)
            appended.append(action)
        if appended:
            calendar["revision"] += 1
            calendar["updated_at"] = _utc_now()
            self.data["calendars"][calendar["id"]] = calendar
            self.save()
        return copy.deepcopy(appended)

    @serialized_repository_write("repository_path")
    def complete_action(
        self,
        planting_id: str,
        action_id: str,
        performed_on: str,
        note: str = "",
        *,
        rating=None,
        attachments: list | None = None,
        work_details: dict | None = None,
    ):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
        if action.get("status") != "in_progress":
            raise PlantManagementValidationError("action must be in progress before completion can be recorded")
        performed_on = _date_string(performed_on, "performed_on")
        work_log = {
            "id": str(uuid.uuid4()),
            "field_id": planting["field_id"],
            "planting_id": planting_id,
            "calendar_id": calendar["id"],
            "action_id": action_id,
            "action_type": action["action_type"],
            "title": action["title"],
            "crop_name": planting["crop_name"],
            "placement_id": planting["placement_id"],
            "placement_name": planting["placement_name"],
            "performed_on": performed_on,
            "note": _clean_string(note)[:1000],
            "rating": _optional_rating(rating),
            "attachments": _normalize_work_attachments(attachments),
            "work_details": _normalize_work_details(work_details),
            "created_at": _utc_now(),
        }
        action["status"] = "completed"
        action["completion"] = {
            "work_log_id": work_log["id"],
            "performed_on": performed_on,
            "note": work_log["note"],
            "rating": work_log["rating"],
            "attachments": work_log["attachments"],
            "work_details": work_log["work_details"],
        }
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.data["work_logs"].append(work_log)
        self.data["work_logs"] = self.data["work_logs"][-MAX_WORK_LOGS:]
        self.save()
        return copy.deepcopy(work_log)

    @serialized_repository_write("repository_path")
    def record_question(self, planting_id: str, question: str, answer: str):
        planting = self._planting(planting_id)
        question = _required_string(question, "question", 2000)
        record = {
            "id": str(uuid.uuid4()),
            "field_id": planting["field_id"],
            "planting_id": planting_id,
            "question": question,
            "answer": _clean_string(answer)[:10000],
            "created_at": _utc_now(),
        }
        self.data["questions"].append(record)
        self.data["questions"] = self.data["questions"][-MAX_QUESTIONS:]
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("repository_path")
    def create_fertilizer_application(self, planting_id: str, value: dict):
        planting = self._planting(planting_id)
        if not isinstance(value, dict):
            raise PlantManagementValidationError("fertilizer application must be an object")
        applications = self.data.setdefault("fertilizer_applications", [])
        if len(applications) >= MAX_FERTILIZER_APPLICATIONS:
            raise PlantManagementValidationError("fertilizer application limit reached")
        record = _normalize_fertilizer_application(
            {
                **value,
                "id": str(uuid.uuid4()),
                "field_id": planting["field_id"],
                "planting_id": planting_id,
                "space_id": planting["space_id"],
                "placement_id": planting["placement_id"],
                "placement_name": planting["placement_name"],
                "created_at": _utc_now(),
            }
        )
        if _date_value(record["applied_on"], "applied_on") > date.today():
            raise PlantManagementValidationError("applied_on must not be in the future")
        applications.append(record)
        self.data["fertilizer_applications"] = applications[-MAX_FERTILIZER_APPLICATIONS:]
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("repository_path")
    def delete_fertilizer_application(self, planting_id: str, application_id: str):
        planting = self._planting(planting_id)
        application = next(
            (
                item
                for item in self.data.get("fertilizer_applications", [])
                if item.get("id") == application_id and item.get("field_id") == planting["field_id"] and item.get("placement_id") == planting["placement_id"]
            ),
            None,
        )
        if application is None:
            raise PlantManagementNotFoundError("fertilizer application not found")
        self.data["fertilizer_applications"] = [item for item in self.data.get("fertilizer_applications", []) if item.get("id") != application_id]
        self.save()

    def fertilizer_applications_for_planting(self, planting_id: str):
        planting = self._planting(planting_id)
        return copy.deepcopy(
            [
                item
                for item in self.data.get("fertilizer_applications", [])
                if item.get("field_id") == planting["field_id"] and item.get("placement_id") == planting["placement_id"]
            ]
        )

    def fertilizer_effect_context(self, planting_id: str, *, as_of: str | date | None = None):
        applications = self.fertilizer_applications_for_planting(planting_id)
        return {
            "placement_scope": "substrate",
            "applications": applications,
            "effect_summary": fertilizer_effect_summary(applications, as_of=as_of),
        }

    def get_planting(self, planting_id: str):
        record = self.data["plantings"].get(planting_id)
        return copy.deepcopy(record) if record else None

    def get_calendar(self, planting_id: str):
        planting = self._planting(planting_id)
        if not planting.get("calendar_id"):
            return None
        calendar = self.data["calendars"].get(planting["calendar_id"])
        return copy.deepcopy(calendar) if calendar else None

    def search_actions(
        self,
        planting_id: str,
        *,
        query="",
        statuses=None,
        action_types=None,
        date_from="",
        date_to="",
        page=1,
        page_size=50,
    ):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        terms = search_terms(query)
        status_filter = {_clean_string(item) for item in (statuses or []) if _clean_string(item)}
        type_filter = {_clean_string(item) for item in (action_types or []) if _clean_string(item)}
        invalid_statuses = status_filter - VALID_ACTION_STATUSES
        if invalid_statuses:
            raise PlantManagementValidationError(f"unsupported action status: {', '.join(sorted(invalid_statuses))}")
        invalid_types = type_filter - VALID_ACTION_TYPES
        if invalid_types:
            raise PlantManagementValidationError(f"unsupported action type: {', '.join(sorted(invalid_types))}")
        date_from = _clean_string(date_from)[:10]
        date_to = _clean_string(date_to)[:10]

        actions = []
        for action in calendar.get("actions") or []:
            if status_filter and action.get("status") not in status_filter:
                continue
            if type_filter and action.get("action_type") not in type_filter:
                continue
            if date_from and str(action.get("window_end") or "") < date_from:
                continue
            if date_to and str(action.get("window_start") or "") > date_to:
                continue
            if not matches_search(
                terms,
                [
                    action.get("title"),
                    action.get("action_type"),
                    action.get("priority"),
                    action.get("reason"),
                    action.get("instructions"),
                    action.get("timing_label"),
                    action.get("tags"),
                    action.get("work_plan"),
                    action.get("completion"),
                ],
            ):
                continue
            actions.append(copy.deepcopy(action))

        status_order = {"in_progress": 0, "planned": 1, "completed": 2, "skipped": 3}
        actions.sort(
            key=lambda action: (
                status_order.get(action.get("status"), 9),
                action.get("window_start") or "",
                action.get("window_end") or "",
                action.get("id") or "",
            )
        )
        result = paginate(actions, page=page, page_size=page_size)
        result["calendar_id"] = calendar.get("id")
        result["calendar_revision"] = calendar.get("revision")
        return result

    def field_bundle(
        self,
        field_id: str,
        today: str | None = None,
        *,
        statuses=None,
        calendar_planting_ids=None,
        include_work_logs=True,
    ):
        status_filter = set(statuses or [])
        calendar_filter = set(calendar_planting_ids) if calendar_planting_ids is not None else None
        plantings = []
        calendars = {}
        for planting in sorted(self.data["plantings"].values(), key=lambda item: (item["status"] != "active", item["planted_on"], item["id"])):
            if planting["field_id"] != field_id:
                continue
            if status_filter and planting.get("status") not in status_filter:
                continue
            plantings.append(copy.deepcopy(planting))
            calendar = self.data["calendars"].get(planting.get("calendar_id"))
            if calendar and (calendar_filter is None or planting["id"] in calendar_filter):
                calendars[planting["id"]] = copy.deepcopy(calendar)
        placement_filter = {planting.get("placement_id") for planting in self.data["plantings"].values() if planting.get("id") in (calendar_filter or set())}
        latest_generation_tasks = {}
        for task in self.data["generation_tasks"]:
            if task.get("field_id") != field_id:
                continue
            current = latest_generation_tasks.get(task.get("planting_id"))
            if current is None or (task.get("created_at") or "", task.get("id") or "") > (current.get("created_at") or "", current.get("id") or ""):
                latest_generation_tasks[task.get("planting_id")] = task
        return {
            "action_types": plant_action_types(),
            "plantings": plantings,
            "calendars": calendars,
            "generation_tasks": [copy.deepcopy(task) for task in latest_generation_tasks.values()],
            "suggestions": self.list_suggestions(field_id, today=today),
            "work_logs": [
                copy.deepcopy(item)
                for item in self.data["work_logs"]
                if include_work_logs and item["field_id"] == field_id and (calendar_filter is None or item.get("planting_id") in calendar_filter)
            ],
            "fertilizer_applications": [
                copy.deepcopy(item)
                for item in self.data.get("fertilizer_applications", [])
                if item.get("field_id") == field_id and (calendar_filter is None or item.get("placement_id") in placement_filter)
            ],
        }

    def list_suggestions(self, field_id: str, today: str | None = None, lead_days: int = 7):
        current = _date_value(today or date.today().isoformat(), "today")
        suggestions = []
        for planting in self.data["plantings"].values():
            if planting["field_id"] != field_id or planting["status"] != "active":
                continue
            calendar = self.data["calendars"].get(planting.get("calendar_id"))
            if not calendar:
                continue
            for action in calendar["actions"]:
                if action["status"] not in {"planned", "in_progress"}:
                    continue
                start = _date_value(action["window_start"], "window_start")
                end = _date_value(action["window_end"], "window_end")
                if current < start - timedelta(days=lead_days):
                    continue
                timing_state = "overdue" if current > end else "upcoming" if current < start else "due"
                suggestions.append(
                    {
                        "planting_id": planting["id"],
                        "crop_name": planting["crop_name"],
                        "cultivar": planting["cultivar"],
                        "placement_id": planting["placement_id"],
                        "placement_name": planting["placement_name"],
                        "timing_state": timing_state,
                        "action": copy.deepcopy(action),
                    }
                )
        timing_order = {"overdue": 0, "due": 1, "upcoming": 2}
        priority_order = {"required": 0, "should": 1, "recommended": 2, "optional": 3}
        return sorted(
            suggestions,
            key=lambda item: (
                timing_order[item["timing_state"]],
                priority_order[item["action"]["priority"]],
                item["action"]["window_start"],
            ),
        )

    def list_notification_actions(self, today: str | None = None, lead_days: int = 7):
        current = _date_value(today or date.today().isoformat(), "today")
        actions = []
        for planting in self.data["plantings"].values():
            if planting.get("status") != "active":
                continue
            calendar = self.data["calendars"].get(planting.get("calendar_id"))
            if not calendar:
                continue
            for action in calendar["actions"]:
                if action.get("status") not in {"planned", "in_progress"}:
                    continue
                start = _date_value(action["window_start"], "window_start")
                end = _date_value(action["window_end"], "window_end")
                timing_state = None
                if start - timedelta(days=lead_days) <= current < start:
                    timing_state = "upcoming"
                elif start <= current <= end:
                    timing_state = "due"
                actions.append(
                    {
                        "field_id": planting["field_id"],
                        "planting_id": planting["id"],
                        "crop_name": planting["crop_name"],
                        "cultivar": planting["cultivar"],
                        "placement_name": planting["placement_name"],
                        "timing_state": timing_state,
                        "action": copy.deepcopy(action),
                    }
                )
        return sorted(actions, key=lambda item: (item["action"]["window_start"], item["action"]["priority"], item["action"]["title"]))

    def guidance_examples(self, crop_name: str, limit: int = 8):
        normalized_crop = _clean_string(crop_name).casefold()
        candidates = [
            item
            for item in reversed(self.data["feedback"])
            if item.get("use_as_guidance") and _clean_string(item.get("crop_name")).casefold() == normalized_crop
        ]
        return copy.deepcopy(candidates[:limit])

    def recent_work_logs(self, planting_id: str, limit: int = 20):
        self._planting(planting_id)
        return copy.deepcopy([item for item in reversed(self.data["work_logs"]) if item.get("planting_id") == planting_id][:limit])

    def _planting(self, planting_id: str):
        record = self.data["plantings"].get(planting_id)
        if record is None:
            raise PlantManagementNotFoundError("planting not found")
        return copy.deepcopy(record)

    def _calendar_for_planting(self, planting: dict):
        calendar = self.data["calendars"].get(planting.get("calendar_id"))
        if calendar is None:
            raise PlantManagementNotFoundError("plant calendar not found")
        return copy.deepcopy(calendar)

    def _generation_task(self, task_id: str):
        task = next((item for item in self.data["generation_tasks"] if item.get("id") == task_id), None)
        if task is None:
            raise PlantManagementNotFoundError("calendar generation task not found")
        return copy.deepcopy(task)

    def _replace_generation_task(self, replacement: dict):
        self.data["generation_tasks"] = [replacement if task.get("id") == replacement.get("id") else task for task in self.data["generation_tasks"]]


def _empty_data():
    return {
        "schema_version": 1,
        "plantings": {},
        "calendars": {},
        "generation_tasks": [],
        "feedback": [],
        "work_logs": [],
        "questions": [],
        "fertilizer_applications": [],
    }


def _normalize_data(value):
    if not isinstance(value, dict):
        return _empty_data()
    return {
        "schema_version": 1,
        "plantings": {
            planting_id: _normalize_planting_record(planting_id, planting)
            for planting_id, planting in (value.get("plantings") or {}).items()
            if isinstance(planting, dict)
        }
        if isinstance(value.get("plantings"), dict)
        else {},
        "calendars": {
            calendar_id: _normalize_calendar_record(calendar_id, calendar)
            for calendar_id, calendar in (value.get("calendars") or {}).items()
            if isinstance(calendar, dict)
        }
        if isinstance(value.get("calendars"), dict)
        else {},
        "generation_tasks": _trim_generation_tasks(
            [_normalize_generation_task(item) for item in list(value.get("generation_tasks") or []) if isinstance(item, dict)]
        ),
        "feedback": list(value.get("feedback") or [])[-MAX_FEEDBACK:],
        "work_logs": [_normalize_work_log(item) for item in list(value.get("work_logs") or [])[-MAX_WORK_LOGS:] if isinstance(item, dict)],
        "questions": list(value.get("questions") or [])[-MAX_QUESTIONS:],
        "fertilizer_applications": [
            _normalize_fertilizer_application(item)
            for item in list(value.get("fertilizer_applications") or [])[-MAX_FERTILIZER_APPLICATIONS:]
            if isinstance(item, dict)
        ],
    }


def _normalize_fertilizer_application(value: dict):
    material_kind = _clean_string(value.get("material_kind"), "custom")
    if material_kind not in VALID_FERTILIZER_MATERIAL_KINDS:
        material_kind = "custom"
    amount_kg = _optional_float(value.get("amount_kg"), 0.001, 1_000_000, "fertilizer_application.amount_kg")
    if amount_kg is None:
        raise PlantManagementValidationError("fertilizer_application.amount_kg is required")
    nutrient_value = value.get("nutrient_percent") if isinstance(value.get("nutrient_percent"), dict) else {}
    nutrient_percent = {
        key: _optional_float(nutrient_value.get(key), 0, 100, f"fertilizer_application.nutrient_percent.{key}") or 0.0 for key in ("n", "p2o5", "k2o")
    }
    if not any(nutrient_percent.values()):
        raise PlantManagementValidationError("at least one fertilizer nutrient percentage is required")
    annual_available_percent = _optional_float(
        value.get("annual_available_percent"),
        0.1,
        100,
        "fertilizer_application.annual_available_percent",
    )
    if annual_available_percent is None:
        raise PlantManagementValidationError("fertilizer_application.annual_available_percent is required")
    return {
        "id": _clean_string(value.get("id"))[:120] or str(uuid.uuid4()),
        "field_id": _required_string(value.get("field_id"), "fertilizer_application.field_id", 120),
        "planting_id": _clean_string(value.get("planting_id"))[:120],
        "space_id": _required_string(value.get("space_id"), "fertilizer_application.space_id", 120),
        "placement_id": _required_string(value.get("placement_id"), "fertilizer_application.placement_id", 120),
        "placement_name": _required_string(value.get("placement_name"), "fertilizer_application.placement_name", 120),
        "applied_on": _date_string(value.get("applied_on"), "fertilizer_application.applied_on"),
        "material_kind": material_kind,
        "material_name": _required_string(value.get("material_name"), "fertilizer_application.material_name", 180),
        "amount_kg": amount_kg,
        "nutrient_percent": nutrient_percent,
        "annual_available_percent": annual_available_percent,
        "effect_years": _bounded_int(value.get("effect_years"), 1, 1, 10, "fertilizer_application.effect_years"),
        "start_delay_days": _bounded_int(value.get("start_delay_days"), 0, 0, 3650, "fertilizer_application.start_delay_days"),
        "analysis_source": _clean_string(value.get("analysis_source"))[:500],
        "notes": _clean_string(value.get("notes"))[:1000],
        "created_at": _clean_string(value.get("created_at"), _utc_now())[:80],
    }


def _normalize_planting_record(planting_id: str, value: dict):
    record = copy.deepcopy(value)
    record["id"] = _clean_string(record.get("id"), planting_id)
    record["crop_category"] = _crop_category(record.get("crop_category"), record.get("crop_name"))
    record["tree_age_years"] = _tree_age(record.get("tree_age_years"), record["crop_category"])
    record["growth_targets"] = _normalize_growth_targets(record.get("growth_targets"))
    return record


def _normalize_generation_task(value: dict):
    record = copy.deepcopy(value)
    status = _clean_string(record.get("status"), "failed")
    kind = _clean_string(record.get("kind"), "initial")
    return {
        "id": _clean_string(record.get("id"))[:120] or str(uuid.uuid4()),
        "field_id": _clean_string(record.get("field_id"))[:120],
        "planting_id": _clean_string(record.get("planting_id"))[:120],
        "kind": kind if kind in VALID_GENERATION_TASK_KINDS else "initial",
        "status": status if status in VALID_GENERATION_TASK_STATUSES else "failed",
        "start_date": _clean_string(record.get("start_date"))[:10],
        "planning_notes": _clean_string(record.get("planning_notes"))[:2000],
        "audience": copy.deepcopy(record.get("audience")) if isinstance(record.get("audience"), dict) else {},
        "attempts": max(0, _bounded_int(record.get("attempts"), 0, 0, 1000, "generation_task.attempts")),
        "error": _clean_string(record.get("error"))[:500],
        "created_at": _clean_string(record.get("created_at"))[:40],
        "started_at": _clean_string(record.get("started_at"))[:40],
        "finished_at": _clean_string(record.get("finished_at"))[:40],
        "updated_at": _clean_string(record.get("updated_at"))[:40],
    }


def _trim_generation_tasks(tasks: list):
    active_ids = {task.get("id") for task in tasks if task.get("status") in ACTIVE_GENERATION_TASK_STATUSES}
    inactive_slots = max(0, MAX_GENERATION_TASKS - len(active_ids))
    inactive_tasks = [task for task in tasks if task.get("status") not in ACTIVE_GENERATION_TASK_STATUSES]
    inactive_ids = {task.get("id") for task in inactive_tasks[-inactive_slots:]} if inactive_slots else set()
    keep_ids = active_ids | inactive_ids
    return [task for task in tasks if task.get("id") in keep_ids]


def _normalize_calendar_record(calendar_id: str, value: dict):
    record = copy.deepcopy(value)
    record["id"] = _clean_string(record.get("id"), calendar_id)
    record["care_profile"] = _normalize_care_profile(record.get("care_profile"))
    record["task_rules"] = _normalize_task_rules(record.get("task_rules"))
    actions = record.get("actions") if isinstance(record.get("actions"), list) else []
    record["actions"] = [_normalize_action(action, index) for index, action in enumerate(actions)]
    record["generation"] = _normalize_generation(record.get("generation"))
    return record


def _crop_category(value, crop_name=""):
    category = _clean_string(value)
    if category in VALID_CROP_CATEGORIES:
        return category
    normalized_name = _clean_string(crop_name)
    if any(keyword in normalized_name for keyword in ("ブルーベリー", "果樹", "柑橘", "リンゴ", "梨", "桃", "ブドウ")):
        return "fruit_tree"
    return "vegetable"


def _tree_age(value, crop_category):
    if crop_category != "fruit_tree":
        return None
    if value in (None, ""):
        return None
    return _bounded_int(value, 1, 0, 300, "tree_age_years")


def _normalize_growth_targets(value):
    value = value if isinstance(value, dict) else {}
    targets = {}
    for metric, (domain_min, domain_max) in PLANTING_TARGET_RANGES.items():
        metric_value = value.get(metric) if isinstance(value.get(metric), dict) else {}
        minimum = _optional_float(metric_value.get("min"), domain_min, domain_max, f"growth_targets.{metric}.min")
        maximum = _optional_float(metric_value.get("max"), domain_min, domain_max, f"growth_targets.{metric}.max")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise PlantManagementValidationError(f"growth_targets.{metric}.min must be less than or equal to max")
        targets[metric] = {"min": minimum, "max": maximum}
    return targets


def _optional_float(value, minimum: float, maximum: float, path: str):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PlantManagementValidationError(f"{path} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PlantManagementValidationError(f"{path} must be a number") from exc
    if number < minimum or number > maximum:
        raise PlantManagementValidationError(f"{path} must be between {minimum} and {maximum}")
    return number


def _normalize_action(value, index: int):
    if not isinstance(value, dict):
        raise PlantManagementValidationError(f"actions[{index}] must be an object")
    action_type = normalize_plant_action_type(value.get("action_type"))
    priority = _clean_string(value.get("priority"), "recommended")
    if priority not in VALID_ACTION_PRIORITIES:
        priority = "recommended"
    status = _clean_string(value.get("status"), "planned")
    if status not in VALID_ACTION_STATUSES:
        status = "planned"
    window_start = _date_string(value.get("window_start"), f"actions[{index}].window_start")
    window_end = _date_string(value.get("window_end") or window_start, f"actions[{index}].window_end")
    if window_end < window_start:
        raise PlantManagementValidationError(f"actions[{index}].window_end must be on or after window_start")
    legacy_plan = value.get("pest_control") if action_type == "pest_control" else None
    return {
        "id": _clean_string(value.get("id"))[:120] or str(uuid.uuid4()),
        "action_type": action_type,
        "title": _required_string(value.get("title"), f"actions[{index}].title", 180),
        "priority": priority,
        "window_start": window_start,
        "window_end": window_end,
        "timing_label": _clean_string(value.get("timing_label"))[:180],
        "reason": _clean_string(value.get("reason"))[:1200],
        "instructions": _clean_string(value.get("instructions"))[:1200],
        "tags": _clean_string_list(value.get("tags"), limit=20, item_length=60),
        "required_people": _bounded_int(value.get("required_people"), 1, 1, 100, f"actions[{index}].required_people"),
        "estimated_minutes": _bounded_int(value.get("estimated_minutes"), 30, 1, 1440, f"actions[{index}].estimated_minutes"),
        "work_plan": _normalize_action_work_plan(value.get("work_plan") or legacy_plan, action_type),
        "status": status,
        "completion": _normalize_action_completion(value.get("completion")),
        "source": _clean_string(value.get("source"), "llm")[:40],
        "rule_id": _clean_string(value.get("rule_id"))[:120],
    }


def _normalize_care_profile(value):
    value = value if isinstance(value, dict) else {}
    irrigation = value.get("irrigation") if isinstance(value.get("irrigation"), dict) else {}
    fertilization = value.get("fertilization") if isinstance(value.get("fertilization"), dict) else {}
    return {
        "summary": _clean_string(value.get("summary"))[:2000],
        "assumptions": _clean_string_list(value.get("assumptions"), limit=20, item_length=300),
        "knowledge_sources": _clean_string_list(value.get("knowledge_sources"), limit=20, item_length=500),
        "irrigation": {
            "strategy": _clean_string(irrigation.get("strategy"))[:1200],
            "baseline_interval_days": _normalize_interval_days(irrigation.get("baseline_interval_days")),
            "decision_factors": _clean_string_list(irrigation.get("decision_factors"), limit=20, item_length=300),
            "skip_conditions": _clean_string_list(irrigation.get("skip_conditions"), limit=20, item_length=300),
        },
        "fertilization": {
            "strategy": _clean_string(fertilization.get("strategy"))[:1200],
            "ec_management": _clean_string(fertilization.get("ec_management"))[:1200],
            "ph_management": _clean_string(fertilization.get("ph_management"))[:1200],
            "decision_factors": _clean_string_list(fertilization.get("decision_factors"), limit=20, item_length=300),
            "skip_conditions": _clean_string_list(fertilization.get("skip_conditions"), limit=20, item_length=300),
        },
        "stage_notes": _normalize_stage_notes(value.get("stage_notes")),
    }


def _normalize_task_rules(value):
    if not isinstance(value, list):
        return []
    rules = []
    for index, item in enumerate(value[:40]):
        if not isinstance(item, dict):
            continue
        action_type = normalize_plant_action_type(item.get("action_type"))
        recurrence_type = _clean_string(item.get("recurrence_type"), "one_time")
        if recurrence_type not in VALID_RECURRENCE_TYPES:
            recurrence_type = "one_time"
        anchor = _clean_string(item.get("anchor"), "calendar_date")
        if anchor not in VALID_RECURRENCE_ANCHORS:
            anchor = "calendar_date"
        active_months = []
        if isinstance(item.get("active_months"), list):
            for month in item["active_months"]:
                try:
                    month_number = int(month)
                except (TypeError, ValueError):
                    continue
                if 1 <= month_number <= 12 and month_number not in active_months:
                    active_months.append(month_number)
        rules.append(
            {
                "rule_id": _clean_string(item.get("rule_id"))[:120] or f"rule-{index + 1}",
                "action_type": action_type,
                "title": _required_string(item.get("title"), f"task_rules[{index}].title", 180),
                "recurrence_type": recurrence_type,
                "anchor": anchor,
                "interval_days": _normalize_interval_days(item.get("interval_days")),
                "active_months": active_months,
                "conditions": _clean_string_list(item.get("conditions"), limit=20, item_length=300),
                "skip_conditions": _clean_string_list(item.get("skip_conditions"), limit=20, item_length=300),
                "notes": _clean_string(item.get("notes"))[:1200],
            }
        )
    return rules


def _normalize_interval_days(value):
    value = value if isinstance(value, dict) else {}
    minimum = _optional_int(value.get("min"), 1, 3660)
    preferred = _optional_int(value.get("preferred"), 1, 3660)
    maximum = _optional_int(value.get("max"), 1, 3660)
    numbers = [number for number in (minimum, preferred, maximum) if number is not None]
    if numbers and numbers != sorted(numbers):
        minimum, preferred, maximum = min(numbers), sorted(numbers)[len(numbers) // 2], max(numbers)
    return {"min": minimum, "preferred": preferred, "max": maximum}


def _normalize_stage_notes(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "stage": _clean_string(item.get("stage"))[:120],
                "indicators": _clean_string_list(item.get("indicators"), limit=20, item_length=300),
                "management": _clean_string(item.get("management"))[:1200],
            }
        )
    return result


def _normalize_generation(value):
    value = value if isinstance(value, dict) else {}
    return {
        "source": _clean_string(value.get("source"), "unknown")[:40],
        "model": _clean_string(value.get("model"))[:120],
        "generated_at": _clean_string(value.get("generated_at"), _utc_now())[:80],
        "context_snapshot": value.get("context_snapshot") if isinstance(value.get("context_snapshot"), dict) else {},
        "guidance_count": _bounded_int(value.get("guidance_count"), 0, 0, 100, "guidance_count"),
    }


def _normalize_conditions(value):
    value = value if isinstance(value, dict) else {}
    return {
        "environment": _clean_string(value.get("environment"))[:120],
        "soil_or_substrate": _clean_string(value.get("soil_or_substrate"))[:180],
        "region": _clean_string(value.get("region"))[:120],
        "sunlight": _clean_string(value.get("sunlight"))[:120],
        "notes": _clean_string(value.get("notes"))[:1000],
    }


def _find_action(calendar: dict, action_id: str):
    action = next((item for item in calendar["actions"] if item["id"] == action_id), None)
    if action is None:
        raise PlantManagementNotFoundError("calendar action not found")
    return action


def _dict_diff(before: dict, after: dict):
    return {key: {"before": before.get(key), "after": after.get(key)} for key in after if before.get(key) != after.get(key)}


def _utc_now():
    return datetime.now(UTC).isoformat()


def _clean_string(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _required_string(value, path: str, max_length: int):
    text = _clean_string(value)
    if not text:
        raise PlantManagementValidationError(f"{path} is required")
    if len(text) > max_length:
        raise PlantManagementValidationError(f"{path} must be {max_length} characters or less")
    return text


def _clean_string_list(value, *, limit: int, item_length: int):
    if isinstance(value, str):
        value = value.replace("、", ",").split(",")
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _clean_string(item)[:item_length]
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _optional_rating(value):
    if value in (None, ""):
        return None
    return _bounded_int(value, 3, 1, 5, "rating")


def _normalize_work_attachments(value):
    if not isinstance(value, list):
        return []
    attachments = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        attachment_id = _clean_string(item.get("id"))
        object_key = _clean_string(item.get("object_key"))
        content_type = _clean_string(item.get("content_type"))
        if not attachment_id or not object_key.startswith("field-records/") or content_type not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        attachments.append(
            {
                "id": attachment_id,
                "storage": "r2",
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": _bounded_int(item.get("size_bytes"), 0, 0, 10 * 1024 * 1024, "attachments.size_bytes"),
                "original_filename": _clean_string(item.get("original_filename"))[:180],
                "url": _clean_string(item.get("url"))[:500],
            }
        )
    return attachments


def _normalize_action_work_plan(value, action_type):
    defaults = default_action_work_plan(action_type)
    value = value if isinstance(value, dict) else {}
    targets = _clean_string_list(value.get("targets"), limit=20, item_length=180)
    start_conditions = _clean_string_list(value.get("start_conditions"), limit=20, item_length=300)
    skip_conditions = _clean_string_list(value.get("skip_conditions"), limit=20, item_length=300)
    checkpoints = _clean_string_list(value.get("checkpoints") or value.get("observation_points"), limit=20, item_length=300)
    methods = _normalize_work_method_options(value.get("method_options"))
    completion_criteria = _clean_string_list(value.get("completion_criteria"), limit=20, item_length=300)
    return {
        "targets": targets or defaults["targets"],
        "start_conditions": start_conditions or defaults["start_conditions"],
        "skip_conditions": skip_conditions or defaults["skip_conditions"],
        "checkpoints": checkpoints or defaults["checkpoints"],
        "method_options": methods or defaults["method_options"],
        "completion_criteria": completion_criteria or defaults["completion_criteria"],
    }


def _normalize_work_method_options(value):
    if not isinstance(value, list):
        return []
    options = []
    for index, item in enumerate(value[:30]):
        if not isinstance(item, dict):
            continue
        method_type = _clean_string(item.get("method_type"), "other")
        if method_type not in VALID_WORK_METHOD_TYPES:
            method_type = "other"
        label = _clean_string(item.get("label"))[:180]
        if not label:
            continue
        instructions = _clean_string(item.get("instructions"))[:1000]
        application_method = _clean_string(item.get("application_method"))[:1000] or instructions or label
        procedure_steps = _clean_string_list(item.get("procedure_steps"), limit=12, item_length=500)
        options.append(
            {
                "id": _clean_string(item.get("id"))[:120] or f"method-{index + 1}",
                "label": label,
                "method_type": method_type,
                "material_name": _clean_string(item.get("material_name") or item.get("product_name"))[:180],
                "registration_number": _clean_string(item.get("registration_number"))[:80],
                "purpose": _clean_string(item.get("purpose"))[:500] or label,
                "application_method": application_method,
                "amount_or_rate": _clean_string(item.get("amount_or_rate"))[:300],
                "procedure_steps": procedure_steps or [application_method],
                "completion_checks": _clean_string_list(item.get("completion_checks"), limit=12, item_length=300),
                "precautions": _clean_string_list(item.get("precautions"), limit=12, item_length=500),
                "frequency": _normalize_work_frequency(item.get("frequency")),
                "instructions": instructions,
                "follow_up_days_default": _optional_int(item.get("follow_up_days_default") or item.get("effective_days_default"), 1, 365),
                "source_name": _clean_string(item.get("source_name"))[:180],
                "source_url": _safe_http_url(item.get("source_url")),
                "source_checked_at": _clean_string(item.get("source_checked_at"))[:40],
            }
        )
    return options


def _normalize_work_frequency(value):
    value = value if isinstance(value, dict) else {}
    mode = _clean_string(value.get("mode"), "as_needed")
    if mode not in VALID_WORK_FREQUENCY_MODES:
        mode = "as_needed"
    interval = _normalize_interval_days(
        {
            "min": value.get("min_interval_days"),
            "preferred": value.get("preferred_interval_days"),
            "max": value.get("max_interval_days"),
        }
    )
    return {
        "mode": mode,
        "min_interval_days": interval["min"],
        "preferred_interval_days": interval["preferred"],
        "max_interval_days": interval["max"],
        "max_applications": _optional_int(value.get("max_applications"), 1, 1000),
        "basis": _clean_string(value.get("basis"))[:500],
    }


def _normalize_work_details(value):
    value = value if isinstance(value, dict) else {}
    execution = value.get("execution")
    if not isinstance(execution, dict):
        execution = value.get("pest_control")
    if not isinstance(execution, dict):
        return {}
    method_type = _clean_string(execution.get("method_type"), "other")
    if method_type not in VALID_WORK_METHOD_TYPES:
        method_type = "other"
    return {
        "execution": {
            "target": _clean_string(execution.get("target"))[:180],
            "method_id": _clean_string(execution.get("method_id"))[:120],
            "method_label": _clean_string(execution.get("method_label"))[:180],
            "method_type": method_type,
            "material_name": _clean_string(execution.get("material_name") or execution.get("product_name"))[:180],
            "amount_or_rate": _clean_string(execution.get("amount_or_rate"))[:300],
            "registration_number": _clean_string(execution.get("registration_number"))[:80],
            "custom_method": _clean_string(execution.get("custom_method"))[:500],
            "follow_up_days": _optional_int(execution.get("follow_up_days") or execution.get("effective_days"), 1, 365),
            "source_name": _clean_string(execution.get("source_name"))[:180],
            "source_url": _safe_http_url(execution.get("source_url")),
            "source_checked_at": _clean_string(execution.get("source_checked_at"))[:40],
        }
    }


def _normalize_action_completion(value):
    if not isinstance(value, dict):
        return None
    performed_on = _clean_string(value.get("performed_on"))
    try:
        performed_on = date.fromisoformat(performed_on).isoformat()
    except ValueError:
        return None
    return {
        "work_log_id": _clean_string(value.get("work_log_id"))[:120],
        "performed_on": performed_on,
        "note": _clean_string(value.get("note"))[:1000],
        "rating": _optional_rating(value.get("rating")),
        "attachments": _normalize_work_attachments(value.get("attachments")),
        "work_details": _normalize_work_details(value.get("work_details")),
    }


def _normalize_work_log(value):
    record = copy.deepcopy(value)
    record["work_details"] = _normalize_work_details(record.get("work_details"))
    record["attachments"] = _normalize_work_attachments(record.get("attachments"))
    record["rating"] = _optional_rating(record.get("rating"))
    return record


def _safe_http_url(value):
    url = _clean_string(value)[:500]
    return url if url.startswith(("https://", "http://")) else ""


def _bounded_int(value, default: int, minimum: int, maximum: int, path: str):
    try:
        number = int(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise PlantManagementValidationError(f"{path} must be an integer") from exc
    if number < minimum or number > maximum:
        raise PlantManagementValidationError(f"{path} must be between {minimum} and {maximum}")
    return number


def _optional_int(value, minimum: int, maximum: int):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


def _date_value(value, path: str):
    try:
        return date.fromisoformat(_clean_string(value))
    except ValueError as exc:
        raise PlantManagementValidationError(f"{path} must be YYYY-MM-DD") from exc


def _date_string(value, path: str):
    return _date_value(value, path).isoformat()


__instance = None


def plant_management_repository():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = PlantManagementRepository()
    return __instance
