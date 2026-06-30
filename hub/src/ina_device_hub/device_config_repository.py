import copy
import json
import os
from collections import deque
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.setting import setting


def _utc_now():
    return datetime.now(UTC).isoformat()


DEVICE_STATES = {"pending", "active", "disabled", "retired"}
MAX_STATUS_HISTORY = 100


class DeviceConfigValidationError(ValueError):
    pass


class DeviceRecordValidationError(ValueError):
    pass


class DeviceConfigRepository:
    device_config_path = os.path.join(setting().get_work_dir(), ".device_configs.json")

    def __init__(self):
        self.device_configs = {}
        self.load()

    def load(self):
        if not os.path.exists(self.device_config_path):
            with open(self.device_config_path, "w", encoding="utf-8") as file:
                json.dump({}, file)
        try:
            with open(self.device_config_path, encoding="utf-8") as file:
                self.device_configs = json.load(file)
        except FileNotFoundError:
            self.device_configs = {}

    def save(self):
        with open(self.device_config_path, "w", encoding="utf-8") as file:
            json.dump(self.device_configs, file, ensure_ascii=True, indent=2)

    def get(self, device_id: str):
        record = self.device_configs.get(device_id)
        return copy.deepcopy(_normalize_device_record(device_id, record)) if record else None

    def get_all(self):
        return {device_id: copy.deepcopy(_normalize_device_record(device_id, record)) for device_id, record in self.device_configs.items()}

    def upsert(self, device_id: str, config: dict):
        validated = validate_device_config(config)
        record = self._get_or_new_record(device_id)
        record["config"] = validated
        record["runtime_config"] = validated
        record["updated_at"] = _utc_now()
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def get_or_create(self, device_id: str, default_config: dict):
        record = self.get(device_id)
        if record is not None:
            return record
        now = _utc_now()
        validated = validate_device_config(default_config)
        record = _new_device_record(device_id, now)
        record["config"] = validated
        record["runtime_config"] = validated
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def record_config_request(self, device_id: str, default_config: dict):
        record = self.get_or_create(device_id, default_config)
        now = _utc_now()
        record["last_seen_at"] = now
        record["last_config_request_at"] = now
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def record_config_reply(self, device_id: str):
        record = self._get_or_new_record(device_id)
        now = _utc_now()
        record["last_config_reply_at"] = now
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def record_status(self, device_id: str, status: dict):
        record = self._get_or_new_record(device_id)
        now = _utc_now()
        record["last_seen_at"] = now
        record["last_status_at"] = now
        record["last_status"] = copy.deepcopy(status)
        status_history = deque(record.get("status_history", []), maxlen=MAX_STATUS_HISTORY)
        status_history.append({"received_at": now, "payload": copy.deepcopy(status)})
        record["status_history"] = list(status_history)
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def update_metadata(self, device_id: str, metadata: dict):
        record = self._get_or_new_record(device_id)
        for key in ("name", "location", "memo"):
            if key in metadata:
                value = metadata[key]
                if value is not None and not isinstance(value, str):
                    raise DeviceRecordValidationError(f"{key} must be a string or null")
                record[key] = value
        record["updated_at"] = _utc_now()
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def set_state(self, device_id: str, state: str, approved_by: str | None = None):
        if state not in DEVICE_STATES:
            raise DeviceRecordValidationError(f"state must be one of: {', '.join(sorted(DEVICE_STATES))}")

        record = self._get_or_new_record(device_id)
        now = _utc_now()
        record["state"] = state
        record["updated_at"] = now
        if state == "active":
            record["approved_at"] = now
            record["approved_by"] = approved_by
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def list_statuses(self, device_id: str, limit: int = 100):
        record = self.get(device_id)
        if record is None:
            return []
        statuses = record.get("status_history", [])
        return copy.deepcopy(statuses[-limit:])

    def _get_or_new_record(self, device_id: str):
        record = self.device_configs.get(device_id)
        if record is None:
            record = _new_device_record(device_id, _utc_now())
        return _normalize_device_record(device_id, record)


