import json
from datetime import date, timedelta
from urllib import error, parse, request


class OpenMeteoWeatherService:
    DEFAULT_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    DAILY_VARIABLES = [
        "precipitation_sum",
        "rain_sum",
        "precipitation_hours",
        "sunshine_duration",
        "shortwave_radiation_sum",
        "et0_fao_evapotranspiration",
        "temperature_2m_max",
        "temperature_2m_min",
    ]

    def __init__(
        self,
        latitude: float,
        longitude: float,
        timezone: str = "Asia/Tokyo",
        archive_url: str | None = None,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self.archive_url = (archive_url or self.DEFAULT_ARCHIVE_URL).strip()

    def fetch_recent_daily_records(self, backfill_days: int = 7):
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=max(backfill_days - 1, 0))
        return self.fetch_daily_records(start_date=start_date.isoformat(), end_date=end_date.isoformat())

    def fetch_daily_records(self, start_date: str, end_date: str):
        response = self._fetch_archive(start_date=start_date, end_date=end_date)
        return self.parse_daily_records(response)

    def parse_daily_records(self, response: dict):
        daily = response.get("daily", {})
        times = daily.get("time", [])
        records = []
        for index, day in enumerate(times):
            daily_values = {
                "date": day,
                "precipitation_mm": self._get_daily_value(daily, "precipitation_sum", index),
                "rain_mm": self._get_daily_value(daily, "rain_sum", index),
                "precipitation_hours": self._get_daily_value(daily, "precipitation_hours", index),
                "sunshine_hours": self._seconds_to_hours(self._get_daily_value(daily, "sunshine_duration", index)),
                "solar_radiation_mj_m2": self._get_daily_value(daily, "shortwave_radiation_sum", index),
                "et0_fao_evapotranspiration_mm": self._get_daily_value(daily, "et0_fao_evapotranspiration", index),
                "temperature_2m_max_c": self._get_daily_value(daily, "temperature_2m_max", index),
                "temperature_2m_min_c": self._get_daily_value(daily, "temperature_2m_min", index),
            }
            records.append(
                {
                    "source": {
                        "type": "reanalysis",
                        "provider": "open_meteo",
                        "archive_url": self.archive_url,
                        "timezone": response.get("timezone") or self.timezone,
                        "requested_latitude": self.latitude,
                        "requested_longitude": self.longitude,
                        "resolved_latitude": response.get("latitude"),
                        "resolved_longitude": response.get("longitude"),
                        "elevation_m": response.get("elevation"),
                    },
                    "location": {
                        "latitude": response.get("latitude"),
                        "longitude": response.get("longitude"),
                        "requested_latitude": self.latitude,
                        "requested_longitude": self.longitude,
                        "timezone": response.get("timezone") or self.timezone,
                        "elevation_m": response.get("elevation"),
                    },
                    "daily": daily_values,
                    "units": response.get("daily_units", {}),
                    "data_quality": "reanalysis_grid_daily",
                }
            )
        return records

    def _fetch_archive(self, start_date: str, end_date: str):
        query = parse.urlencode(
            {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "start_date": start_date,
                "end_date": end_date,
                "daily": ",".join(self.DAILY_VARIABLES),
                "timezone": self.timezone,
            }
        )
        url = f"{self.archive_url}?{query}"
        req = request.Request(url, headers={"User-Agent": "ina-device-hub/1.0"})
        try:
            with request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to fetch Open-Meteo archive: {url}: {exc}") from exc

    def _get_daily_value(self, daily: dict, key: str, index: int):
        values = daily.get(key, [])
        if index >= len(values):
            return None
        return values[index]

    def _seconds_to_hours(self, seconds):
        if seconds is None:
            return None
        return round(seconds / 3600, 2)
