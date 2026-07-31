import threading
from datetime import datetime

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.field_repository import field_repository
from ina_device_hub.general_log import logger
from ina_device_hub.open_meteo_weather_service import OpenMeteoWeatherService
from ina_device_hub.setting import setting
from ina_device_hub.weather_forecast_service import weather_forecast_service
from ina_device_hub.weather_record_repository import weather_record_repository


class WeatherRecordTask:
    def __init__(self):
        self.settings = setting().get("weather")
        self.provider = self.settings.get("provider", "open_meteo")
        self.open_meteo_service = OpenMeteoWeatherService(
            latitude=self.settings.get("latitude"),
            longitude=self.settings.get("longitude"),
            timezone=self.settings.get("timezone", "Asia/Tokyo"),
            archive_url=self.settings.get("open_meteo_archive_url"),
        )
        self.forecast_service = weather_forecast_service(
            forecast_url=self.settings.get("forecast_url"),
            area_name=self.settings.get("area_name"),
            office_name=self.settings.get("office_name"),
            forecast_title=self.settings.get("forecast_title"),
        )
        self.repository = weather_record_repository()
        self.scheduler = BlockingScheduler()

    def start(self):
        if not self.settings.get("record_enabled") or self.scheduler.running:
            return

        interval_seconds = self.settings.get("record_interval_seconds", 21600)
        self.scheduler.add_job(
            self._run,
            "interval",
            seconds=interval_seconds,
            next_run_time=datetime.now(),
            max_instances=1,
        )
        logger.info(f"Start {self.__class__.__name__}(interval: {interval_seconds})")
        worker_thread = threading.Thread(target=self.scheduler.start)
        worker_thread.daemon = True
        worker_thread.start()

    def _run(self):
        if self.provider == "open_meteo":
            self._record_open_meteo_daily_weather()
            return

        self._record_jma_forecast()

    def _record_open_meteo_daily_weather(self):
        self._record_open_meteo_service(self.open_meteo_service, field_id=None)
        for field in field_repository().list():
            location = field.get("weather_location") or {}
            if location.get("status") != "confirmed":
                continue
            service = OpenMeteoWeatherService(
                latitude=location.get("latitude"),
                longitude=location.get("longitude"),
                timezone=location.get("timezone") or "Asia/Tokyo",
                archive_url=self.settings.get("open_meteo_archive_url"),
            )
            self._record_open_meteo_service(service, field_id=field["id"])

    def _record_open_meteo_service(self, service, field_id):
        try:
            observations = service.fetch_recent_daily_records(
                backfill_days=self.settings.get("backfill_days", 7),
            )
        except RuntimeError:
            logger.exception(f"Failed to record Open-Meteo daily weather (field_id={field_id or 'legacy-global'})")
            return

        added_count = 0
        for observation in observations:
            record = self.repository.add_daily_observation(observation, field_id=field_id)
            if record:
                added_count += 1
                logger.info(f"Open-Meteo daily weather recorded: {record['record_id']}")
        if added_count == 0:
            logger.info(f"Skip Open-Meteo daily weather records because recent days exist (field_id={field_id or 'legacy-global'})")

    def _record_jma_forecast(self):
        try:
            forecast = self.forecast_service.fetch_forecast()
            record = self.repository.add_forecast(forecast)
        except RuntimeError:
            logger.exception("Failed to record weather forecast")
            return

        if record:
            logger.info(f"Weather forecast recorded: {record['record_id']}")
        else:
            logger.info("Skip weather forecast record because the report is already recorded")


__instance = None


def weather_record_task():
    global __instance
    if not __instance:
        __instance = WeatherRecordTask()
    return __instance
