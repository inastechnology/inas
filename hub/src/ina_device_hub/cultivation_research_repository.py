import copy
import json
import os
import uuid
from datetime import UTC, datetime

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting


def _now():
    return datetime.now(UTC).isoformat()


class CultivationResearchRepository:
    def __init__(self, file_path: str | None = None):
        self.file_path = file_path or os.path.join(setting().get_work_dir(), "cultivation_research.json")
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.data = {}
        self.load()

    def load(self):
        try:
            with open(self.file_path, encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        self.data = data if isinstance(data, dict) else {}

    def _field_data(self, field_id):
        return self.data.setdefault(field_id, {"hypotheses": [], "analyses": []})

    def list_hypotheses(self, field_id):
        return copy.deepcopy(self._field_data(field_id)["hypotheses"])

    @serialized_repository_write("file_path")
    def add_hypothesis(self, field_id, value):
        title = str(value.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        item = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": str(value.get("description") or "").strip(),
            "status": str(value.get("status") or "open").strip(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        if item["status"] not in {"open", "supported", "not_supported", "inconclusive", "archived"}:
            raise ValueError("unsupported hypothesis status")
        self._field_data(field_id)["hypotheses"].append(item)
        atomic_write_json(self.file_path, self.data)
        return copy.deepcopy(item)

    @serialized_repository_write("file_path")
    def update_hypothesis(self, field_id, hypothesis_id, value):
        for item in self._field_data(field_id)["hypotheses"]:
            if item["id"] != hypothesis_id:
                continue
            if "title" in value:
                title = str(value.get("title") or "").strip()
                if not title:
                    raise ValueError("title is required")
                item["title"] = title
            if "description" in value:
                item["description"] = str(value.get("description") or "").strip()
            if "status" in value:
                status = str(value.get("status") or "").strip()
                if status not in {"open", "supported", "not_supported", "inconclusive", "archived"}:
                    raise ValueError("unsupported hypothesis status")
                item["status"] = status
            item["updated_at"] = _now()
            atomic_write_json(self.file_path, self.data)
            return copy.deepcopy(item)
        raise KeyError("hypothesis not found")

    @serialized_repository_write("file_path")
    def add_analysis(self, field_id, analysis):
        item = {"id": str(uuid.uuid4()), "created_at": _now(), **analysis}
        analyses = self._field_data(field_id)["analyses"]
        analyses.append(item)
        self._field_data(field_id)["analyses"] = analyses[-200:]
        atomic_write_json(self.file_path, self.data)
        return copy.deepcopy(item)


__instance = None


def cultivation_research_repository(file_path: str | None = None):
    global __instance
    if file_path:
        return CultivationResearchRepository(file_path)
    if not __instance:
        __instance = CultivationResearchRepository()
    return __instance
