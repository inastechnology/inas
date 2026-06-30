import json
import os
from datetime import datetime

from ina_device_hub.setting import setting


class WeatherRecordRepository:
    SCHEMA = "ina.weather_record.v1"

    def __init__(self, file_path: str | None = None):
        self.file_path = file_path or os.path.join(setting().get_work_dir(), "weather_records.jsonl")
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def add_forecast(self, forecast: dict):
        record = self.build_forecast_record(forecast)
        return self.add_record(record)

    def add_daily_observation(self, observation: dict):
        record = self.build_daily_observation_record(observation)
        return self.add_record(record)

    def add_record(self, record: dict):
        if self.exists(record["record_id"]):
            return None

        with open(self.file_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
        return record

    def build_forecast_record(self, forecast: dict):
        source = {
            "type": "forecast",
            "provider": forecast.get("source") or "jma_xml",
            "office": forecast.get("office"),
            "area": forecast.get("area"),
            "feed_url": forecast.get("feed_url"),
            "forecast_url": forecast.get("forecast_url"),
            "report_datetime": forecast.get("report_datetime"),
            "target_datetime": forecast.get("target_datetime"),
        }
        record_id = self._forecast_record_id(source)
        return {
            "schema": self.SCHEMA,
            "record_id": record_id,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "location": {
                "office": forecast.get("office"),
                "area": forecast.get("area"),
            },
            "daily_weather": forecast.get("daily_weather", []),
            "precipitation_probabilities": forecast.get("precipitation_probabilities", []),
            "daily_summaries": self._build_daily_summaries(forecast),
            "growth_metrics": {
                "precipitation_mm": None,
                "sunshine_hours": None,
                "solar_radiation_mj_m2": None,
                "note": "JMA area forecast snapshot. Observed precipitation and sunshine are intentionally nullable for future observation sources.",
            },
        }

    def build_daily_observation_record(self, observation: dict):
        source = observation.get("source", {})
        location = observation.get("location", {})
        daily = observation.get("daily", {})
        date = daily.get("date")
        record_id = self._daily_observation_record_id(source, location, date)
        return {
            "schema": self.SCHEMA,
            "record_id": record_id,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "location": location,
            "daily_weather": [],
            "precipitation_probabilities": [],
            "daily_summaries": [
                {
                    "date": date,
                    "name": "observed_daily",
                    "weather": None,
                    "sentence": None,
                    "precipitation_probability_max_percent": None,
                    "precipitation_probability_avg_percent": None,
                    "precipitation_mm": daily.get("precipitation_mm"),
                    "rain_mm": daily.get("rain_mm"),
                    "precipitation_hours": daily.get("precipitation_hours"),
                    "sunshine_hours": daily.get("sunshine_hours"),
                    "solar_radiation_mj_m2": daily.get("solar_radiation_mj_m2"),
                    "et0_fao_evapotranspiration_mm": daily.get("et0_fao_evapotranspiration_mm"),
                    "temperature_2m_max_c": daily.get("temperature_2m_max_c"),
                    "temperature_2m_min_c": daily.get("temperature_2m_min_c"),
                    "data_quality": observation.get("data_quality", "reanalysis_grid_daily"),
                }
            ],
            "growth_metrics": {
                "precipitation_mm": daily.get("precipitation_mm"),
                "sunshine_hours": daily.get("sunshine_hours"),
                "solar_radiation_mj_m2": daily.get("solar_radiation_mj_m2"),
                "et0_fao_evapotranspiration_mm": daily.get("et0_fao_evapotranspiration_mm"),
                "note": "Daily grid reanalysis/analysis weather data for cultivation-period aggregation.",
            },
            "raw_daily": daily,
            "units": observation.get("units", {}),
        }

    def exists(self, record_id: str):
        if not os.path.exists(self.file_path):
            return False
        with open(self.file_path, encoding="utf-8") as file:
            for line in file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("record_id") == record_id:
                    return True
        return False

    def get_recent(self, limit: int = 30):
        if not os.path.exists(self.file_path):
            return []
        records = []
        with open(self.file_path, encoding="utf-8") as file:
            for line in file:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records[-limit:]

    def _forecast_record_id(self, source: dict):
        return ":".join(
            [
                source.get("provider") or "unknown",
                source.get("office") or "unknown",
                source.get("area") or "unknown",
                source.get("report_datetime") or "unknown",
                source.get("forecast_url") or "unknown",
            ]
        )

    def _daily_observation_record_id(self, source: dict, location: dict, date: str | None):
        return ":".join(
            [
                source.get("provider") or "unknown",
                source.get("type") or "unknown",
                str(location.get("requested_latitude") or location.get("latitude") or "unknown"),
                str(location.get("requested_longitude") or location.get("longitude") or "unknown"),
                date or "unknown",
            ]
        )

    def _build_daily_summaries(self, forecast: dict):
        probabilities_by_date = {}
        for probability in forecast.get("precipitation_probabilities", []):
            date_time = probability.get("date_time")
            if not date_time:
                continue
            date = date_time[:10]
            probabilities_by_date.setdefault(date, []).append(probability.get("probability_percent"))

        summaries = []
        for weather in forecast.get("daily_weather", []):
            date_time = weather.get("date_time")
            date = date_time[:10] if date_time else None
            probability_values = [value for value in probabilities_by_date.get(date, []) if value is not None]
            probability_avg = round(sum(probability_values) / len(probability_values), 1) if probability_values else None
            summaries.append(
                {
                    "date": date,
                    "name": weather.get("name"),
                    "weather": weather.get("weather"),
                    "sentence": weather.get("sentence"),
                    "precipitation_probability_max_percent": max(probability_values) if probability_values else None,
                    "precipitation_probability_avg_percent": probability_avg,
                    "precipitation_mm": None,
                    "sunshine_hours": None,
                    "solar_radiation_mj_m2": None,
                    "data_quality": "forecast_area_level",
                }
            )
        return summaries


__instance = None


def weather_record_repository(file_path: str | None = None):
    global __instance
    if file_path:
        return WeatherRecordRepository(file_path=file_path)
    if not __instance:
        __instance = WeatherRecordRepository()
    return __instance
