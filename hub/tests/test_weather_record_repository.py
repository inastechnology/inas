import json
import os
import tempfile
import unittest

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "x")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "x")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from ina_device_hub.weather_record_repository import WeatherRecordRepository  # noqa: E402


class WeatherRecordRepositoryTest(unittest.TestCase):
    def test_add_daily_observation_writes_aggregation_ready_record_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = WeatherRecordRepository(file_path=os.path.join(tmp_dir, "weather_records.jsonl"))
            observation = {
                "source": {
                    "type": "reanalysis",
                    "provider": "open_meteo",
                    "archive_url": "https://archive-api.open-meteo.com/v1/archive",
                    "timezone": "Asia/Tokyo",
                    "requested_latitude": 33.90366750991095,
                    "requested_longitude": 133.1918432786152,
                    "resolved_latitude": 33.919155,
                    "resolved_longitude": 133.20448,
                    "elevation_m": 8.0,
                },
                "location": {
                    "latitude": 33.919155,
                    "longitude": 133.20448,
                    "requested_latitude": 33.90366750991095,
                    "requested_longitude": 133.1918432786152,
                    "timezone": "Asia/Tokyo",
                    "elevation_m": 8.0,
                },
                "daily": {
                    "date": "2026-05-05",
                    "precipitation_mm": 0.0,
                    "rain_mm": 0.0,
                    "precipitation_hours": 0.0,
                    "sunshine_hours": 12.06,
                    "solar_radiation_mj_m2": 27.88,
                    "et0_fao_evapotranspiration_mm": 4.4,
                    "temperature_2m_max_c": 19.2,
                    "temperature_2m_min_c": 10.7,
                },
                "units": {},
                "data_quality": "reanalysis_grid_daily",
            }

            first_record = repository.add_daily_observation(observation)
            second_record = repository.add_daily_observation(observation)

            self.assertIsNotNone(first_record)
            self.assertIsNone(second_record)
            with open(repository.file_path, encoding="utf-8") as file:
                lines = file.readlines()
            self.assertEqual(len(lines), 1)

            record = json.loads(lines[0])
            self.assertEqual(record["schema"], "ina.weather_record.v1")
            self.assertEqual(record["source"]["provider"], "open_meteo")
            self.assertEqual(record["source"]["type"], "reanalysis")
            self.assertEqual(record["daily_summaries"][0]["date"], "2026-05-05")
            self.assertEqual(record["daily_summaries"][0]["precipitation_mm"], 0.0)
            self.assertEqual(record["daily_summaries"][0]["sunshine_hours"], 12.06)
            self.assertEqual(record["growth_metrics"]["solar_radiation_mj_m2"], 27.88)

    def test_add_forecast_writes_growth_weather_jsonl_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = WeatherRecordRepository(file_path=os.path.join(tmp_dir, "weather_records.jsonl"))
            forecast = {
                "source": "jma_xml",
                "office": "松山地方気象台",
                "area": "東予",
                "feed_url": "https://example.test/feed.xml",
                "forecast_url": "https://example.test/ehime.xml",
                "report_datetime": "2026-05-06T05:00:00+09:00",
                "target_datetime": "2026-05-06T05:00:00+09:00",
                "daily_weather": [
                    {
                        "name": "今日",
                        "date_time": "2026-05-06T05:00:00+09:00",
                        "weather": "晴れ時々くもり",
                        "sentence": "晴れ　時々　くもり",
                    }
                ],
                "precipitation_probabilities": [
                    {
                        "name": "０６時から１２時まで",
                        "date_time": "2026-05-06T06:00:00+09:00",
                        "duration": "PT6H",
                        "probability_percent": 0,
                    },
                    {
                        "name": "１２時から１８時まで",
                        "date_time": "2026-05-06T12:00:00+09:00",
                        "duration": "PT6H",
                        "probability_percent": 10,
                    },
                ],
            }

            first_record = repository.add_forecast(forecast)
            second_record = repository.add_forecast(forecast)

            self.assertIsNotNone(first_record)
            self.assertIsNone(second_record)
            with open(repository.file_path, encoding="utf-8") as file:
                lines = file.readlines()
            self.assertEqual(len(lines), 1)

            record = json.loads(lines[0])
            self.assertEqual(record["schema"], "ina.weather_record.v1")
            self.assertEqual(record["source"]["office"], "松山地方気象台")
            self.assertEqual(record["source"]["area"], "東予")
            self.assertEqual(record["daily_summaries"][0]["precipitation_probability_max_percent"], 10)
            self.assertEqual(record["daily_summaries"][0]["precipitation_probability_avg_percent"], 5.0)
            self.assertIsNone(record["daily_summaries"][0]["precipitation_mm"])
            self.assertIsNone(record["daily_summaries"][0]["sunshine_hours"])


if __name__ == "__main__":
    unittest.main()
