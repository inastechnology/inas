import copy
import json
import os
import uuid
from datetime import UTC, datetime

from ina_device_hub.setting import setting


MAX_FIELD_NOTES = 1000
MAX_FIELD_REFLECTIONS = 300
MAX_FIELD_EVENTS = 1000


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
        record["crop"] = _clean_string(data.get("crop"), record.get("crop"))
        record["stage"] = _clean_string(data.get("stage"), record.get("stage"))
        record["memo"] = _clean_string(data.get("memo"), record.get("memo"))
        if "device_ids" in data:
            record["device_ids"] = _clean_string_list(data.get("device_ids"))
        if "camera_device_ids" in data:
            record["camera_device_ids"] = _clean_string_list(data.get("camera_device_ids"))
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
        "memo": "",
        "device_ids": [],
        "camera_device_ids": [],
        "notes": [],
        "events": [],
        "reflections": [],
        "created_at": now,
        "updated_at": now,
    }


def _normalize_field(field_id: str, record: dict):
    now = _utc_now()
    normalized = _new_field(field_id, record.get("created_at") or now)
    normalized.update(record)
    normalized["id"] = field_id
    normalized["device_ids"] = _clean_string_list(normalized.get("device_ids"))
    normalized["camera_device_ids"] = _clean_string_list(normalized.get("camera_device_ids"))
    normalized["notes"] = list(normalized.get("notes") or [])[-MAX_FIELD_NOTES:]
    normalized["events"] = list(normalized.get("events") or [])[-MAX_FIELD_EVENTS:]
    normalized["reflections"] = list(normalized.get("reflections") or [])[-MAX_FIELD_REFLECTIONS:]
    normalized["updated_at"] = normalized.get("updated_at") or now
    return normalized


__instance = None


def field_repository():
    global __instance
    if not __instance:
        __instance = FieldRepository()
    return __instance
