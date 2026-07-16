import json
import os

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting


class SensorDeviceRepository:
    device_repo_path = os.path.join(setting().get_work_dir(), ".device_list.json")

    def __init__(self):
        self.device_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.device_repo_path):
            atomic_write_json(self.device_repo_path, {}, indent=None)
        try:
            with open(self.device_repo_path) as f:
                self.device_dict = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.device_dict = {}

    def save(self):
        atomic_write_json(self.device_repo_path, self.device_dict, indent=None)

    def get(self, key):
        return self.device_dict.get(key)

    @serialized_repository_write("device_repo_path")
    def add(self, device_id, info: dict):
        existing = self.device_dict.get(device_id, {})
        updated = {**existing, **info, "id": device_id}
        self.device_dict[device_id] = updated
        self.save()

    @serialized_repository_write("device_repo_path")
    def remove(self, device_id):
        if device_id in self.device_dict:
            del self.device_dict[device_id]
            self.save()

    def get_all(self):
        return self.device_dict

    @serialized_repository_write("device_repo_path")
    def clear(self):
        self.device_dict = {}
        self.save()


# singleton instance
__instance = None


def sensor_device_repository():
    global __instance
    if not __instance:
        __instance = SensorDeviceRepository()

    return __instance
