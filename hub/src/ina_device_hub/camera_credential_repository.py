import copy
import json
import os

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting


class CameraCredentialRepository:
    credential_path = os.path.join(setting().get_work_dir(), ".camera_credentials.json")

    def __init__(self):
        self.credentials = {}
        self.load()

    def load(self):
        if not os.path.exists(self.credential_path):
            self.credentials = {}
            return
        try:
            with open(self.credential_path, encoding="utf-8") as file:
                value = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            value = {}
        self.credentials = value if isinstance(value, dict) else {}

    def save(self):
        atomic_write_json(self.credential_path, self.credentials)
        os.chmod(self.credential_path, 0o600)

    def get(self, device_id: str):
        value = self.credentials.get(device_id)
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    @serialized_repository_write("credential_path")
    def set(self, device_id: str, *, username: str, password: str):
        value = {"username": str(username), "password": str(password)}
        self.credentials[device_id] = value
        self.save()
        return copy.deepcopy(value)

    @serialized_repository_write("credential_path")
    def remove(self, device_id: str):
        deleted = self.credentials.pop(device_id, None)
        if deleted is not None:
            self.save()
        return copy.deepcopy(deleted) if isinstance(deleted, dict) else None

    def get_all(self):
        return copy.deepcopy(self.credentials)


__instance = None


def camera_credential_repository():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = CameraCredentialRepository()
    return __instance
