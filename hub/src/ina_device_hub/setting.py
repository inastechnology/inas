import json
import os
import sys
import uuid
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# device name
try:
    DEVICE_NAME = os.environ["HOSTNAME"]
except KeyError:
    DEVICE_NAME = "ina-device-hub"

# work directory
try:
    WORK_DIR = os.environ["WORK_DIR"]
    WORK_DIR = os.path.expanduser(WORK_DIR)
except KeyError:
    WORK_DIR = os.path.expanduser("~/.ina-device-hub")

if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)

# Turso settings
try:
    TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
    TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

try:
    LOCAL_STORAGE_BASE_DIR = os.environ["LOCAL_STORAGE_BASE_DIR"]
    LOCAL_STORAGE_BASE_DIR = os.path.expanduser(LOCAL_STORAGE_BASE_DIR)
except KeyError:
    LOCAL_STORAGE_BASE_DIR = "./.data/storage"

if not os.path.exists(LOCAL_STORAGE_BASE_DIR):
    os.makedirs(LOCAL_STORAGE_BASE_DIR)

try:
    S3_ENDPOINT_URL = os.environ["S3_ENDPOINT_URL"]
    S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
    S3_BUCKET_REGION = os.environ["S3_BUCKET_REGION"]
    S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
    S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

S3_TMP_ENDPOINT_URL = os.environ.get("S3_TMP_ENDPOINT_URL", "").strip()
S3_TMP_BUCKET_NAME = os.environ.get("S3_TMP_BUCKET_NAME", "").strip()
S3_TMP_BUCKET_REGION = os.environ.get("S3_TMP_BUCKET_REGION", "").strip()
S3_TMP_ACCESS_KEY = os.environ.get("S3_TMP_ACCESS_KEY", "").strip()
S3_TMP_SECRET_KEY = os.environ.get("S3_TMP_SECRET_KEY", "").strip()
S3_TMP_BASE_URL = os.environ.get("S3_TMP_BASE_URL", "").strip()

