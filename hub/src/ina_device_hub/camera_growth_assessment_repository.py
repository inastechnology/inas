import copy
import json
import os
import uuid
from datetime import UTC, datetime

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting

SCHEMA_VERSION = 1
MAX_ASSESSMENTS = 1000


class CameraGrowthAssessmentRepository:
    repository_path = os.path.join(setting().get_work_dir(), ".camera_growth_assessments.json")

    def __init__(self):
        self.data = _empty_data()
        self.load()

    def load(self):
        if not os.path.exists(self.repository_path):
            atomic_write_json(self.repository_path, _empty_data())
        try:
            with open(self.repository_path, encoding="utf-8") as file:
                value = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            value = {}
        self.data = _normalize_data(value)

    def save(self):
        atomic_write_json(self.repository_path, self.data)

    def list(self, *, field_id: str, camera_id: str = "", limit: int = 50):
        field_id = _clean_string(field_id)
        camera_id = _clean_string(camera_id)
        limit = max(1, min(_clean_int(limit, 50), 200))
        records = [
            record for record in self.data["assessments"] if record.get("field_id") == field_id and (not camera_id or record.get("camera_id") == camera_id)
        ]
        records.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)
        return copy.deepcopy(records[:limit])

    def get(self, assessment_id: str):
        record = next((item for item in self.data["assessments"] if item.get("id") == assessment_id), None)
        return copy.deepcopy(record) if record else None

    @serialized_repository_write("repository_path")
    def create(self, value: dict):
        if not isinstance(value, dict):
            raise ValueError("assessment data must be an object")
        record = _normalize_assessment(
            {
                **value,
                "id": _clean_string(value.get("id")) or str(uuid.uuid4()),
                "created_at": _clean_string(value.get("created_at")) or datetime.now(UTC).isoformat(),
            }
        )
        if not record["field_id"] or not record["camera_id"]:
            raise ValueError("field_id and camera_id are required")
        self.data["assessments"].append(record)
        self.data["assessments"].sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)
        self.data["assessments"] = self.data["assessments"][:MAX_ASSESSMENTS]
        self.save()
        return copy.deepcopy(record)


def _empty_data():
    return {"schema_version": SCHEMA_VERSION, "assessments": []}


def _normalize_data(value):
    value = value if isinstance(value, dict) else {}
    records = value.get("assessments") if isinstance(value.get("assessments"), list) else []
    normalized = [_normalize_assessment(item) for item in records if isinstance(item, dict)]
    normalized = [item for item in normalized if item["id"] and item["field_id"] and item["camera_id"]]
    normalized.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)
    return {"schema_version": SCHEMA_VERSION, "assessments": normalized[:MAX_ASSESSMENTS]}


def _normalize_assessment(value):
    result = value.get("result") if isinstance(value.get("result"), dict) else {}
    return {
        "id": _clean_string(value.get("id"))[:120],
        "field_id": _clean_string(value.get("field_id"))[:120],
        "camera_id": _clean_string(value.get("camera_id"))[:120],
        "camera_name": _clean_string(value.get("camera_name"))[:120],
        "camera_placement_id": _clean_string(value.get("camera_placement_id"))[:80],
        "target_placement_ids": _clean_string_list(value.get("target_placement_ids"), 100, 80),
        "planting_ids": _clean_string_list(value.get("planting_ids"), 100, 120),
        "crop_labels": _clean_string_list(value.get("crop_labels"), 50, 160),
        "current_frame": _normalize_frame(value.get("current_frame")),
        "previous_frame": _normalize_frame(value.get("previous_frame")),
        "result": copy.deepcopy(result),
        "context_snapshot": _normalize_context_snapshot(value.get("context_snapshot")),
        "created_by": _clean_string(value.get("created_by"))[:254],
        "created_at": _clean_string(value.get("created_at"))[:80],
    }


def _normalize_frame(value):
    if not isinstance(value, dict):
        return None
    relative_path = _clean_string(value.get("relative_path"))
    captured_at = _clean_string(value.get("captured_at"))
    if not relative_path or not captured_at:
        return None
    return {
        "captured_at": captured_at[:80],
        "relative_path": relative_path[:500],
        "url": _clean_string(value.get("url"))[:700],
    }


def _normalize_context_snapshot(value):
    if not isinstance(value, dict):
        return {}
    # Context is deliberately constrained so request-only image data and camera
    # connection details can never be copied into the history repository.
    return copy.deepcopy({key: value.get(key) for key in ("field", "monitored_areas", "plantings", "sensor_readings", "audience") if key in value})


def _clean_string(value):
    return "" if value is None else str(value).strip()


def _clean_string_list(value, limit: int, item_length: int):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _clean_string(item)[:item_length]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__instance = None


def camera_growth_assessment_repository():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = CameraGrowthAssessmentRepository()
    return __instance
