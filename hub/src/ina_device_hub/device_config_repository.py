import copy
import json
import os
import re
from collections import deque
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.setting import setting


def _utc_now():
    return datetime.now(UTC).isoformat()


DEVICE_STATES = {"pending", "active", "disabled", "retired"}
MAX_STATUS_HISTORY = 2000
MAX_OTA_STATUS_HISTORY = 100
DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")


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
        _apply_firmware_metadata(record, status)
        _apply_device_kind(record, status)
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

    def set_firmware_target(self, device_id: str, target_firmware_version: str | None):
        if target_firmware_version is not None:
            if not isinstance(target_firmware_version, str) or not target_firmware_version.strip():
                raise DeviceRecordValidationError("target_firmware_version must be a non-empty string or null")
            target_firmware_version = target_firmware_version.strip()

        record = self._get_or_new_record(device_id)
        record["target_firmware_version"] = target_firmware_version
        record["updated_at"] = _utc_now()
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def record_ota_request(self, device_id: str, request_payload: dict):
        record = self._get_or_new_record(device_id)
        now = _utc_now()
        record["last_seen_at"] = now
        record["last_ota_request_at"] = now
        _apply_device_kind(record, request_payload)
        _apply_firmware_metadata(record, request_payload)
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def record_ota_status(self, device_id: str, status: dict):
        record = self._get_or_new_record(device_id)
        now = _utc_now()
        state = status.get("state")
        record["last_seen_at"] = now
        record["last_ota_status_at"] = now
        record["ota_update_id"] = status.get("update_id") or record.get("ota_update_id")
        already_running = (
            state == "skipped"
            and status.get("error") == "already_running"
            and isinstance(status.get("to_version"), str)
            and status.get("firmware_version") == status.get("to_version")
        )
        record["ota_state"] = "confirmed" if already_running else state or record.get("ota_state")
        record["ota_error"] = None if already_running else status.get("error")
        _apply_device_kind(record, status)
        _apply_firmware_metadata(record, status)
        if state == "started":
            record["ota_attempt_count"] = int(record.get("ota_attempt_count") or 0) + 1
            record["ota_last_attempt_at"] = now
        if state == "confirmed" or already_running:
            record["ota_confirmed_at"] = now
            to_version = status.get("to_version")
            reported_version = status.get("firmware_version")
            if isinstance(to_version, str) and to_version and reported_version == to_version:
                record["firmware_version"] = to_version
            elif isinstance(to_version, str) and to_version:
                record["ota_error"] = "confirmed_version_mismatch"
        ota_status_history = deque(record.get("ota_status_history", []), maxlen=MAX_OTA_STATUS_HISTORY)
        ota_status_history.append({"received_at": now, "payload": copy.deepcopy(status)})
        record["ota_status_history"] = list(ota_status_history)
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    def list_statuses(self, device_id: str, limit: int = 100):
        record = self.get(device_id)
        if record is None:
            return []
        statuses = record.get("status_history", [])
        return copy.deepcopy(statuses[-limit:])

    def list_ota_statuses(self, device_id: str, limit: int = 100):
        record = self.get(device_id)
        if record is None:
            return []
        statuses = record.get("ota_status_history", [])
        return copy.deepcopy(statuses[-limit:])

    def _get_or_new_record(self, device_id: str):
        record = self.device_configs.get(device_id)
        if record is None:
            record = _new_device_record(device_id, _utc_now())
        return _normalize_device_record(device_id, record)


