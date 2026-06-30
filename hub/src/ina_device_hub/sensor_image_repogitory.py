import os
import time
import boto3
from datetime import datetime, timezone, timedelta

from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.ina_db_connector import InaDBConnector
from ina_device_hub.general_log import logger


class SensorImageRepogitory:
    IMAGE_BASE_DIR = f"{setting().get('image_base_dir')}/sensor"

    def __init__(self, db_connector: InaDBConnector):
        self.db_connector = db_connector
        if not os.path.exists(self.IMAGE_BASE_DIR):
            os.makedirs(self.IMAGE_BASE_DIR)

        self.storage_connector = storage_connector()

    def save(self, device_id, imageBytes):
        # save image to cloud storage
        image_path = self.storage_connector.save_to_cloud(self.get_image_path(device_id), imageBytes, "image/jpeg")

        # insert image path to database
        yyyymmddhhmmss = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        self.db_connector.insert_sensor_image_data(device_id, yyyymmddhhmmss, image_path)

    def fetch_latest(self, device_id: str, limit: int = 1):
        sensor_images = self.db_connector.fetch_sensor_latest_image(device_id, limit)
        sensor_images_as_dict = []
        for sensor_image in sensor_images:
            device_id, yyyymmddhhmmss, image_path, created_at = sensor_image
            sensor_images_as_dict.append(
                {
                    "device_id": device_id,
                    "yyyymmddhhmmss": yyyymmddhhmmss,
                    "image_path": image_path,
                    "created_at": datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        return sensor_images_as_dict

    def get_image_dir(self, device_id):
        yyyymmdd = time.strftime("%Y%m%d", time.gmtime())
        return os.path.join(setting().get("tenant_id"), device_id, yyyymmdd)

    def get_image_path(self, device_id):
        return os.path.join(
            self.get_image_dir(device_id),
            time.strftime("%Y%m%d_%H%M%S", time.gmtime()) + ".jpg",
        )

    def fetch_from_cloud_as_bytes(self, image_path):
        try:
            response = self.storage_connector.fetch_from_cloud_as_bytes(image_path)
            return response
        except Exception as e:
            logger.error(f"Error: {e}")
            return None


# singleton instance
__instance = None


def sensor_image_repogitory(db_connector: InaDBConnector = None):
    global __instance
    if not __instance:
        if db_connector is None:
            raise ValueError("db_connector is required")
        __instance = SensorImageRepogitory(db_connector)
    return __instance