# MQTT settings
try:
    MQTT_BROKER_URL = os.environ["MQTT_BROKER_URL"]
    MQTT_BROKER_PORT = int(os.environ["MQTT_BROKER_PORT"])
    MQTT_BROKER_USERNAME = os.environ["MQTT_BROKER_USERNAME"]
    MQTT_BROKER_PASSWORD = os.environ["MQTT_BROKER_PASSWORD"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")

# sensor settings
try:
    SENSOR_SAVE_IMAGE = bool("true" == os.environ["SENSOR_SAVE_IMAGE"].lower())
    SENSOR_SAVE_AUDIO = bool("true" == os.environ["SENSOR_SAVE_AUDIO"].lower())
except KeyError:
    SENSOR_SAVE_IMAGE = False
    SENSOR_SAVE_AUDIO = False

# other settings
try:
    TIMELAPSE_INTERVAL = int(os.environ["TIMELAPSE_INTERVAL"])
except KeyError:
    sys.exit("Please set TIMELAPSE_INTERVAL in .env file")

DEFAULT_JMA_WEATHER_FEED_URL = "https://www.data.jma.go.jp/developer/xml/feed/regular.xml"
WEATHER_RECORD_ENABLED = bool("true" == os.environ.get("WEATHER_RECORD_ENABLED", "true").lower())
WEATHER_RECORD_INTERVAL_SECONDS = int(os.environ.get("WEATHER_RECORD_INTERVAL_SECONDS", "21600"))
WEATHER_PROVIDER = os.environ.get("WEATHER_PROVIDER", "open_meteo").strip()
WEATHER_LATITUDE = float(os.environ.get("WEATHER_LATITUDE", "33.90366750991095"))
WEATHER_LONGITUDE = float(os.environ.get("WEATHER_LONGITUDE", "133.1918432786152"))
WEATHER_TIMEZONE = os.environ.get("WEATHER_TIMEZONE", "Asia/Tokyo").strip()
WEATHER_BACKFILL_DAYS = int(os.environ.get("WEATHER_BACKFILL_DAYS", "7"))
WEATHER_OPEN_METEO_ARCHIVE_URL = os.environ.get("WEATHER_OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive").strip()
WEATHER_FORECAST_URL = os.environ.get("WEATHER_FORECAST_URL", os.environ.get("INSTAGRAM_WEATHER_FORECAST_URL", DEFAULT_JMA_WEATHER_FEED_URL)).strip()
WEATHER_AREA_NAME = os.environ.get("WEATHER_AREA_NAME", os.environ.get("INSTAGRAM_WEATHER_AREA_NAME", "東予")).strip()
WEATHER_OFFICE_NAME = os.environ.get("WEATHER_OFFICE_NAME", os.environ.get("INSTAGRAM_WEATHER_OFFICE_NAME", "松山地方気象台")).strip()
WEATHER_FORECAST_TITLE = os.environ.get("WEATHER_FORECAST_TITLE", os.environ.get("INSTAGRAM_WEATHER_FORECAST_TITLE", "府県天気予報")).strip()

INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
INSTAGRAM_SENSOR_ID = os.environ.get("INSTAGRAM_SENSOR_ID", "").strip()
INSTAGRAM_CAMERA_ID = os.environ.get("INSTAGRAM_CAMERA_ID", "").strip()
INSTAGRAM_PLANT_POSITION_PROMPT = os.environ.get("INSTAGRAM_PLANT_POSITION_PROMPT", "").strip()
INSTAGRAM_ADMIN_USERNAME = os.environ.get("INSTAGRAM_ADMIN_USERNAME", "").strip()
INSTAGRAM_WEATHER_FORECAST_URL = os.environ.get("INSTAGRAM_WEATHER_FORECAST_URL", WEATHER_FORECAST_URL).strip()
INSTAGRAM_WEATHER_AREA_NAME = os.environ.get("INSTAGRAM_WEATHER_AREA_NAME", WEATHER_AREA_NAME).strip()
INSTAGRAM_WEATHER_OFFICE_NAME = os.environ.get("INSTAGRAM_WEATHER_OFFICE_NAME", WEATHER_OFFICE_NAME).strip()
INSTAGRAM_WEATHER_FORECAST_TITLE = os.environ.get("INSTAGRAM_WEATHER_FORECAST_TITLE", WEATHER_FORECAST_TITLE).strip()

AI_ENABLED = bool("true" == os.environ.get("AI_ENABLED", "false").lower())
AI_AGENT_SCHEDULE_START = os.environ.get("AI_AGENT_SCHEDULE_START", "09:01").strip()
AI_IMAGE_ANALYZE_API_KEY = os.environ.get("AI_IMAGE_ANALYZE_API_KEY", "").strip()
AI_IMAGE_ANALYZE_BASE_URL = os.environ.get("AI_IMAGE_ANALYZE_BASE_URL", "").strip()
AI_IMAGE_ANALYZE_MODEL = os.environ.get("AI_IMAGE_ANALYZE_MODEL", "").strip()
AI_TEXT_ANALYZE_API_KEY = os.environ.get("AI_TEXT_ANALYZE_API_KEY", "").strip()
AI_TEXT_ANALYZE_BASE_URL = os.environ.get("AI_TEXT_ANALYZE_BASE_URL", "").strip()
AI_TEXT_ANALYZE_MODEL = os.environ.get("AI_TEXT_ANALYZE_MODEL", "").strip()

DEVICE_CONFIG_DEFAULT_NTP_SERVER = os.environ.get("DEVICE_CONFIG_DEFAULT_NTP_SERVER", DEVICE_NAME)
DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC = int(os.environ.get("DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC", "32400"))
DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD = int(os.environ.get("DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD", "35"))

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()


def get_device_id():
    prefix = "inahub-"
    try:
        # grep Serial /proc/cpuinfo|awk '{print $3}'
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("Serial"):
                    return prefix + line.split(":")[1].strip()
    except FileNotFoundError:
        pass
    return prefix + str(uuid.getnode())


# Default settings
DEFAULT_SETTINGS = {
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "device_id": get_device_id(),
    "device_name": DEVICE_NAME,
    "turso": {
        "database_url": TURSO_DATABASE_URL,
        "auth_token": TURSO_AUTH_TOKEN,
        "local_db_path": os.path.join(os.path.expanduser(WORK_DIR), "ina.db"),
    },
    "storage_bucket": {
        "endpoint_url": S3_ENDPOINT_URL,
        "bucket_name": S3_BUCKET_NAME,
        "region": S3_BUCKET_REGION,
        "access_key": S3_ACCESS_KEY,
        "secret_key": S3_SECRET_KEY,
    },
    "temporary_storage_bucket": {
        "endpoint_url": S3_TMP_ENDPOINT_URL,
        "bucket_name": S3_TMP_BUCKET_NAME,
        "region": S3_TMP_BUCKET_REGION,
        "access_key": S3_TMP_ACCESS_KEY,
        "secret_key": S3_TMP_SECRET_KEY,
        "base_url": S3_TMP_BASE_URL,
    },
    "local_storage_base_dir": LOCAL_STORAGE_BASE_DIR,
    "timelapse_interval": TIMELAPSE_INTERVAL,
    "weather": {
        "record_enabled": WEATHER_RECORD_ENABLED,
        "record_interval_seconds": WEATHER_RECORD_INTERVAL_SECONDS,
        "provider": WEATHER_PROVIDER,
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "timezone": WEATHER_TIMEZONE,
        "backfill_days": WEATHER_BACKFILL_DAYS,
        "open_meteo_archive_url": WEATHER_OPEN_METEO_ARCHIVE_URL,
        "forecast_url": WEATHER_FORECAST_URL,
        "area_name": WEATHER_AREA_NAME,
        "office_name": WEATHER_OFFICE_NAME,
        "forecast_title": WEATHER_FORECAST_TITLE,
    },
    "instagram": {
        "user_id": INSTAGRAM_USER_ID,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
        "sensor_id": INSTAGRAM_SENSOR_ID,
        "camera_id": INSTAGRAM_CAMERA_ID,
        "plant_position_prompt": INSTAGRAM_PLANT_POSITION_PROMPT,
        "admin_username": INSTAGRAM_ADMIN_USERNAME,
        "weather_forecast_url": INSTAGRAM_WEATHER_FORECAST_URL,
        "weather_area_name": INSTAGRAM_WEATHER_AREA_NAME,
        "weather_office_name": INSTAGRAM_WEATHER_OFFICE_NAME,
        "weather_forecast_title": INSTAGRAM_WEATHER_FORECAST_TITLE,
    },
    "mqtt": {
        "mqtt_broker": MQTT_BROKER_URL,
        "mqtt_port": MQTT_BROKER_PORT,
        "mqtt_client_id": DEVICE_NAME,
        "mqtt_username": MQTT_BROKER_USERNAME,
        "mqtt_password": MQTT_BROKER_PASSWORD,
    },
    "ai": {
        "enabled": AI_ENABLED,
        "agent_schedule_start": AI_AGENT_SCHEDULE_START,
        "image_analyze_api_key": AI_IMAGE_ANALYZE_API_KEY,
        "image_analyze_base_url": AI_IMAGE_ANALYZE_BASE_URL,
        "image_analyze_model": AI_IMAGE_ANALYZE_MODEL,
        "text_analyze_api_key": AI_TEXT_ANALYZE_API_KEY,
        "text_analyze_base_url": AI_TEXT_ANALYZE_BASE_URL,
        "text_analyze_model": AI_TEXT_ANALYZE_MODEL,
    },
    "sensor": {
        "save_image": SENSOR_SAVE_IMAGE,
        "save_audio": SENSOR_SAVE_AUDIO,
        "blacklist": [],
    },
    "device_config_defaults": {
        "ntp_server": DEVICE_CONFIG_DEFAULT_NTP_SERVER,
        "timezone_offset_sec": DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC,
        "moisture_threshold": DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD,
    },
    "discord": {
        "webhook_url": DISCORD_WEBHOOK_URL,
    },
}


""" Setting module
This module provides the settings for the device.

"""


class Setting:
    SETTING_FILE_PATH = os.path.expanduser("~/.ina-device-hub/config.json")

    def __init__(self, path=None):
        if path:
            self.SETTING_FILE_PATH = path
        self.settings = DEFAULT_SETTINGS
        self.load()

    def load(self):
        try:
            with open(self.SETTING_FILE_PATH) as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            pass

    def save(self):
        with open(self.SETTING_FILE_PATH, "w") as f:
            json.dump(self.settings, f)

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_work_dir(self):
        return WORK_DIR


@lru_cache(maxsize=1)
def setting():
    return Setting()
