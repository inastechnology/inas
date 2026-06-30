import json
import os

from ina_device_hub.setting import setting


class SensorDeviceRepository:
    device_repo_path = os.path.join(setting().get_work_dir(), ".device_list.json")

    def __init__(self):
        self.device_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.device_repo_path):
            # create empty file
            with open(self.device_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.device_repo_path, "r") as f:
                self.device_dict = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.device_repo_path, "w") as f:
            json.dump(self.device_dict, f)

    def get(self, key):
        return self.device_dict.get(key)

    def add(self, device_id, info: dict):
        if device_id not in self.device_dict:
            info["id"] = device_id
            self.device_dict[device_id] = info
            self.save()

    def remove(self, device_id):
        if device_id in self.device_dict:
            del self.device_dict[device_id]
            self.save()

    def get_all(self):
        return self.device_dict

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
