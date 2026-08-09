import json
import os
import sys
import uuid
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock
from ina_device_hub.plant_calendar_prompt import DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


# device name
try:
    DEVICE_NAME = os.environ["HOSTNAME"]
except KeyError:
    DEVICE_NAME = "ina-device-hub"

HUB_HTTP_HOST = os.environ.get("HUB_HTTP_HOST", "0.0.0.0").strip() or "0.0.0.0"
HUB_HTTP_PORT = _int_env("HUB_HTTP_PORT", 39151)
HUB_HTTP_SERVER = os.environ.get("HUB_HTTP_SERVER", "flask").strip().lower() or "flask"
HUB_HTTP_THREADS = _int_env("HUB_HTTP_THREADS", 8)
HUB_AUTH_MODE = os.environ.get("HUB_AUTH_MODE", "local").strip().lower() or "local"
HUB_MAX_REQUEST_BYTES = _int_env("HUB_MAX_REQUEST_BYTES", 64 * 1024 * 1024)
FIRMWARE_MAX_UPLOAD_BYTES = _int_env("FIRMWARE_MAX_UPLOAD_BYTES", 16 * 1024 * 1024)

# work directory
try:
    WORK_DIR = os.environ["WORK_DIR"]
    WORK_DIR = os.path.expanduser(WORK_DIR)
except KeyError:
    WORK_DIR = os.path.expanduser("~/.ina-device-hub")

HUB_BACKUP_DIR = os.path.expanduser(os.environ.get("HUB_BACKUP_DIR", os.path.join(WORK_DIR, "backups")))
HUB_BACKUP_RETENTION = _int_env("HUB_BACKUP_RETENTION", 14)

if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)

# Turso settings. These belong to this Local Hub installation; Cloud Hub
# tenant routing and credentials are managed separately under hub-cloud.
try:
    TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
    TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]
except KeyError as e:
    sys.exit(f"Please set {e} in .env file")
TURSO_SYNC_INTERVAL = _int_env("TURSO_SYNC_INTERVAL", 600)
TURSO_SYNC_ON_WRITE = _bool_env("TURSO_SYNC_ON_WRITE", False)

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

# OTA firmware download settings
FIRMWARE_BASE_URL = os.environ.get("FIRMWARE_BASE_URL", "").strip()
FIRMWARE_HOSTNAME = os.environ.get("FIRMWARE_HOSTNAME", "").strip()
FIRMWARE_PORT = _int_env("FIRMWARE_PORT", HUB_HTTP_PORT)

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
INSTAGRAM_POST_SCHEDULE_START = os.environ.get(
    "INSTAGRAM_POST_SCHEDULE_START",
    os.environ.get("AI_AGENT_SCHEDULE_START", "09:01"),
).strip()
INSTAGRAM_WEATHER_FORECAST_URL = os.environ.get("INSTAGRAM_WEATHER_FORECAST_URL", WEATHER_FORECAST_URL).strip()
INSTAGRAM_WEATHER_AREA_NAME = os.environ.get("INSTAGRAM_WEATHER_AREA_NAME", WEATHER_AREA_NAME).strip()
INSTAGRAM_WEATHER_OFFICE_NAME = os.environ.get("INSTAGRAM_WEATHER_OFFICE_NAME", WEATHER_OFFICE_NAME).strip()
INSTAGRAM_WEATHER_FORECAST_TITLE = os.environ.get("INSTAGRAM_WEATHER_FORECAST_TITLE", WEATHER_FORECAST_TITLE).strip()

AI_ENABLED = bool("true" == os.environ.get("AI_ENABLED", "false").lower())
AI_IMAGE_ANALYZE_API_KEY = os.environ.get("AI_IMAGE_ANALYZE_API_KEY", "").strip()
AI_IMAGE_ANALYZE_BASE_URL = os.environ.get("AI_IMAGE_ANALYZE_BASE_URL", "").strip()
AI_IMAGE_ANALYZE_MODEL = os.environ.get("AI_IMAGE_ANALYZE_MODEL", "").strip()
AI_TEXT_ANALYZE_API_KEY = os.environ.get("AI_TEXT_ANALYZE_API_KEY", "").strip()
AI_TEXT_ANALYZE_BASE_URL = os.environ.get("AI_TEXT_ANALYZE_BASE_URL", "").strip()
AI_TEXT_ANALYZE_MODEL = os.environ.get("AI_TEXT_ANALYZE_MODEL", "").strip()
AI_PLANT_CALENDAR_WEB_KNOWLEDGE_ENABLED = _bool_env("AI_PLANT_CALENDAR_WEB_KNOWLEDGE_ENABLED", True)
AI_PLANT_CALENDAR_WEB_KNOWLEDGE_CACHE_DAYS = _int_env("AI_PLANT_CALENDAR_WEB_KNOWLEDGE_CACHE_DAYS", 30)

