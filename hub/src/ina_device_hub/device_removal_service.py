from functools import lru_cache

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.field_layout_repository import field_layout_repository
from ina_device_hub.field_repository import field_repository


class DeviceRemovalConflictError(ValueError):
    def __init__(self, references: list[dict]):
        super().__init__("圃場または設置ビューから参照されているため削除できません")
        self.references = references


class DeviceRemovalService:
    def __init__(self, device_repository=None, field_repo=None, layout_repo=None, event_writer=None):
        self.device_repository = device_repository or device_config_repository()
        self.field_repository = field_repo or field_repository()
        self.layout_repository = layout_repo or field_layout_repository()
        self.event_writer = event_writer or append_device_event

    def delete(self, device_id: str, *, deleted_by: str = "unknown"):
        if self.device_repository.get(device_id) is None:
            return None
        references = self.references(device_id)
        if references:
            raise DeviceRemovalConflictError(references)
        deleted = self.device_repository.delete(device_id)
        if deleted is not None:
            self.event_writer(
                "device_deleted",
                "local",
                device_id,
                category="device",
                action="delete",
                payload={"deleted_by": deleted_by, "name": deleted.get("name"), "state": deleted.get("state")},
            )
        return deleted

    def references(self, device_id: str):
        references = []
        for field in self.field_repository.list():
            field_id = field.get("id")
            field_name = field.get("name") or field_id
            if device_id in set(field.get("device_ids") or []) | set(field.get("camera_device_ids") or []):
                references.append({"type": "field", "field_id": field_id, "field_name": field_name})
            layout = self.layout_repository.get(field_id, field_name=field_name)
            for space in layout.get("spaces") or []:
                for placement in space.get("placements") or []:
                    if (placement.get("binding") or {}).get("device_id") == device_id:
                        references.append(
                            {
                                "type": "layout",
                                "field_id": field_id,
                                "field_name": field_name,
                                "space_name": space.get("name") or space.get("id"),
                                "placement_name": placement.get("name") or placement.get("id"),
                            }
                        )
        return references


@lru_cache(maxsize=1)
def device_removal_service():
    return DeviceRemovalService()
