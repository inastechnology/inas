import json
import os

from ina_device_hub.setting import setting


class LocationRepository:
    location_repo_path = os.path.join(setting().get_work_dir(), ".location_list.json")

    def __init__(self):
        self.location_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.location_repo_path):
            # create empty file
            with open(self.location_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.location_repo_path, "r") as f:
                self.location_dict = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.location_repo_path, "w") as f:
            json.dump(self.location_dict, f)

    def get(self, key):
        return self.location_dict.get(key)

    def add(self, device_id, info: dict):
        if device_id not in self.location_dict:
            self.location_dict[device_id] = info
            self.save()

    def remove(self, device_id):
        if device_id in self.location_dict:
            del self.location_dict[device_id]
            self.save()

    def get_all(self):
        return self.location_dict

    def clear(self):
        self.location_dict = {}
        self.save()


# singleton instance
__instance = None


def location_repository():
    global __instance
    if not __instance:
        __instance = LocationRepository()

    return __instance
