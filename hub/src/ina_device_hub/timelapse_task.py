import os
import threading
from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger
from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.timelapse_media_service import timelapse_media_service


class TimelapseTask:
    def __init__(self):
        self.storage_connector = storage_connector()
        self.timelapse_media_service = timelapse_media_service()
        self.TIMELAPSE_INTERVAL = setting().get("timelapse_interval")

        self.routin_scheduler = BlockingScheduler()

    def start(self):
        if self.routin_scheduler.running:
            return
        self.routin_scheduler.add_job(
            self.__routin,
            "interval",
            seconds=self.TIMELAPSE_INTERVAL,
            max_instances=1,
        )
        logger.info(f"Start {self.__class__.__name__}(interval: {self.TIMELAPSE_INTERVAL})")
        self.worker_thread = threading.Thread(target=self.routin_scheduler.start)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop(self):
        if self.routin_scheduler.running:
            self.routin_scheduler.shutdown

        self.worker_thread.join()

    def __routin(self):
        camera = camera_connector()
        camera_list = camera.camera_device_repository.get_all()
        for device_id, info in camera_list.items():
            if not info.get("timelapse"):
                # skip devices that are not timelapse
                continue

            img_bytes = camera.take_picture(device_id)
            if img_bytes:
                self.timelapse_media_service.save_frame(device_id, img_bytes)
                img_key = self.get_img_key(device_id)
                self.storage_connector.save_to_cloud(img_key, img_bytes)
            else:
                logger.error(f"Failed to take picture: {device_id}")

    def get_img_key(self, device_id):
        return os.path.join(device_id, "timelapse")


__instance = None


def timelapse_task():
    global __instance
    if not __instance:
        __instance = TimelapseTask()

    return __instance