def _is_yyyy_mm_dd(value: str):
    parts = value.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return False
    year, month, day = (int(part) for part in parts)
    return 1970 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31


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

    debug_log_on_wake = config.get("debug_log_on_wake", False)
    if not isinstance(debug_log_on_wake, bool):
        raise DeviceConfigValidationError("debug_log_on_wake must be a boolean")

    ota_check_interval_sec = config.get("ota_check_interval_sec", 21600)
    if not isinstance(ota_check_interval_sec, int) or not 3600 <= ota_check_interval_sec <= 86400:
        raise DeviceConfigValidationError("ota_check_interval_sec must be between 3600 and 86400")

    def _optional_bool(parent: dict, key: str, default: bool = False, label: str | None = None):
        value = parent.get(key, default)
        if not isinstance(value, bool):
            raise DeviceConfigValidationError(f"{label or key} must be a boolean")
        return value

    def _optional_int(parent: dict, key: str, default: int, min_value: int, max_value: int, label: str | None = None):
        value = parent.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise DeviceConfigValidationError(f"{label or key} must be an integer")
        if not min_value <= value <= max_value:
            raise DeviceConfigValidationError(f"{label or key} must be between {min_value} and {max_value}")
        return value

    watering_pattern = config.get("watering_pattern", {"enabled": False})
    if not isinstance(watering_pattern, dict):
        raise DeviceConfigValidationError("watering_pattern must be an object")
    normalized_watering_pattern = {
        "enabled": _optional_bool(watering_pattern, "enabled", False, "watering_pattern.enabled"),
        "on_sec": _optional_int(watering_pattern, "on_sec", 0, 0, 3600, "watering_pattern.on_sec"),
        "off_sec": _optional_int(watering_pattern, "off_sec", 0, 0, 3600, "watering_pattern.off_sec"),
        "repeat_count": _optional_int(watering_pattern, "repeat_count", 0, 0, 20, "watering_pattern.repeat_count"),
    }
    if normalized_watering_pattern["enabled"] and (
        normalized_watering_pattern["on_sec"] <= 0 or normalized_watering_pattern["repeat_count"] <= 0
    ):
        raise DeviceConfigValidationError("enabled watering_pattern requires on_sec and repeat_count")

    soil_calibration = config.get("soil_calibration", {})
    if not isinstance(soil_calibration, dict):
        raise DeviceConfigValidationError("soil_calibration must be an object")
    normalized_soil_calibration = {
        "auto_mode_enabled": _optional_bool(soil_calibration, "auto_mode_enabled", False, "soil_calibration.auto_mode_enabled"),
        "apply_auto_calibration": _optional_bool(soil_calibration, "apply_auto_calibration", False, "soil_calibration.apply_auto_calibration"),
        "drift_check_enabled": _optional_bool(soil_calibration, "drift_check_enabled", False, "soil_calibration.drift_check_enabled"),
        "dry_raw": _optional_int(soil_calibration, "dry_raw", 1895, 1, 4095, "soil_calibration.dry_raw"),
        "wet_raw": _optional_int(soil_calibration, "wet_raw", 1285, 0, 4094, "soil_calibration.wet_raw"),
        "min_delta_raw": _optional_int(soil_calibration, "min_delta_raw", 80, 10, 2000, "soil_calibration.min_delta_raw"),
        "drift_tolerance_raw": _optional_int(soil_calibration, "drift_tolerance_raw", 120, 10, 2000, "soil_calibration.drift_tolerance_raw"),
    }
    if normalized_soil_calibration["dry_raw"] <= normalized_soil_calibration["wet_raw"]:
        raise DeviceConfigValidationError("soil_calibration.dry_raw must be greater than wet_raw")

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

        frequency = schedule.get("frequency", {"mode": "daily"})
        if not isinstance(frequency, dict):
            raise DeviceConfigValidationError(f"schedules[{index}].frequency must be an object")
        mode = frequency.get("mode", "daily")
        if mode not in {"daily", "interval", "weekdays"}:
            raise DeviceConfigValidationError(f"schedules[{index}].frequency.mode must be daily, interval, or weekdays")
        normalized_frequency = {"mode": mode}
        if mode == "interval":
            interval_days = frequency.get("interval_days", 1)
            if not isinstance(interval_days, int) or isinstance(interval_days, bool) or not 1 <= interval_days <= 31:
                raise DeviceConfigValidationError(f"schedules[{index}].frequency.interval_days must be between 1 and 31")
            start_date = frequency.get("start_date", "1970-01-01")
            if not isinstance(start_date, str) or not _is_yyyy_mm_dd(start_date):
                raise DeviceConfigValidationError(f"schedules[{index}].frequency.start_date must be YYYY-MM-DD")
            normalized_frequency["interval_days"] = interval_days
            normalized_frequency["start_date"] = start_date
        elif mode == "weekdays":
            weekdays = frequency.get("weekdays", [])
            if not isinstance(weekdays, list) or not weekdays:
                raise DeviceConfigValidationError(f"schedules[{index}].frequency.weekdays must contain at least one weekday")
            normalized_weekdays = []
            for weekday in weekdays:
                if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
                    raise DeviceConfigValidationError(f"schedules[{index}].frequency.weekdays values must be 0-6")
                if weekday not in normalized_weekdays:
                    normalized_weekdays.append(weekday)
            normalized_frequency["weekdays"] = sorted(normalized_weekdays)
            normalized_frequency["weekdays_mask"] = sum(1 << weekday for weekday in normalized_frequency["weekdays"])

        normalized_schedules.append(
            {
                "hour": hour,
                "minute": minute,
                "duration_sec": duration_sec,
                "channel_mask": channel_mask,
                "frequency": normalized_frequency,
            }
        )

    normalized = {
        "ntp_server": ntp_server.strip(),
        "timezone_offset_sec": timezone_offset_sec,
        "moisture_threshold": moisture_threshold,
        "force_watering": force_watering,
        "debug_log_on_wake": debug_log_on_wake,
        "ota_check_interval_sec": ota_check_interval_sec,
        "watering_pattern": normalized_watering_pattern,
        "soil_calibration": normalized_soil_calibration,
        "schedules": normalized_schedules,
    }
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) >= 2048:
        raise DeviceConfigValidationError("config payload must be less than 2048 bytes")
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
        "device_kind": None,
        "first_seen_at": now,
        "last_seen_at": None,
        "last_config_request_at": None,
        "last_config_reply_at": None,
        "last_status_at": None,
        "last_status": None,
        "status_history": [],
        "firmware_version": None,
        "firmware_build_id": None,
        "target_firmware_version": None,
        "ota_update_id": None,
        "ota_state": None,
        "ota_error": None,
        "ota_attempt_count": 0,
        "ota_last_attempt_at": None,
        "ota_confirmed_at": None,
        "last_ota_request_at": None,
        "last_ota_status_at": None,
        "ota_status_history": [],
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
    normalized["ota_status_history"] = list(normalized.get("ota_status_history") or [])[-MAX_OTA_STATUS_HISTORY:]
    return normalized


def _apply_firmware_metadata(record: dict, payload: dict):
    firmware_version = payload.get("firmware_version")
    if isinstance(firmware_version, str) and firmware_version:
        record["firmware_version"] = firmware_version

    firmware_build_id = payload.get("firmware_build_id")
    if isinstance(firmware_build_id, str) and firmware_build_id:
        record["firmware_build_id"] = firmware_build_id


def _apply_device_kind(record: dict, payload: dict):
    device_kind = payload.get("device_kind")
    if isinstance(device_kind, str) and DEVICE_KIND_RE.match(device_kind) and record.get("device_kind") in (None, device_kind):
        record["device_kind"] = device_kind


@lru_cache(maxsize=1)
def device_config_repository():
    return DeviceConfigRepository()
