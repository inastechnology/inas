import copy
import json
import os
import uuid
from datetime import UTC, datetime

from ina_device_hub.setting import setting

MAX_FIELD_NOTES = 1000
MAX_FIELD_REFLECTIONS = 300
MAX_FIELD_EVENTS = 1000
MAX_FIELD_ACTION_PLANS = 500
VALID_FIELD_AREA_TYPES = {"section", "bed", "ridge", "zone", "point", "other"}
VALID_DEVICE_SCOPE_TYPES = {"field", "section", "bed", "ridge", "zone", "point", "other"}
VALID_DEVICE_ROLES = {"environment", "soil", "watering", "camera", "actuator", "sensor", "other"}


def _utc_now():
    return datetime.now(UTC).isoformat()


def _clean_string(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _clean_string_list(values):
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = _clean_string(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _clean_float(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_int(value, default=0):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean_range(value, default_min=None, default_max=None):
    value = value if isinstance(value, dict) else {}
    return {
        "min": _clean_float(value.get("min"), default_min),
        "max": _clean_float(value.get("max"), default_max),
    }


def _clean_dict(value):
    return value if isinstance(value, dict) else {}


class FieldValidationError(ValueError):
    pass


class FieldRepository:
    field_repo_path = os.path.join(setting().get_work_dir(), ".fields.json")

    def __init__(self):
        self.fields = {}
        self.load()

    def load(self):
        if not os.path.exists(self.field_repo_path):
            with open(self.field_repo_path, "w", encoding="utf-8") as file:
                json.dump({}, file)
        try:
            with open(self.field_repo_path, encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        self.fields = {field_id: _normalize_field(field_id, record) for field_id, record in data.items() if isinstance(record, dict)}

    def save(self):
        with open(self.field_repo_path, "w", encoding="utf-8") as file:
            json.dump(self.fields, file, ensure_ascii=True, indent=2)

    def list(self):
        return [copy.deepcopy(field) for field in sorted(self.fields.values(), key=lambda item: item.get("name") or item.get("id"))]

    def get(self, field_id: str):
        record = self.fields.get(field_id)
        return copy.deepcopy(_normalize_field(field_id, record)) if record else None

    def upsert(self, field_id: str | None, data: dict):
        if not isinstance(data, dict):
            raise FieldValidationError("field data must be an object")
        now = _utc_now()
        field_id = _clean_string(field_id) or str(uuid.uuid4())
        existing = self.fields.get(field_id) or _new_field(field_id, now)
        record = _normalize_field(field_id, existing)
        name = _clean_string(data.get("name"), record.get("name"))
        if not name:
            raise FieldValidationError("name is required")
        record["name"] = name
        record["crop_profile"] = _normalize_crop_profile(
            {
                **_clean_dict(record.get("crop_profile")),
                **_clean_dict(data.get("crop_profile")),
                "crop_name": data.get("crop", _clean_dict(data.get("crop_profile")).get("crop_name")),
                "growth_stage": data.get("stage", _clean_dict(data.get("crop_profile")).get("growth_stage")),
            },
            record,
        )
        record["crop"] = record["crop_profile"]["crop_name"]
        record["stage"] = record["crop_profile"]["growth_stage"]
        record["growth_targets"] = _normalize_growth_targets(
            {**_clean_dict(record.get("growth_targets")), **_clean_dict(data.get("growth_targets"))}
        )
        record["cultivation_context"] = _normalize_cultivation_context(
            {**_clean_dict(record.get("cultivation_context")), **_clean_dict(data.get("cultivation_context"))}
        )
        record["control_policy"] = _normalize_control_policy(
            {**_clean_dict(record.get("control_policy")), **_clean_dict(data.get("control_policy"))}
        )
        record["knowledge_context"] = _normalize_knowledge_context(
            {**_clean_dict(record.get("knowledge_context")), **_clean_dict(data.get("knowledge_context"))}
        )
        record["memo"] = _clean_string(data.get("memo"), record.get("memo"))
        if "device_ids" in data:
            record["device_ids"] = _clean_string_list(data.get("device_ids"))
        if "camera_device_ids" in data:
            record["camera_device_ids"] = _clean_string_list(data.get("camera_device_ids"))
        if "areas" in data:
            record["areas"] = _normalize_field_areas(data.get("areas"))
        else:
            record["areas"] = _normalize_field_areas(record.get("areas"))
        if "device_placements" in data:
            record["device_placements"] = _normalize_device_placements(
                data.get("device_placements"),
                record["device_ids"],
                record["camera_device_ids"],
                record["areas"],
            )
        else:
            record["device_placements"] = _normalize_device_placements(
                record.get("device_placements"),
                record["device_ids"],
                record["camera_device_ids"],
                record["areas"],
            )
        record["updated_at"] = now
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(record)

    def add_note(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        text = _clean_string(data.get("text"))
        if not text:
            raise FieldValidationError("note text is required")
        note = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "author": _clean_string(data.get("author"), "human"),
            "category": _clean_string(data.get("category"), "observation"),
            "text": text,
            "tags": _clean_string_list(data.get("tags")),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
        }
        notes = list(record.get("notes") or [])
        notes.append(note)
        record["notes"] = notes[-MAX_FIELD_NOTES:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(note)

    def add_event(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        event_type = _clean_string(data.get("event_type"), "observation")
        occurred_at = _clean_string(data.get("occurred_at")) or _utc_now()
        event = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "occurred_at": occurred_at,
            "event_type": event_type,
            "title": _clean_string(data.get("title"), event_type),
            "description": _clean_string(data.get("description")),
            "amount": _clean_string(data.get("amount")),
            "unit": _clean_string(data.get("unit")),
            "device_id": _clean_string(data.get("device_id")),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
            "tags": _clean_string_list(data.get("tags")),
        }
        events = list(record.get("events") or [])
        events.append(event)
        record["events"] = events[-MAX_FIELD_EVENTS:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(event)

    def add_reflection(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        reflection = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "period_start": _clean_string(data.get("period_start")),
            "period_end": _clean_string(data.get("period_end")),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
            "llm_reflection": _clean_string(data.get("llm_reflection")),
            "context_snapshot": data.get("context_snapshot") if isinstance(data.get("context_snapshot"), dict) else {},
        }
        if not reflection["human_evaluation"] and not reflection["llm_reflection"]:
            raise FieldValidationError("human_evaluation or llm_reflection is required")
        reflections = list(record.get("reflections") or [])
        reflections.append(reflection)
        record["reflections"] = reflections[-MAX_FIELD_REFLECTIONS:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(reflection)

    def add_action_plan(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        action_type = _clean_string(data.get("action_type"), "observation")
        if action_type not in {"watering", "fertigation", "misting", "environment", "observation"}:
            raise FieldValidationError("unsupported action_type")
        status = _clean_string(data.get("status"), "proposed")
        if status not in {"proposed", "approved", "applied", "rejected", "evaluated"}:
            raise FieldValidationError("unsupported action status")
        plan = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "status": status,
            "action_type": action_type,
            "target_device_id": _clean_string(data.get("target_device_id")),
            "title": _clean_string(data.get("title"), action_type),
            "scientific_reason": _clean_string(data.get("scientific_reason")),
            "preconditions": _clean_dict(data.get("preconditions")),
            "expected_effect": _clean_string(data.get("expected_effect")),
            "risk": _clean_string(data.get("risk")),
            "control_payload": _clean_dict(data.get("control_payload")),
            "source": _clean_string(data.get("source"), "human"),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
            "tags": _clean_string_list(data.get("tags")),
        }
        plans = list(record.get("action_plans") or [])
        plans.append(plan)
        record["action_plans"] = plans[-MAX_FIELD_ACTION_PLANS:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(plan)

    def _get_existing(self, field_id: str):
        record = self.fields.get(field_id)
        if record is None:
            raise FieldValidationError("field not found")
        return _normalize_field(field_id, record)


def _new_field(field_id: str, now: str):
    return {
        "id": field_id,
        "name": "",
        "crop": "",
        "stage": "",
        "crop_profile": _normalize_crop_profile({}),
        "growth_targets": _normalize_growth_targets({}),
        "cultivation_context": _normalize_cultivation_context({}),
        "control_policy": _normalize_control_policy({}),
        "knowledge_context": _normalize_knowledge_context({}),
        "memo": "",
        "areas": [],
        "device_placements": [],
        "device_ids": [],
        "camera_device_ids": [],
        "notes": [],
        "events": [],
        "action_plans": [],
        "reflections": [],
        "created_at": now,
        "updated_at": now,
    }


def _normalize_field(field_id: str, record: dict):
    now = _utc_now()
    normalized = _new_field(field_id, record.get("created_at") or now)
    normalized.update(record)
    normalized["id"] = field_id
    normalized["crop_profile"] = _normalize_crop_profile(normalized.get("crop_profile"), normalized)
    normalized["crop"] = normalized["crop_profile"]["crop_name"]
    normalized["stage"] = normalized["crop_profile"]["growth_stage"]
    normalized["growth_targets"] = _normalize_growth_targets(normalized.get("growth_targets"))
    normalized["cultivation_context"] = _normalize_cultivation_context(normalized.get("cultivation_context"))
    normalized["control_policy"] = _normalize_control_policy(normalized.get("control_policy"))
    normalized["knowledge_context"] = _normalize_knowledge_context(normalized.get("knowledge_context"))
    normalized["device_ids"] = _clean_string_list(normalized.get("device_ids"))
    normalized["camera_device_ids"] = _clean_string_list(normalized.get("camera_device_ids"))
    normalized["areas"] = _normalize_field_areas(normalized.get("areas"))
    normalized["device_placements"] = _normalize_device_placements(
        normalized.get("device_placements"),
        normalized["device_ids"],
        normalized["camera_device_ids"],
        normalized["areas"],
    )
    normalized["notes"] = list(normalized.get("notes") or [])[-MAX_FIELD_NOTES:]
    normalized["events"] = list(normalized.get("events") or [])[-MAX_FIELD_EVENTS:]
    normalized["action_plans"] = list(normalized.get("action_plans") or [])[-MAX_FIELD_ACTION_PLANS:]
    normalized["reflections"] = list(normalized.get("reflections") or [])[-MAX_FIELD_REFLECTIONS:]
    normalized["updated_at"] = normalized.get("updated_at") or now
    return normalized


def _normalize_crop_profile(value, legacy_record=None):
    value = _clean_dict(value)
    legacy_record = legacy_record or {}
    return {
        "crop_name": _clean_string(value.get("crop_name"), _clean_string(legacy_record.get("crop"))),
        "cultivar": _clean_string(value.get("cultivar")),
        "growth_stage": _clean_string(value.get("growth_stage"), _clean_string(legacy_record.get("stage"))),
        "seeding_date": _clean_string(value.get("seeding_date")),
        "transplant_date": _clean_string(value.get("transplant_date")),
        "target_harvest_date": _clean_string(value.get("target_harvest_date")),
    }


def _normalize_growth_targets(value):
    value = _clean_dict(value)
    return {
        "soil_moisture_percent": _clean_range(value.get("soil_moisture_percent"), 35.0, 70.0),
        "soil_ec_us_cm": _clean_range(value.get("soil_ec_us_cm")),
        "soil_ph": _clean_range(value.get("soil_ph"), 5.5, 7.0),
        "air_humidity_percent": _clean_range(value.get("air_humidity_percent")),
        "par_umol_m2_s": _clean_range(value.get("par_umol_m2_s")),
    }


def _normalize_cultivation_context(value):
    value = _clean_dict(value)
    return {
        "cultivation_method": _clean_string(value.get("cultivation_method")),
        "soil_type": _clean_string(value.get("soil_type")),
        "substrate": _clean_string(value.get("substrate")),
        "greenhouse_type": _clean_string(value.get("greenhouse_type")),
        "mulching": _clean_string(value.get("mulching")),
        "irrigation_method": _clean_string(value.get("irrigation_method")),
        "water_source": _clean_string(value.get("water_source")),
        "bed_area_m2": _clean_float(value.get("bed_area_m2")),
        "plant_count": _clean_int(value.get("plant_count")),
        "notes": _clean_string(value.get("notes")),
    }


def _normalize_control_policy(value):
    value = _clean_dict(value)
    autonomy_level = _clean_string(value.get("autonomy_level"), "suggest_only")
    if autonomy_level not in {"observe_only", "suggest_only", "manual_approval", "auto"}:
        autonomy_level = "suggest_only"
    allowed_actions = _clean_string_list(value.get("allowed_actions")) or ["watering"]
    allowed_actions = [action for action in allowed_actions if action in {"watering", "fertigation", "misting"}]
    return {
        "objective": _clean_string(value.get("objective"), "作物の状態と安全性を優先して、必要最小限の制御を行う"),
        "autonomy_level": autonomy_level,
        "allowed_actions": allowed_actions or ["watering"],
        "max_watering_sec_per_day": _clean_int(value.get("max_watering_sec_per_day"), 0),
        "min_watering_interval_min": _clean_int(value.get("min_watering_interval_min"), 0),
        "safety_notes": _clean_string(value.get("safety_notes")),
    }


def _normalize_knowledge_context(value):
    value = _clean_dict(value)
    return {
        "research_queries": _clean_string_list(value.get("research_queries")),
        "external_reference_urls": _clean_string_list(value.get("external_reference_urls")),
        "image_observation_prompt": _clean_string(value.get("image_observation_prompt")),
        "notes": _clean_string(value.get("notes")),
    }


def _normalize_field_areas(value):
    if not isinstance(value, list):
        return []
    normalized = []
    seen_ids = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _clean_string(item.get("name"))
        if not name:
            continue
        area_id = _clean_string(item.get("id")) or _field_area_id(name)
        if area_id in seen_ids:
            continue
        area_type = _clean_string(item.get("area_type"), "section")
        if area_type not in VALID_FIELD_AREA_TYPES:
            area_type = "section"
        normalized.append(
            {
                "id": area_id,
                "name": name,
                "area_type": area_type,
                "crop_name": _clean_string(item.get("crop_name")),
                "memo": _clean_string(item.get("memo")),
            }
        )
        seen_ids.add(area_id)
    return normalized


def _normalize_device_placements(value, device_ids, camera_device_ids, areas):
    if not isinstance(value, list):
        return []
    allowed_devices = set(device_ids or []) | set(camera_device_ids or [])
    allowed_area_ids = {area.get("id") for area in areas or []}
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        device_id = _clean_string(item.get("device_id"))
        if not device_id or device_id not in allowed_devices:
            continue
        role = _clean_string(item.get("device_role")) or ("camera" if device_id in set(camera_device_ids or []) else "sensor")
        if role not in VALID_DEVICE_ROLES:
            role = "sensor"
        scope_type = _clean_string(item.get("scope_type"), "field")
        if scope_type not in VALID_DEVICE_SCOPE_TYPES:
            scope_type = "field"
        area_id = _clean_string(item.get("area_id"))
        if scope_type == "field" or area_id not in allowed_area_ids:
            area_id = ""
        key = (device_id, role)
        if key in seen:
            continue
        normalized.append(
            {
                "device_id": device_id,
                "device_role": role,
                "scope_type": scope_type,
                "area_id": area_id,
                "crop_name": _clean_string(item.get("crop_name")),
                "memo": _clean_string(item.get("memo")),
            }
        )
        seen.add(key)
    return normalized


def _field_area_id(name):
    return f"area-{uuid.uuid5(uuid.NAMESPACE_URL, name).hex[:10]}"


__instance = None


def field_repository():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = FieldRepository()
    return __instance
