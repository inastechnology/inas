import unittest

from ina_device_hub.device_removal_service import DeviceRemovalConflictError, DeviceRemovalService


class _DeviceRepository:
    def __init__(self):
        self.records = {"old-id": {"device_id": "old-id", "name": "旧機器", "state": "disabled"}}

    def get(self, device_id):
        return self.records.get(device_id)

    def delete(self, device_id):
        return self.records.pop(device_id, None)


class _FieldRepository:
    def __init__(self, fields):
        self.fields = fields

    def list(self):
        return self.fields


class _LayoutRepository:
    def __init__(self, binding=None):
        self.binding = binding

    def get(self, field_id, field_name=""):
        del field_id, field_name
        placement = {"id": "sensor-a", "name": "土壌センサー", "binding": self.binding} if self.binding else None
        return {"spaces": [{"id": "space-root", "name": "圃場全体", "placements": [placement] if placement else []}]}


class DeviceRemovalServiceTest(unittest.TestCase):
    def test_delete_keeps_history_external_and_writes_audit_event(self):
        devices = _DeviceRepository()
        events = []
        service = DeviceRemovalService(
            device_repository=devices,
            field_repo=_FieldRepository([]),
            layout_repo=_LayoutRepository(),
            event_writer=lambda *args, **kwargs: events.append((args, kwargs)),
        )

        deleted = service.delete("old-id", deleted_by="operator@example.com")

        self.assertEqual(deleted["device_id"], "old-id")
        self.assertIsNone(devices.get("old-id"))
        self.assertEqual(events[0][0][:3], ("device_deleted", "local", "old-id"))
        self.assertEqual(events[0][1]["payload"]["deleted_by"], "operator@example.com")

    def test_delete_is_blocked_by_field_and_layout_references(self):
        fields = [{"id": "field-1", "name": "西条圃場", "device_ids": ["old-id"], "camera_device_ids": []}]
        service = DeviceRemovalService(
            device_repository=_DeviceRepository(),
            field_repo=_FieldRepository(fields),
            layout_repo=_LayoutRepository({"device_id": "old-id", "resource_type": "device"}),
            event_writer=lambda *args, **kwargs: None,
        )

        with self.assertRaises(DeviceRemovalConflictError) as raised:
            service.delete("old-id")

        self.assertEqual({item["type"] for item in raised.exception.references}, {"field", "layout"})
