import threading
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.general_log import logger
from ina_device_hub.post_watering_moisture_service import post_watering_moisture_service

DEFAULT_INTERVAL_SECONDS = 1800


class SoilMoistureNotificationTask:
    def __init__(self, monitor_service=None, device_repository=None, interval_seconds=DEFAULT_INTERVAL_SECONDS):
        self.monitor_service = monitor_service or post_watering_moisture_service()
        self.device_repository = device_repository or device_config_repository()
        self.interval_seconds = max(60, int(interval_seconds))
        self.scheduler = BlockingScheduler()
        self.worker_thread = None

    def start(self):
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self.run_once,
            "interval",
            seconds=self.interval_seconds,
            max_instances=1,
            next_run_time=datetime.now(UTC) + timedelta(seconds=10),
        )
        logger.info("Start %s(interval: %s)", self.__class__.__name__, self.interval_seconds)
        self.worker_thread = threading.Thread(target=self.scheduler.start, daemon=True)
        self.worker_thread.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
        if self.worker_thread:
            self.worker_thread.join()

    def run_once(self, now: datetime | None = None):
        try:
            return self.monitor_service.evaluate_rules(self.device_repository.get_all(), now=now or datetime.now(UTC))
        except Exception:  # noqa: BLE001
            logger.exception("Soil moisture notification evaluation failed")
            return False


__instance = None


def soil_moisture_notification_task():
    global __instance
    if not __instance:
        __instance = SoilMoistureNotificationTask()
    return __instance