def validate_device_config(config: dict):
    if not isinstance(config, dict):
        raise DeviceConfigValidationError("config must be an object")

    required_keys = {
        "ntp_server",
        "timezone_offset_sec",
        "moisture_threshold",
        "schedules",
    }
    missing_keys = sorted(required_keys - set(config))
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise DeviceConfigValidationError(f"missing required keys: {missing}")

    ntp_server = config["ntp_server"]
    if not isinstance(ntp_server, str) or not ntp_server.strip():
        raise DeviceConfigValidationError("ntp_server must be a non-empty string")

    timezone_offset_sec = config["timezone_offset_sec"]
    if not isinstance(timezone_offset_sec, int):
        raise DeviceConfigValidationError("timezone_offset_sec must be an integer")

    moisture_threshold = config["moisture_threshold"]
    if not isinstance(moisture_threshold, int) or not 0 <= moisture_threshold <= 100:
        raise DeviceConfigValidationError("moisture_threshold must be between 0 and 100")

    force_watering = config.get("force_watering", False)
    if not isinstance(force_watering, bool):
        raise DeviceConfigValidationError("force_watering must be a boolean")

    schedules = config["schedules"]
    if not isinstance(schedules, list):
        raise DeviceConfigValidationError("schedules must be an array")
    if not 1 <= len(schedules) <= 8:
        raise DeviceConfigValidationError("schedules must contain 1 to 8 entries")

    normalized_schedules = []
    for index, schedule in enumerate(schedules):
        if not isinstance(schedule, dict):
            raise DeviceConfigValidationError(f"schedules[{index}] must be an object")

        required_schedule_keys = {"hour", "minute", "duration_sec", "channel_mask"}
        missing_schedule_keys = sorted(required_schedule_keys - set(schedule))
        if missing_schedule_keys:
            missing = ", ".join(missing_schedule_keys)
            raise DeviceConfigValidationError(f"schedules[{index}] missing required keys: {missing}")

        hour = schedule["hour"]
        minute = schedule["minute"]
        duration_sec = schedule["duration_sec"]
        channel_mask = schedule["channel_mask"]

        if not isinstance(hour, int) or not 0 <= hour <= 23:
            raise DeviceConfigValidationError(f"schedules[{index}].hour must be 0-23")
        if not isinstance(minute, int) or not 0 <= minute <= 59:
            raise DeviceConfigValidationError(f"schedules[{index}].minute must be 0-59")
        if not isinstance(duration_sec, int) or duration_sec <= 0:
            raise DeviceConfigValidationError(f"schedules[{index}].duration_sec must be > 0")
        if not isinstance(channel_mask, int) or channel_mask <= 0:
            raise DeviceConfigValidationError(f"schedules[{index}].channel_mask must be > 0")

        normalized_schedules.append(
            {
                "hour": hour,
                "minute": minute,
                "duration_sec": duration_sec,
                "channel_mask": channel_mask,
            }
        )

    normalized = {
        "ntp_server": ntp_server.strip(),
        "timezone_offset_sec": timezone_offset_sec,
        "moisture_threshold": moisture_threshold,
        "force_watering": force_watering,
        "schedules": normalized_schedules,
    }
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) >= 512:
        raise DeviceConfigValidationError("config payload must be less than 512 bytes")
    return normalized


def _new_device_record(device_id: str, now: str):
    return {
        "device_id": device_id,
        "state": "pending",
        "name": None,
        "location": None,
        "memo": None,
        "config": None,
        "runtime_config": None,
        "first_seen_at": now,
        "last_seen_at": None,
        "last_config_request_at": None,
        "last_config_reply_at": None,
        "last_status_at": None,
        "last_status": None,
        "status_history": [],
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
        "approved_by": None,
    }


def _normalize_device_record(device_id: str, record: dict):
    now = record.get("updated_at") or record.get("created_at") or _utc_now()
    normalized = _new_device_record(device_id, now)
    normalized.update(record)
    normalized["device_id"] = device_id
    normalized["state"] = normalized.get("state") if normalized.get("state") in DEVICE_STATES else "pending"

    config = normalized.get("runtime_config") or normalized.get("config")
    normalized["config"] = config
    normalized["runtime_config"] = config
    normalized["status_history"] = list(normalized.get("status_history") or [])[-MAX_STATUS_HISTORY:]
    return normalized


@lru_cache(maxsize=1)
def device_config_repository():
    return DeviceConfigRepository()