DEVICE_CONFIG_DEFAULT_NTP_SERVER = os.environ.get("DEVICE_CONFIG_DEFAULT_NTP_SERVER", DEVICE_NAME)
DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC = int(os.environ.get("DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC", "32400"))
DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD = int(os.environ.get("DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD", "35"))

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_ENABLED = _bool_env("DISCORD_ENABLED", True)
DISCORD_NOTIFY_MQTT_ACTIVITY = _bool_env("DISCORD_NOTIFY_MQTT_ACTIVITY", False)
DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS = _bool_env("DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS", True)
DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS = _int_env("DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS", 300)
DISCORD_NOTIFY_NEW_DEVICE = _bool_env("DISCORD_NOTIFY_NEW_DEVICE", True)
DISCORD_NOTIFY_DEVICE_OFFLINE = _bool_env("DISCORD_NOTIFY_DEVICE_OFFLINE", True)
DISCORD_NOTIFY_WATERING_MISSING = _bool_env("DISCORD_NOTIFY_WATERING_MISSING", True)
DISCORD_NOTIFY_SOIL_CALIBRATION_SUGGESTED = _bool_env("DISCORD_NOTIFY_SOIL_CALIBRATION_SUGGESTED", True)
DISCORD_NOTIFY_PLANT_TASKS = _bool_env("DISCORD_NOTIFY_PLANT_TASKS", True)
DISCORD_PLANT_TASK_NOTIFY_NEW = _bool_env("DISCORD_PLANT_TASK_NOTIFY_NEW", True)
DISCORD_PLANT_TASK_REMINDER_DAYS_BEFORE = _int_env("DISCORD_PLANT_TASK_REMINDER_DAYS_BEFORE", 7)
DISCORD_PLANT_TASK_NOTIFY_ON_START_DAY = _bool_env("DISCORD_PLANT_TASK_NOTIFY_ON_START_DAY", True)
DISCORD_PLANT_TASK_NOTIFY_DURING_WINDOW = _bool_env("DISCORD_PLANT_TASK_NOTIFY_DURING_WINDOW", True)
HEALTH_MONITOR_ENABLED = _bool_env("HEALTH_MONITOR_ENABLED", False)
HEALTH_MONITOR_INTERVAL_SECONDS = _int_env("HEALTH_MONITOR_INTERVAL_SECONDS", 1800)
HEALTH_DEVICE_OFFLINE_AFTER_HOURS = _int_env("HEALTH_DEVICE_OFFLINE_AFTER_HOURS", 12)
HEALTH_WATERING_MISSING_AFTER_DAYS = _int_env("HEALTH_WATERING_MISSING_AFTER_DAYS", 2)

