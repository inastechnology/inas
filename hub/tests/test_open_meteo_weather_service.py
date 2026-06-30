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

from ina_device_hub.open_meteo_weather_service import OpenMeteoWeatherService  # noqa: E402


class OpenMeteoWeatherServiceTest(unittest.TestCase):
    def test_parse_daily_records_maps_growth_metrics(self):
        service = OpenMeteoWeatherService(
            latitude=33.90366750991095,
            longitude=133.1918432786152,
            timezone="Asia/Tokyo",
        )
        records = service.parse_daily_records(
            {
                "latitude": 33.919155,
                "longitude": 133.20448,
                "timezone": "Asia/Tokyo",
                "elevation": 8.0,
                "daily_units": {"precipitation_sum": "mm", "sunshine_duration": "s"},
                "daily": {
                    "time": ["2026-05-05"],
                    "precipitation_sum": [0.0],
                    "rain_sum": [0.0],
                    "precipitation_hours": [0.0],
                    "sunshine_duration": [43422.91],
                    "shortwave_radiation_sum": [27.88],
                    "et0_fao_evapotranspiration": [4.4],
                    "temperature_2m_max": [19.2],
                    "temperature_2m_min": [10.7],
                },
            }
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source"]["provider"], "open_meteo")
        self.assertEqual(record["source"]["type"], "reanalysis")
        self.assertEqual(record["daily"]["date"], "2026-05-05")
        self.assertEqual(record["daily"]["precipitation_mm"], 0.0)
        self.assertEqual(record["daily"]["sunshine_hours"], 12.06)
        self.assertEqual(record["daily"]["solar_radiation_mj_m2"], 27.88)
        self.assertEqual(record["daily"]["et0_fao_evapotranspiration_mm"], 4.4)


if __name__ == "__main__":
    unittest.main()
