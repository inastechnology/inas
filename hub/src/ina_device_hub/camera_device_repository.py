import copy
import json
import os
import uuid

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting


class CameraDeviceRepository:
    camera_device_repo_path = os.path.join(setting().get_work_dir(), ".camera_device_list.json")

    def __init__(self):
        self.camera_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.camera_device_repo_path):
            atomic_write_json(self.camera_device_repo_path, {}, indent=None)
        try:
            with open(self.camera_device_repo_path, encoding="utf-8") as file:
                value = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            value = {}
        self.camera_dict = {str(device_id): record for device_id, record in value.items() if isinstance(record, dict)} if isinstance(value, dict) else {}

    def save(self):
        atomic_write_json(self.camera_device_repo_path, self.camera_dict)

    def get(self, key):
        record = self.camera_dict.get(key)
        return copy.deepcopy(record) if isinstance(record, dict) else None

    @serialized_repository_write("camera_device_repo_path")
    def add(self, device_id: str = None, info: dict | None = None):
        info = dict(info or {})
        if device_id is None:
            device_id = f"INACD-{str(uuid.uuid4())}"

        if device_id not in self.camera_dict:
            info["id"] = device_id
            self.camera_dict[device_id] = info
            self.save()
        return self.get(device_id)

    @serialized_repository_write("camera_device_repo_path")
    def upsert(self, device_id: str, info: dict):
        record = {**dict(info or {}), "id": device_id}
        self.camera_dict[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("camera_device_repo_path")
    def remove(self, device_id):
        deleted = self.camera_dict.pop(device_id, None)
        if deleted is not None:
            self.save()
        return copy.deepcopy(deleted) if isinstance(deleted, dict) else None

    def get_all(self):
        return copy.deepcopy(self.camera_dict)

    @serialized_repository_write("camera_device_repo_path")
    def clear(self):
        self.camera_dict = {}
        self.save()


# singleton instance
__instance = None


def camera_device_repository():
    global __instance
    if not __instance:
        __instance = CameraDeviceRepository()

    return __instance
