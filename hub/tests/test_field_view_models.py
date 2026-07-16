import unittest

from ina_device_hub.field_calendar_view import build_calendar_todo_items
from ina_device_hub.field_record_calendar import build_field_record_calendar
from ina_device_hub.field_status_dashboard import build_field_status_dashboard


class FieldViewModelsTest(unittest.TestCase):
    def test_calendar_todo_uses_catalog_metadata_and_honors_limit(self):
        bundle = {
            "suggestions": [
                {
                    "planting_id": "planting-1",
                    "placement_name": "鉢A",
                    "crop_name": "ブルーベリー",
                    "timing_state": "due",
                    "action": {
                        "id": "action-1",
                        "action_type": "施肥",
                        "title": "少量施肥",
                        "priority": "required",
                        "reason": "樹勢を維持するため",
                    },
                },
                {
                    "planting_id": "planting-2",
                    "crop_name": "イチゴ",
                    "action": {"action_type": "watering"},
                },
            ]
        }

        items = build_calendar_todo_items("field/1", bundle, limit=1)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["action_type"], "fertilization")
        self.assertEqual(items[0]["action_type_label"], "追肥")
        self.assertEqual(items[0]["priority_label"], "必須")
        self.assertEqual(items[0]["title"], "ブルーベリーに今、追肥の確認が必要です")
        self.assertEqual(items[0]["calendar_url"], "/fields/field/1/calendar?planting=planting-1&action=action-1")

    def test_record_calendar_deduplicates_work_logs_and_groups_measurements(self):
        field = {
            "events": [
                {
                    "id": "event-1",
                    "source_work_log_id": "work-1",
                    "occurred_at": "2026-07-18T08:30:00+09:00",
                    "title": "葉色を確認",
                    "rating": 5,
                    "attachments": [
                        {
                            "id": "image-1",
                            "url": "/record-images/image-1",
                            "content_type": "image/png",
                            "original_filename": "leaf.png",
                        }
                    ],
                }
            ]
        }
        bundle = {
            "work_logs": [
                {"id": "work-1", "performed_on": "2026-07-18", "title": "重複する作業"},
                {"id": "work-2", "performed_on": "2026-07-19", "title": "追肥"},
            ],
            "plantings": [
                {
                    "id": "planting-1",
                    "planted_on": "2026-07-01",
                    "crop_name": "イチゴ",
                    "placement_name": "1番畝",
                }
            ],
        }
        measurements = [
            {"date": "2026-07-18", "time": "08:00", "label": "土壌水分", "value": 48},
            {"date": "2026-07-18", "time": "08:05", "label": "EC", "value": 850},
        ]

        calendar = build_field_record_calendar(field, bundle, "2026-07", measurements)

        self.assertEqual(calendar["previous"], "2026-06")
        self.assertEqual(calendar["next"], "2026-08")
        self.assertEqual([item["label"] for item in calendar["items_by_date"]["2026-07-18"]], ["葉色を確認"])
        self.assertEqual(calendar["items_by_date"]["2026-07-18"][0]["rating_emoji"], "😄")
        self.assertEqual(calendar["items_by_date"]["2026-07-18"][0]["attachments"][0]["url"], "/record-images/image-1")
        self.assertEqual([item["label"] for item in calendar["items_by_date"]["2026-07-19"]], ["追肥"])
        self.assertEqual(len(calendar["measurements_by_date"]["2026-07-18"]), 2)

    def test_status_dashboard_uses_target_for_sensor_placement(self):
        dashboard = build_field_status_dashboard(
            {"id": "field-1", "growth_targets": {"soil_moisture_percent": {"min": 20, "max": 80}}},
            [
                {
                    "device_id": "SOI-001",
                    "scope_label": "ブルーベリー鉢A",
                    "target_placement_ids": ["pot-a"],
                    "updated_at": "2026-07-15T00:00:00+00:00",
                    "values": {"soil_moisture_percent": 42},
                }
            ],
            [
                {
                    "id": "planting-a",
                    "space_id": "space-a",
                    "placement_id": "pot-a",
                    "growth_targets": {"soil_moisture_percent": {"min": 45, "max": 65}},
                },
                {
                    "placement_id": "bed-b",
                    "growth_targets": {"soil_moisture_percent": {"min": 30, "max": 70}},
                },
            ],
        )

        moisture = dashboard["metrics"][0]
        self.assertEqual(dashboard["overall_state"], "attention")
        self.assertEqual(moisture["minimum"], 45)
        self.assertEqual(moisture["maximum"], 65)
        self.assertEqual(moisture["state"], "low")
        self.assertEqual(moisture["scope_label"], "ブルーベリー鉢A")
        self.assertEqual(
            moisture["target_url"],
            "/fields/field-1/layout?target_metric=soil_moisture_percent&space=space-a&placement=pot-a&planting=planting-a",
        )


if __name__ == "__main__":
    unittest.main()
