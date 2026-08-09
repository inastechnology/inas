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
                {"id": "work-3", "performed_on": "2026-07-20", "title": "確認待ち作業", "review_status": "pending"},
                {"id": "work-4", "performed_on": "2026-07-21", "title": "差戻し作業", "review_status": "rejected"},
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
        self.assertNotIn("2026-07-20", calendar["items_by_date"])
        self.assertNotIn("2026-07-21", calendar["items_by_date"])
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

        moisture = next(metric for metric in dashboard["metrics"] if metric["metric"] == "soil_moisture_percent")
        self.assertEqual(dashboard["overall_state"], "attention")
        self.assertEqual(moisture["minimum"], 45)
        self.assertEqual(moisture["maximum"], 65)
        self.assertEqual(moisture["state"], "low")
        self.assertEqual(moisture["scope_label"], "ブルーベリー鉢A")
        self.assertEqual(
            moisture["target_url"],
            "/fields/field-1/layout?target_metric=soil_moisture_percent&space=space-a&placement=pot-a&planting=planting-a",
        )

    def test_status_dashboard_includes_air_and_soil_temperature_targets(self):
        dashboard = build_field_status_dashboard(
            {
                "id": "field-1",
                "growth_targets": {
                    "air_temperature_c": {"min": 15, "max": 30},
                    "soil_temperature_c": {"min": 12, "max": 28},
                },
            },
            [
                {
                    "device_id": "ENV-001",
                    "updated_at": "2026-07-21T01:00:00+00:00",
                    "values": {"air_temperature_c": 31.5},
                },
                {
                    "device_id": "WRS-001",
                    "updated_at": "2026-07-21T01:05:00+00:00",
                    "values": {"soil_temperature_c": 21.5},
                },
            ],
        )

        metrics = {metric["metric"]: metric for metric in dashboard["metrics"]}
        self.assertEqual(metrics["air_temperature_c"]["state"], "high")
        self.assertEqual(metrics["air_temperature_c"]["unit"], "℃")
        self.assertEqual(metrics["soil_temperature_c"]["state"], "good")
        self.assertEqual(metrics["soil_temperature_c"]["minimum"], 12)
        self.assertEqual(dashboard["counts"]["attention"], 1)

    def test_status_dashboard_uses_median_of_every_valid_fgt_sensor(self):
        dashboard = build_field_status_dashboard(
            {"id": "field-1", "growth_targets": {"soil_moisture_percent": {"min": 40, "max": 70}}},
            [
                {
                    "device_id": "FGT-001",
                    "scope_label": "ライチ区画",
                    "updated_at": "2026-08-09T01:00:00+00:00",
                    "values": {
                        "soil_moisture_percent": 26,
                        "rs485_devices": [
                            {
                                "index": 0,
                                "enabled": True,
                                "ok": True,
                                "type": "soil",
                                "name": "土壌センサー1",
                                "location": "北",
                                "moisture_percent": 26,
                                "temperature_c": 30,
                                "ec_us_cm": 100,
                            },
                            {
                                "index": 1,
                                "enabled": True,
                                "ok": True,
                                "type": "soil",
                                "name": "土壌センサー2",
                                "location": "南",
                                "moisture_percent": 64,
                                "temperature_c": 34,
                                "ec_us_cm": 180,
                            },
                            {
                                "index": 2,
                                "enabled": True,
                                "ok": False,
                                "type": "soil",
                                "name": "読取エラー",
                                "moisture_percent": 95,
                            },
                        ],
                    },
                }
            ],
        )

        metrics = {metric["metric"]: metric for metric in dashboard["metrics"]}
        moisture = metrics["soil_moisture_percent"]
        self.assertEqual(moisture["value"], 45)
        self.assertEqual(moisture["source_count"], 2)
        self.assertEqual(moisture["source_summary"], "FGT-001 / 2センサーの中央値 / ライチ区画")
        self.assertEqual(metrics["soil_temperature_c"]["value"], 32)
        self.assertEqual(metrics["soil_ec_us_cm"]["value"], 140)

    def test_status_dashboard_uses_both_numbered_soil_moisture_probes(self):
        dashboard = build_field_status_dashboard(
            {},
            [
                {
                    "device_id": "SOI-001",
                    "received_at": "2026-08-09T01:00:00+00:00",
                    "values": {
                        "soil_moisture_percent": 20,
                        "soil_moisture_1_pct": 20,
                        "soil_moisture_2_pct": 60,
                    },
                }
            ],
        )

        moisture = next(metric for metric in dashboard["metrics"] if metric["metric"] == "soil_moisture_percent")
        self.assertEqual(moisture["value"], 40)
        self.assertEqual(moisture["source_count"], 2)


if __name__ == "__main__":
    unittest.main()
