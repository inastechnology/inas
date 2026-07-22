import copy
import json
import math
import os
import uuid
from datetime import UTC, datetime

from ina_device_hub.collection_search import matches_search, paginate, search_terms
from ina_device_hub.field_record_catalog import normalize_field_record_values
from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting

MAX_FIELD_NOTES = 1000
MAX_FIELD_REFLECTIONS = 300
MAX_FIELD_EVENTS = 1000
MAX_FIELD_ACTION_PLANS = 500
VALID_FIELD_AREA_TYPES = {"section", "bed", "ridge", "zone", "point", "other"}
VALID_DEVICE_SCOPE_TYPES = {"field", "section", "bed", "ridge", "zone", "point", "other"}
VALID_DEVICE_ROLES = {"environment", "soil", "watering", "camera", "actuator", "sensor", "other"}
VALID_FIELD_ENVIRONMENT_TYPES = {"", "outdoor", "greenhouse", "indoor", "semi_outdoor", "other"}
VALID_RECORD_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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


def _clean_rating(value):
    if value in (None, ""):
        return None
    rating = _clean_int(value, -1)
    if rating not in {1, 2, 3, 4, 5}:
        raise FieldValidationError("rating must be between 1 and 5")
    return rating


def _clean_attachments(values):
    if not isinstance(values, list):
        return []
    attachments = []
    for value in values[:5]:
        if not isinstance(value, dict):
            continue
        attachment_id = _clean_string(value.get("id"))
        object_key = _clean_string(value.get("object_key"))
        content_type = _clean_string(value.get("content_type"))
        if not attachment_id or not object_key.startswith("field-records/") or content_type not in VALID_RECORD_IMAGE_TYPES:
            continue
        attachments.append(
            {
                "id": attachment_id,
                "storage": "r2",
                "object_key": object_key,
                "content_type": content_type,
                "size_bytes": max(0, _clean_int(value.get("size_bytes"))),
                "original_filename": _clean_string(value.get("original_filename"))[:180],
                "url": _clean_string(value.get("url")),
            }
        )
    return attachments


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
            atomic_write_json(self.field_repo_path, {})
        try:
            with open(self.field_repo_path, encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        self.fields = {field_id: _normalize_field(field_id, record) for field_id, record in data.items() if isinstance(record, dict)}

    def save(self):
        atomic_write_json(self.field_repo_path, self.fields)

    def list(self):
        return [copy.deepcopy(field) for field in sorted(self.fields.values(), key=lambda item: item.get("name") or item.get("id"))]

    def search_records(
        self,
        field_id: str,
        *,
        query="",
        kinds=None,
        target="",
        date_from="",
        date_to="",
        page=1,
        page_size=20,
    ):
        field = self._get_existing(field_id)
        terms = search_terms(query)
        kind_filter = {_clean_string(item) for item in (kinds or []) if _clean_string(item)}
        target = _clean_string(target)
        date_from = _clean_string(date_from)[:10]
        date_to = _clean_string(date_to)[:10]
        records = []

        for event in field.get("events") or []:
            item = _field_event_search_item(event)
            if _record_search_match(item, terms, kind_filter, target, date_from, date_to):
                records.append(item)
        for note in field.get("notes") or []:
            item = _field_note_search_item(note)
            if _record_search_match(item, terms, kind_filter, target, date_from, date_to):
                records.append(item)

        records.sort(key=lambda item: (item.get("occurred_at") or "", item.get("id") or ""), reverse=True)
        return paginate(records, page=page, page_size=page_size)

    def search(self, *, query="", prefecture="", environment_type="", page=1, page_size=24):
        query = _clean_string(query).casefold()[:120]
        prefecture = _clean_string(prefecture)[:40]
        environment_type = _clean_string(environment_type)[:40]
        page = max(1, _clean_int(page, 1))
        page_size = min(100, max(1, _clean_int(page_size, 24)))

        matches = []
        for field in self.fields.values():
            location = _clean_dict(field.get("location"))
            if prefecture and location.get("prefecture") != prefecture:
                continue
            if environment_type and location.get("environment_type") != environment_type:
                continue
            if query:
                haystack = "\n".join(
                    _clean_string(value)
                    for value in (
                        field.get("name"),
                        location.get("prefecture"),
                        location.get("municipality"),
                        location.get("locality"),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            matches.append(field)

        matches.sort(key=lambda item: ((item.get("name") or item.get("id") or "").casefold(), item.get("id") or ""))
        total = len(matches)
        page_count = max(1, math.ceil(total / page_size))
        page = min(page, page_count)
        start = (page - 1) * page_size
        return {
            "items": [copy.deepcopy(field) for field in matches[start : start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
            "page_count": page_count,
        }

    def get(self, field_id: str):
        record = self.fields.get(field_id)
        return copy.deepcopy(_normalize_field(field_id, record)) if record else None

    @serialized_repository_write("field_repo_path")
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
        record["location"] = _normalize_field_location({**_clean_dict(record.get("location")), **_clean_dict(data.get("location"))})
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
        record["growth_targets"] = _normalize_growth_targets({**_clean_dict(record.get("growth_targets")), **_clean_dict(data.get("growth_targets"))})
        record["cultivation_context"] = _normalize_cultivation_context(
            {**_clean_dict(record.get("cultivation_context")), **_clean_dict(data.get("cultivation_context"))}
        )
        record["control_policy"] = _normalize_control_policy({**_clean_dict(record.get("control_policy")), **_clean_dict(data.get("control_policy"))})
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

    @serialized_repository_write("field_repo_path")
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
            "rating": _clean_rating(data.get("rating")),
            "attachments": _clean_attachments(data.get("attachments")),
        }
        notes = list(record.get("notes") or [])
        notes.append(note)
        record["notes"] = notes[-MAX_FIELD_NOTES:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(note)

    @serialized_repository_write("field_repo_path")
    def add_event(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        event_type = _clean_string(data.get("event_type"), "observation")
        occurred_at = _clean_string(data.get("occurred_at")) or _utc_now()
        try:
            record_values = normalize_field_record_values(data.get("record_values"))
        except ValueError as exc:
            raise FieldValidationError(str(exc)) from exc
        event = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "occurred_at": occurred_at,
            "event_type": event_type,
            "title": _clean_string(data.get("title"), event_type),
            "description": _clean_string(data.get("description")),
            "target_placement_id": _clean_string(data.get("target_placement_id")),
            "target_name": _clean_string(data.get("target_name")),
            "record_values": record_values,
            "amount": _clean_string(data.get("amount")),
            "unit": _clean_string(data.get("unit")),
            "device_id": _clean_string(data.get("device_id")),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
            "rating": _clean_rating(data.get("rating")),
            "attachments": _clean_attachments(data.get("attachments")),
            "source_work_log_id": _clean_string(data.get("source_work_log_id")),
            "tags": _clean_string_list(data.get("tags")),
        }
        events = list(record.get("events") or [])
        events.append(event)
        record["events"] = events[-MAX_FIELD_EVENTS:]
        record["updated_at"] = _utc_now()
        self.fields[field_id] = record
        self.save()
        return copy.deepcopy(event)

    @serialized_repository_write("field_repo_path")
    def add_reflection(self, field_id: str, data: dict):
        record = self._get_existing(field_id)
        reflection = {
            "id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "period_start": _clean_string(data.get("period_start")),
            "period_end": _clean_string(data.get("period_end")),
            "human_evaluation": _clean_string(data.get("human_evaluation")),
            "rating": _clean_rating(data.get("rating")),
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

    @serialized_repository_write("field_repo_path")
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
            "rating": _clean_rating(data.get("rating")),
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


def _field_event_search_item(event: dict):
    return {
        "id": event.get("id") or "",
        "source": "event",
        "kind": event.get("event_type") or "field_event",
        "occurred_at": event.get("occurred_at") or event.get("created_at") or "",
        "title": event.get("title") or event.get("event_type") or "記録",
        "body": event.get("description") or event.get("human_evaluation") or "",
        "target_placement_id": event.get("target_placement_id") or "",
        "target_name": event.get("target_name") or "",
        "device_id": event.get("device_id") or "",
        "rating": event.get("rating"),
        "attachments": copy.deepcopy(event.get("attachments") or []),
        "record_values": copy.deepcopy(event.get("record_values") or []),
        "tags": list(event.get("tags") or []),
        "amount": event.get("amount") or "",
        "unit": event.get("unit") or "",
    }


def _field_note_search_item(note: dict):
    return {
        "id": note.get("id") or "",
        "source": "note",
        "kind": note.get("category") or "note",
        "occurred_at": note.get("created_at") or "",
        "title": note.get("text") or "メモ",
        "body": note.get("human_evaluation") or "",
        "target_placement_id": "",
        "target_name": "",
        "device_id": "",
        "rating": note.get("rating"),
        "attachments": copy.deepcopy(note.get("attachments") or []),
        "record_values": [],
        "tags": list(note.get("tags") or []),
        "amount": "",
        "unit": "",
    }


def _record_search_match(item, terms, kind_filter, target, date_from, date_to):
    occurred_on = str(item.get("occurred_at") or "")[:10]
    if kind_filter and item.get("kind") not in kind_filter and item.get("source") not in kind_filter:
        return False
    if target and target not in {item.get("target_placement_id"), item.get("target_name")}:
        return False
    if date_from and occurred_on < date_from:
        return False
    if date_to and occurred_on > date_to:
        return False
    return matches_search(
        terms,
        [
            item.get("title"),
            item.get("body"),
            item.get("kind"),
            item.get("target_name"),
            item.get("device_id"),
            item.get("tags"),
            item.get("record_values"),
            item.get("amount"),
            item.get("unit"),
        ],
    )


def _new_field(field_id: str, now: str):
    return {
        "id": field_id,
        "name": "",
        "location": _normalize_field_location({}),
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
    normalized["location"] = _normalize_field_location(normalized.get("location"))
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


def _normalize_field_location(value):
    value = _clean_dict(value)
    environment_type = _clean_string(value.get("environment_type"))
    if environment_type not in VALID_FIELD_ENVIRONMENT_TYPES:
        environment_type = ""
    return {
        "prefecture": _clean_string(value.get("prefecture")),
        "municipality": _clean_string(value.get("municipality")),
        "locality": _clean_string(value.get("locality")),
        "environment_type": environment_type,
    }


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
        "air_temperature_c": _clean_range(value.get("air_temperature_c")),
        "air_humidity_percent": _clean_range(value.get("air_humidity_percent")),
        "soil_moisture_percent": _clean_range(value.get("soil_moisture_percent"), 35.0, 70.0),
        "soil_temperature_c": _clean_range(value.get("soil_temperature_c")),
        "soil_ec_us_cm": _clean_range(value.get("soil_ec_us_cm")),
        "soil_ph": _clean_range(value.get("soil_ph"), 5.5, 7.0),
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