SWITCHBOT_OPEN_TOKEN = os.environ.get("SWITCHBOT_OPEN_TOKEN", "").strip()
SWITCHBOT_SECRET_KEY = os.environ.get("SWITCHBOT_SECRET_KEY", "").strip()
SWITCHBOT_BASE_URL = os.environ.get("SWITCHBOT_BASE_URL", "https://api.switch-bot.com").strip()
SWITCHBOT_TIMEOUT_SECONDS = _int_env("SWITCHBOT_TIMEOUT_SECONDS", 20)
SWITCHBOT_PLUG_MINI_DEVICE_ID = os.environ.get("SWITCHBOT_PLUG_MINI_DEVICE_ID", "").strip()


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
    # Legacy object-key namespace retained for stored-path compatibility. A
    # Local Hub never accepts this value as a tenant/database routing choice.
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "device_id": get_device_id(),
    "device_name": DEVICE_NAME,
    "http": {
        "host": HUB_HTTP_HOST,
        "port": HUB_HTTP_PORT,
        "server": HUB_HTTP_SERVER,
        "threads": HUB_HTTP_THREADS,
        "max_request_bytes": HUB_MAX_REQUEST_BYTES,
    },
    "security": {
        "auth_mode": HUB_AUTH_MODE,
        "firmware_max_upload_bytes": FIRMWARE_MAX_UPLOAD_BYTES,
    },
    "backup": {
        "directory": HUB_BACKUP_DIR,
        "retention": HUB_BACKUP_RETENTION,
    },
    "turso": {
        "database_url": TURSO_DATABASE_URL,
        "auth_token": TURSO_AUTH_TOKEN,
        "local_db_path": os.path.join(os.path.expanduser(WORK_DIR), "ina.db"),
        "sync_interval": TURSO_SYNC_INTERVAL,
        "sync_on_write": TURSO_SYNC_ON_WRITE,
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
    "firmware": {
        "base_url": FIRMWARE_BASE_URL,
        "hostname": FIRMWARE_HOSTNAME,
        "port": FIRMWARE_PORT,
        "root_dir": os.path.join(os.path.expanduser(WORK_DIR), "firmware"),
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
        "post_schedule_start": INSTAGRAM_POST_SCHEDULE_START,
        "account_id": "",
        "account_username": "",
        "account_profile_updated_at": "",
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
        "image_analyze_api_key": AI_IMAGE_ANALYZE_API_KEY,
        "image_analyze_base_url": AI_IMAGE_ANALYZE_BASE_URL,
        "image_analyze_model": AI_IMAGE_ANALYZE_MODEL,
        "image_analyze_temperature_mode": "auto",
        "image_analyze_temperature": 1.0,
        "image_analyze_reasoning_effort": "",
        "text_analyze_api_key": AI_TEXT_ANALYZE_API_KEY,
        "text_analyze_base_url": AI_TEXT_ANALYZE_BASE_URL,
        "text_analyze_model": AI_TEXT_ANALYZE_MODEL,
        "text_analyze_temperature_mode": "auto",
        "text_analyze_temperature": 1.0,
        "text_analyze_reasoning_effort": "",
        "plant_calendar_web_knowledge_enabled": AI_PLANT_CALENDAR_WEB_KNOWLEDGE_ENABLED,
        "plant_calendar_web_knowledge_cache_days": AI_PLANT_CALENDAR_WEB_KNOWLEDGE_CACHE_DAYS,
        "plant_calendar_prompt_template": DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE,
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
        "enabled": DISCORD_ENABLED,
        "notify_mqtt_activity": DISCORD_NOTIFY_MQTT_ACTIVITY,
        "notify_operations_security_alerts": DISCORD_NOTIFY_OPERATIONS_SECURITY_ALERTS,
        "security_alert_cooldown_sec": DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS,
        "notify_new_device": DISCORD_NOTIFY_NEW_DEVICE,
        "notify_device_offline": DISCORD_NOTIFY_DEVICE_OFFLINE,
        "notify_watering_missing": DISCORD_NOTIFY_WATERING_MISSING,
        "notify_soil_calibration_suggested": DISCORD_NOTIFY_SOIL_CALIBRATION_SUGGESTED,
        "notify_plant_tasks": DISCORD_NOTIFY_PLANT_TASKS,
        "plant_task_notify_new": DISCORD_PLANT_TASK_NOTIFY_NEW,
        "plant_task_reminder_days_before": DISCORD_PLANT_TASK_REMINDER_DAYS_BEFORE,
        "plant_task_notify_on_start_day": DISCORD_PLANT_TASK_NOTIFY_ON_START_DAY,
        "plant_task_notify_during_window": DISCORD_PLANT_TASK_NOTIFY_DURING_WINDOW,
    },
    "health_monitor": {
        "enabled": HEALTH_MONITOR_ENABLED,
        "interval_seconds": HEALTH_MONITOR_INTERVAL_SECONDS,
        "device_offline_after_hours": HEALTH_DEVICE_OFFLINE_AFTER_HOURS,
        "watering_missing_after_days": HEALTH_WATERING_MISSING_AFTER_DAYS,
    },
    "switchbot": {
        "open_token": SWITCHBOT_OPEN_TOKEN,
        "secret_key": SWITCHBOT_SECRET_KEY,
        "base_url": SWITCHBOT_BASE_URL,
        "timeout_seconds": SWITCHBOT_TIMEOUT_SECONDS,
        "plug_mini_device_id": SWITCHBOT_PLUG_MINI_DEVICE_ID,
    },
}


RUNTIME_SETTING_FIELDS = {
    "ai": {
        "enabled",
        "image_analyze_base_url",
        "image_analyze_model",
        "image_analyze_temperature_mode",
        "image_analyze_temperature",
        "image_analyze_reasoning_effort",
        "text_analyze_base_url",
        "text_analyze_model",
        "text_analyze_temperature_mode",
        "text_analyze_temperature",
        "text_analyze_reasoning_effort",
        "plant_calendar_web_knowledge_enabled",
        "plant_calendar_web_knowledge_cache_days",
        "plant_calendar_prompt_template",
    },
    "instagram": {
        "post_schedule_start",
        "camera_id",
        "plant_position_prompt",
        "account_id",
        "account_username",
        "account_profile_updated_at",
    },
    "discord": {
        "enabled",
        "notify_mqtt_activity",
        "notify_operations_security_alerts",
        "security_alert_cooldown_sec",
        "notify_new_device",
        "notify_device_offline",
        "notify_watering_missing",
        "notify_soil_calibration_suggested",
        "notify_plant_tasks",
        "plant_task_notify_new",
        "plant_task_reminder_days_before",
        "plant_task_notify_on_start_day",
        "plant_task_notify_during_window",
    },
}

RUNTIME_SECRET_FIELDS = {
    "ai": {
        "image_analyze_api_key",
        "text_analyze_api_key",
    },
}


