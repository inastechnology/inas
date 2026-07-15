import copy
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta

from ina_device_hub.plant_action_catalog import (
    is_known_plant_action_type,
    normalize_plant_action_type,
    plant_action_type_codes,
    plant_action_types,
)
from ina_device_hub.setting import setting

MAX_PLANTINGS = 2000
MAX_ACTIONS_PER_CALENDAR = 100
MAX_FEEDBACK = 3000
MAX_WORK_LOGS = 5000
MAX_QUESTIONS = 1000

VALID_PLANTING_STATUSES = {"active", "harvested", "removed"}
VALID_CROP_CATEGORIES = {"vegetable", "fruit_tree", "flower", "herb", "other"}
VALID_ACTION_STATUSES = {"planned", "completed", "skipped"}
VALID_ACTION_PRIORITIES = {"required", "should", "recommended", "optional"}
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


class PlantManagementRepository:
    repository_path = os.path.join(setting().get_work_dir(), ".plant_management.json")

    def __init__(self):
        self.data = _empty_data()
        self.load()

    def load(self):
        if not os.path.exists(self.repository_path):
            with open(self.repository_path, "w", encoding="utf-8") as file:
                json.dump(_empty_data(), file)
        try:
            with open(self.repository_path, encoding="utf-8") as file:
                loaded = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            loaded = {}
        self.data = _normalize_data(loaded)

    def save(self):
        with open(self.repository_path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=True, indent=2)

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

    def update_action(self, planting_id: str, action_id: str, value: dict, *, use_as_guidance: bool = False):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
        if not isinstance(value, dict):
            raise PlantManagementValidationError("action data must be an object")
        before = copy.deepcopy(action)

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
            action["status"] = status
        if "window_start" in value:
            action["window_start"] = _date_string(value.get("window_start"), "window_start")
        if "window_end" in value:
            action["window_end"] = _date_string(value.get("window_end"), "window_end")
        if action["window_end"] < action["window_start"]:
            raise PlantManagementValidationError("window_end must be on or after window_start")
        if "tags" in value:
            action["tags"] = _clean_string_list(value.get("tags"), limit=20, item_length=60)
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

    def delete_action(self, planting_id: str, action_id: str):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
        if action.get("status") == "completed":
            raise PlantManagementValidationError("completed actions cannot be deleted")
        calendar["actions"] = [item for item in calendar["actions"] if item["id"] != action_id]
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.save()

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
        completed = [copy.deepcopy(action) for action in calendar["actions"] if action.get("status") == "completed"]
        regenerated = [_normalize_action(action, index) for index, action in enumerate(actions)]
        calendar["actions"] = completed + regenerated
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

    def append_generated_actions(self, planting_id: str, actions: list):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        if not isinstance(actions, list):
            raise PlantManagementValidationError("calendar actions must be an array")
        normalized = [_normalize_action(action, index) for index, action in enumerate(actions[:3])]
        existing_keys = {
            (action.get("rule_id"), action.get("window_start"), action.get("window_end"), action.get("title"))
            for action in calendar["actions"]
            if action.get("status") == "planned"
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

    def complete_action(
        self,
        planting_id: str,
        action_id: str,
        performed_on: str,
        note: str = "",
        *,
        rating=None,
        attachments: list | None = None,
    ):
        planting = self._planting(planting_id)
        calendar = self._calendar_for_planting(planting)
        action = _find_action(calendar, action_id)
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
            "created_at": _utc_now(),
        }
        action["status"] = "completed"
        action["completion"] = {
            "work_log_id": work_log["id"],
            "performed_on": performed_on,
            "note": work_log["note"],
            "rating": work_log["rating"],
            "attachments": work_log["attachments"],
        }
        calendar["revision"] += 1
        calendar["updated_at"] = _utc_now()
        self.data["calendars"][calendar["id"]] = calendar
        self.data["work_logs"].append(work_log)
        self.data["work_logs"] = self.data["work_logs"][-MAX_WORK_LOGS:]
        self.save()
        return copy.deepcopy(work_log)

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

    def get_planting(self, planting_id: str):
        record = self.data["plantings"].get(planting_id)
        return copy.deepcopy(record) if record else None

    def get_calendar(self, planting_id: str):
        planting = self._planting(planting_id)
        if not planting.get("calendar_id"):
            return None
        calendar = self.data["calendars"].get(planting["calendar_id"])
        return copy.deepcopy(calendar) if calendar else None

    def field_bundle(self, field_id: str, today: str | None = None):
        plantings = []
        calendars = {}
        for planting in sorted(self.data["plantings"].values(), key=lambda item: (item["status"] != "active", item["planted_on"], item["id"])):
            if planting["field_id"] != field_id:
                continue
            plantings.append(copy.deepcopy(planting))
            calendar = self.data["calendars"].get(planting.get("calendar_id"))
            if calendar:
                calendars[planting["id"]] = copy.deepcopy(calendar)
        return {
            "action_types": plant_action_types(),
            "plantings": plantings,
            "calendars": calendars,
            "suggestions": self.list_suggestions(field_id, today=today),
            "work_logs": [copy.deepcopy(item) for item in self.data["work_logs"] if item["field_id"] == field_id],
        }

    def list_suggestions(self, field_id: str, today: str | None = None, lead_days: int = 14):
        current = _date_value(today or date.today().isoformat(), "today")
        suggestions = []
        for planting in self.data["plantings"].values():
            if planting["field_id"] != field_id or planting["status"] != "active":
                continue
            calendar = self.data["calendars"].get(planting.get("calendar_id"))
            if not calendar:
                continue
            for action in calendar["actions"]:
                if action["status"] != "planned":
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


def _empty_data():
    return {"schema_version": 1, "plantings": {}, "calendars": {}, "feedback": [], "work_logs": [], "questions": []}


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
        "feedback": list(value.get("feedback") or [])[-MAX_FEEDBACK:],
        "work_logs": list(value.get("work_logs") or [])[-MAX_WORK_LOGS:],
        "questions": list(value.get("questions") or [])[-MAX_QUESTIONS:],
    }


def _normalize_planting_record(planting_id: str, value: dict):
    record = copy.deepcopy(value)
    record["id"] = _clean_string(record.get("id"), planting_id)
    record["crop_category"] = _crop_category(record.get("crop_category"), record.get("crop_name"))
    record["tree_age_years"] = _tree_age(record.get("tree_age_years"), record["crop_category"])
    record["growth_targets"] = _normalize_growth_targets(record.get("growth_targets"))
    return record


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
        "status": status,
        "completion": value.get("completion") if isinstance(value.get("completion"), dict) else None,
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
