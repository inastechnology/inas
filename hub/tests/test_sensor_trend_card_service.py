import io
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image

from ina_device_hub.sensor_trend_card_service import SensorTrendCardService


class SensorTrendCardServiceTest(unittest.TestCase):
    def setUp(self):
        self.timezone = ZoneInfo("Asia/Tokyo")
        self.start_at = datetime(2026, 9, 2, 20, 0, tzinfo=self.timezone)
        self.end_at = datetime(2026, 9, 5, 20, 0, tzinfo=self.timezone)
        self.service = SensorTrendCardService()

    def test_build_series_prefers_supported_metrics_and_averages_each_hour(self):
        measurements = [
            self._measurement("soil-1", "soil_moisture_percent", "2026-09-03T10:05:00+09:00", 40),
            self._measurement("soil-1", "soil_moisture_percent", "2026-09-03T10:35:00+09:00", 44),
            self._measurement("soil-1", "soil_moisture_percent", "2026-09-04T10:00:00+09:00", 48),
            self._measurement("env-1", "par_umol_m2_s", "2026-09-03T12:00:00+09:00", 700),
            self._measurement("env-1", "par_umol_m2_s", "2026-09-04T12:00:00+09:00", 900),
            self._measurement("env-1", "soil_temperature_c", "2026-09-03T12:00:00+09:00", 21),
            self._measurement("env-1", "soil_temperature_c", "2026-09-04T12:00:00+09:00", 23),
            self._measurement("env-1", "soil_ec_us_cm", "2026-09-04T12:00:00+09:00", 800),
        ]

        result = self.service.build_series(
            measurements,
            start_at=self.start_at,
            end_at=self.end_at,
            device_names={"soil-1": "鉢センサー", "env-1": "環境センサー"},
        )

        self.assertEqual([item["metric"] for item in result], ["soil_moisture_percent", "par_umol_m2_s", "soil_temperature_c"])
        self.assertEqual(result[0]["device_name"], "鉢センサー")
        self.assertEqual(result[0]["points"][0]["value"], 42)
        self.assertEqual(result[1]["label"], "光量（PAR）")
        self.assertEqual(result[2]["label"], "地温")
        self.assertNotIn("device_name", self.service.summarize_for_ai(result)[0])
        self.assertEqual(self.service._value_range([0, 100], floor=0)[0], 0)

    def test_rendered_card_is_instagram_portrait_jpeg_with_short_impression(self):
        series = self.service.build_series(
            [
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-03T10:00:00+09:00", 42),
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-05T10:00:00+09:00", 47),
            ],
            start_at=self.start_at,
            end_at=self.end_at,
            device_names={"sensor-1": "鉢センサー"},
        )

        image_bytes = self.service.render_jpeg(series, "今日も穏やか", start_at=self.start_at, end_at=self.end_at)
        with Image.open(io.BytesIO(image_bytes)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1080, 1350))
        self.assertEqual(self.service.clean_impression("「今日も穏やか。」"), "今日も穏やか")
        self.assertEqual(self.service.clean_impression("これは十文字を確実に超える長い文章です"), "")
        self.assertEqual(self.service._font_runs("直近3日 PAR"), [(False, "直近"), (True, "3"), (False, "日"), (True, " PAR")])

    def test_editorial_focus_rotates_and_caption_reports_the_selected_fact(self):
        series = self.service.build_series(
            [
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-03T10:00:00+09:00", 42),
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-05T10:00:00+09:00", 47),
                self._measurement("sensor-1", "par_umol_m2_s", "2026-09-03T12:00:00+09:00", 700),
                self._measurement("sensor-1", "par_umol_m2_s", "2026-09-05T12:00:00+09:00", 900),
            ],
            start_at=self.start_at,
            end_at=self.end_at,
        )

        context = self.service.build_editorial_context(series, end_at=self.end_at, previous_focus_metric="soil_moisture_percent")
        prioritized = self.service.prioritize_series(series, context)
        context["angle"] = "range"
        context["angle_label"] = self.service.EDITORIAL_ANGLES["range"]["label"]
        caption = self.service.build_caption(
            prioritized,
            "光量の幅に注目",
            start_at=self.start_at,
            end_at=self.end_at,
            editorial_context=context,
        )

        self.assertEqual(context["focus_metric"], "par_umol_m2_s")
        self.assertEqual(prioritized[0]["metric"], "par_umol_m2_s")
        self.assertIn("光量（PAR）の振れ幅（700〜900µmol/m²/s）", caption)
        self.assertIn("#PAR", caption)

    def test_duplicate_ai_impression_is_replaced_with_metric_specific_heading(self):
        series = self.service.build_series(
            [
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-03T10:00:00+09:00", 42),
                self._measurement("sensor-1", "soil_moisture_percent", "2026-09-05T10:00:00+09:00", 47),
            ],
            start_at=self.start_at,
            end_at=self.end_at,
        )
        context = self.service.build_editorial_context(series, end_at=self.end_at)
        context.update({"angle": "change", "direction": "上向き"})

        impression = self.service.choose_impression(
            "変化をそっと見守ろう",
            series,
            editorial_context=context,
            recent_impressions=["変化をそっと見守ろう"],
        )

        self.assertEqual(impression, "水分は上向き")
        self.assertLessEqual(len(impression), self.service.MAX_IMPRESSION_CHARACTERS)

    @staticmethod
    def _measurement(device_id, metric, measured_at, value):
        return {"device_id": device_id, "metric": metric, "measured_at": measured_at, "value": value, "quality": "ok"}


if __name__ == "__main__":
    unittest.main()