def _runtime_settings_from(values):
    if not isinstance(values, dict):
        return {}
    runtime_settings = {}
    for section, allowed_fields in RUNTIME_SETTING_FIELDS.items():
        source = values.get(section)
        if not isinstance(source, dict):
            continue
        runtime_settings[section] = {key: source[key] for key in allowed_fields if key in source}
    legacy_ai = values.get("ai")
    instagram = runtime_settings.setdefault("instagram", {})
    if "post_schedule_start" not in instagram and isinstance(legacy_ai, dict) and "agent_schedule_start" in legacy_ai:
        instagram["post_schedule_start"] = legacy_ai["agent_schedule_start"]
    if not instagram:
        runtime_settings.pop("instagram", None)
    return runtime_settings


def _runtime_secrets_from(values):
    if not isinstance(values, dict):
        return {}
    runtime_secrets = {}
    for section, allowed_fields in RUNTIME_SECRET_FIELDS.items():
        source = values.get(section)
        if not isinstance(source, dict):
            continue
        selected = {key: str(source[key]) for key in allowed_fields if key in source}
        if selected:
            runtime_secrets[section] = selected
    return runtime_secrets


def _merge_settings(base, overrides):
    merged = deepcopy(base)
    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section].update(values)
        else:
            merged[section] = values
    return merged


""" Setting module
This module provides the settings for the device.

"""


class Setting:
    SETTING_FILE_PATH = os.path.join(WORK_DIR, "config.json")
    SECRET_FILE_PATH = os.path.join(WORK_DIR, "runtime-secrets.json")

    def __init__(self, path=None, secret_path=None):
        if path:
            self.SETTING_FILE_PATH = str(path)
            self.SECRET_FILE_PATH = str(Path(path).with_name("runtime-secrets.json"))
        if secret_path:
            self.SECRET_FILE_PATH = str(secret_path)
        self.settings = deepcopy(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        with repository_file_lock(self.SETTING_FILE_PATH):
            self._load_unlocked()

    def _load_unlocked(self):
        runtime_settings = {}
        try:
            with open(self.SETTING_FILE_PATH) as f:
                persisted = json.load(f)
            runtime_settings = _runtime_settings_from(persisted)
            normalized = {"schema_version": 1, **runtime_settings}
            if persisted != normalized:
                self.settings = _merge_settings(DEFAULT_SETTINGS, runtime_settings)
                self._save_unlocked()
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self.settings = _merge_settings(DEFAULT_SETTINGS, runtime_settings)
        self.settings = _merge_settings(self.settings, self._load_secret_overrides())

    def _load_secret_overrides(self):
        try:
            with open(self.SECRET_FILE_PATH, encoding="utf-8") as file:
                return _runtime_secrets_from(json.load(file))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self):
        with repository_file_lock(self.SETTING_FILE_PATH):
            self._save_unlocked()

    def _save_unlocked(self):
        setting_path = Path(self.SETTING_FILE_PATH)
        setting_path.parent.mkdir(parents=True, exist_ok=True)
        persisted = {
            "schema_version": 1,
            **_runtime_settings_from(self.settings),
        }
        atomic_write_json(str(setting_path), persisted)
        os.chmod(setting_path, 0o600)

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        if key not in RUNTIME_SETTING_FIELDS:
            raise ValueError(f"{key} is not a runtime-editable setting")
        with repository_file_lock(self.SETTING_FILE_PATH):
            self._load_unlocked()
            runtime_value = _runtime_settings_from({key: value}).get(key, {})
            current = self.settings.get(key) if isinstance(self.settings.get(key), dict) else {}
            self.settings[key] = {**current, **runtime_value}
            self._save_unlocked()

    def set_secret(self, section, key, value):
        if section not in RUNTIME_SECRET_FIELDS or key not in RUNTIME_SECRET_FIELDS[section]:
            raise ValueError(f"{section}.{key} is not a runtime-editable secret")
        value = str(value)
        with repository_file_lock(self.SECRET_FILE_PATH):
            secret_values = self._load_secret_overrides()
            secret_values.setdefault(section, {})[key] = value
            secret_path = Path(self.SECRET_FILE_PATH)
            secret_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                str(secret_path),
                {"schema_version": 1, **_runtime_secrets_from(secret_values)},
            )
            os.chmod(secret_path, 0o600)
        self.settings = _merge_settings(self.settings, secret_values)

    def secret_configured(self, section, key):
        if section not in RUNTIME_SECRET_FIELDS or key not in RUNTIME_SECRET_FIELDS[section]:
            raise ValueError(f"{section}.{key} is not a runtime-editable secret")
        return bool(self.settings.get(section, {}).get(key))

    def runtime_settings(self):
        return _runtime_settings_from(self.settings)

    def get_work_dir(self):
        return WORK_DIR


@lru_cache(maxsize=1)
def setting():
    return Setting()
