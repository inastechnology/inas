import json
import os
import uuid

from ina_device_hub.setting import setting


class CameraDeviceRepository:
    camera_device_repo_path = os.path.join(setting().get_work_dir(), ".camera_device_list.json")

    def __init__(self):
        self.camera_dict = {}
        self.load()

    def load(self):
        if not os.path.exists(self.camera_device_repo_path):
            # create empty file
            with open(self.camera_device_repo_path, "w") as f:
                f.write("{}")
        try:
            with open(self.camera_device_repo_path, "r") as f:
                self.camera_dict = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.camera_device_repo_path, "w") as f:
            json.dump(self.camera_dict, f)

    def get(self, key):
        return self.camera_dict.get(key)

    def add(self, device_id: str = None, info: dict = {}):
        if device_id is None:
            # generate new device_id
            device_id = f"INACD-{str(uuid.uuid4())}"

        if device_id not in self.camera_dict:
            info["id"] = device_id
            self.camera_dict[device_id] = info
            self.save()

    def remove(self, device_id):
        if device_id in self.camera_dict:
            del self.camera_dict[device_id]
            self.save()

    def get_all(self):
        return self.camera_dict

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
