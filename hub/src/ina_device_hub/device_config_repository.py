import copy
import json
import os
import re
from collections import deque
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.json_repository_io import atomic_write_json, serialized_repository_write
from ina_device_hub.setting import setting


def _utc_now():
    return datetime.now(UTC).isoformat()


DEVICE_STATES = {"pending", "active", "disabled", "retired"}
DEVICE_STATE_TRANSITIONS = {
    "pending": {"active", "retired"},
    "active": {"disabled"},
    "disabled": {"active", "retired"},
    "retired": set(),
}
MAX_STATUS_HISTORY = 2000
MAX_OTA_STATUS_HISTORY = 100
DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")
MOSFET_SWITCH_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class DeviceConfigValidationError(ValueError):
    pass


class DeviceRecordValidationError(ValueError):
    pass


class DeviceStateConflictError(DeviceRecordValidationError):
    pass


class DeviceConfigRepository:
    device_config_path = os.path.join(setting().get_work_dir(), ".device_configs.json")

    def __init__(self):
        self.device_configs = {}
        self.load()

    def load(self):
        if not os.path.exists(self.device_config_path):
            atomic_write_json(self.device_config_path, {})
        try:
            with open(self.device_config_path, encoding="utf-8") as file:
                self.device_configs = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.device_configs = {}

    def save(self):
        atomic_write_json(self.device_config_path, self.device_configs)

    def get(self, device_id: str):
        record = self.device_configs.get(device_id)
        return copy.deepcopy(_normalize_device_record(device_id, record)) if record else None

    def get_all(self):
        return {device_id: copy.deepcopy(_normalize_device_record(device_id, record)) for device_id, record in self.device_configs.items()}

    @serialized_repository_write("device_config_path")
    def delete(self, device_id: str):
        record = self.device_configs.pop(device_id, None)
        if record is None:
            return None
        self.save()
        return copy.deepcopy(_normalize_device_record(device_id, record))

    @serialized_repository_write("device_config_path")
    def upsert(self, device_id: str, config: dict):
        validated = validate_device_config(config)
        record = self._get_or_new_record(device_id)
        if record.get("state") == "retired":
            raise DeviceStateConflictError("retired devices are read-only")
        record["config"] = validated
        record["runtime_config"] = validated
        record["updated_at"] = _utc_now()
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("device_config_path")
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

    @serialized_repository_write("device_config_path")
    def record_config_request(self, device_id: str, default_config: dict):
        record = self.get_or_create(device_id, default_config)
        now = _utc_now()
        record["last_seen_at"] = now
        record["last_config_request_at"] = now
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("device_config_path")
    def record_config_reply(self, device_id: str):
        record = self._get_or_new_record(device_id)
        now = _utc_now()
        record["last_config_reply_at"] = now
        record["updated_at"] = now
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("device_config_path")
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

    @serialized_repository_write("device_config_path")
    def update_metadata(self, device_id: str, metadata: dict):
        record = self._get_or_new_record(device_id)
        if record.get("state") == "retired":
            raise DeviceStateConflictError("retired devices are read-only")
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

    @serialized_repository_write("device_config_path")
    def set_state(self, device_id: str, state: str, approved_by: str | None = None):
        if state not in DEVICE_STATES:
            raise DeviceRecordValidationError(f"state must be one of: {', '.join(sorted(DEVICE_STATES))}")

        record = self._get_or_new_record(device_id)
        current_state = record.get("state", "pending")
        if state == current_state:
            raise DeviceStateConflictError(f"device is already {state}")
        if state not in DEVICE_STATE_TRANSITIONS[current_state]:
            raise DeviceStateConflictError(f"device state cannot change from {current_state} to {state}")
        now = _utc_now()
        record["state"] = state
        record["updated_at"] = now
        if state == "active":
            record["approved_at"] = now
            record["approved_by"] = approved_by
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("device_config_path")
    def set_firmware_target(self, device_id: str, target_firmware_version: str | None):
        if target_firmware_version is not None:
            if not isinstance(target_firmware_version, str) or not target_firmware_version.strip():
                raise DeviceRecordValidationError("target_firmware_version must be a non-empty string or null")
            target_firmware_version = target_firmware_version.strip()

        record = self._get_or_new_record(device_id)
        if record.get("state") == "retired":
            raise DeviceStateConflictError("retired devices are read-only")
        record["target_firmware_version"] = target_firmware_version
        record["updated_at"] = _utc_now()
        self.device_configs[device_id] = record
        self.save()
        return copy.deepcopy(record)

    @serialized_repository_write("device_config_path")
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

    @serialized_repository_write("device_config_path")
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


def validate_device_config(config: dict):  # noqa: PLR0915
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

    sleep_sec = config.get("sleep_sec", 300)
    if not isinstance(sleep_sec, int) or isinstance(sleep_sec, bool) or not 60 <= sleep_sec <= 86400:
        raise DeviceConfigValidationError("sleep_sec must be between 60 and 86400")

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

    def _optional_float(parent: dict, key: str, default: float, min_value: float, max_value: float, label: str | None = None):
        value = parent.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DeviceConfigValidationError(f"{label or key} must be a number")
        value = float(value)
        if not min_value <= value <= max_value:
            raise DeviceConfigValidationError(f"{label or key} must be between {min_value} and {max_value}")
        return value

    def _optional_str(parent: dict, key: str, default: str, label: str | None = None, max_length: int = 64):
        value = parent.get(key, default)
        if not isinstance(value, str):
            raise DeviceConfigValidationError(f"{label or key} must be a string")
        value = value.strip()
        if len(value) > max_length:
            raise DeviceConfigValidationError(f"{label or key} must be {max_length} characters or less")
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
    if normalized_watering_pattern["enabled"] and (normalized_watering_pattern["on_sec"] <= 0 or normalized_watering_pattern["repeat_count"] <= 0):
        raise DeviceConfigValidationError("enabled watering_pattern requires on_sec and repeat_count")

    soil_calibration = config.get("soil_calibration", {})
    if not isinstance(soil_calibration, dict):
        raise DeviceConfigValidationError("soil_calibration must be an object")
    soil_calibration_mode = _optional_str(soil_calibration, "mode", "normal", "soil_calibration.mode", 16)
    allowed_soil_calibration_modes = {"normal", "capture_dry", "capture_wet", "reset"}
    if soil_calibration_mode not in allowed_soil_calibration_modes:
        raise DeviceConfigValidationError("soil_calibration.mode must be normal, capture_dry, capture_wet, or reset")
    soil_calibration_request_id = _optional_str(soil_calibration, "request_id", "", "soil_calibration.request_id", 39)
    if soil_calibration_mode != "normal" and not soil_calibration_request_id:
        raise DeviceConfigValidationError("soil_calibration.request_id is required when mode is not normal")
    normalized_soil_calibration = {
        "mode": soil_calibration_mode,
        "request_id": soil_calibration_request_id,
        "calibrated": _optional_bool(soil_calibration, "calibrated", False, "soil_calibration.calibrated"),
        "auto_mode_enabled": _optional_bool(soil_calibration, "auto_mode_enabled", False, "soil_calibration.auto_mode_enabled"),
        "apply_auto_calibration": _optional_bool(soil_calibration, "apply_auto_calibration", False, "soil_calibration.apply_auto_calibration"),
        "drift_check_enabled": _optional_bool(soil_calibration, "drift_check_enabled", False, "soil_calibration.drift_check_enabled"),
        "dry_raw": _optional_int(soil_calibration, "dry_raw", 1895, 1, 4095, "soil_calibration.dry_raw"),
        "wet_raw": _optional_int(soil_calibration, "wet_raw", 1285, 0, 4094, "soil_calibration.wet_raw"),
        "min_delta_raw": _optional_int(soil_calibration, "min_delta_raw", 80, 10, 2000, "soil_calibration.min_delta_raw"),
        "drift_tolerance_raw": _optional_int(soil_calibration, "drift_tolerance_raw", 120, 10, 2000, "soil_calibration.drift_tolerance_raw"),
        "sample_count": _optional_int(soil_calibration, "sample_count", 20, 1, 100, "soil_calibration.sample_count"),
        "sample_interval_ms": _optional_int(soil_calibration, "sample_interval_ms", 40, 0, 1000, "soil_calibration.sample_interval_ms"),
    }
    if normalized_soil_calibration["dry_raw"] <= normalized_soil_calibration["wet_raw"]:
        raise DeviceConfigValidationError("soil_calibration.dry_raw must be greater than wet_raw")

    env_sensors = config.get("env_sensors", {})
    if not isinstance(env_sensors, dict):
        raise DeviceConfigValidationError("env_sensors must be an object")
    env_par = env_sensors.get("par", {})
    env_soil = env_sensors.get("soil", {})
    if not isinstance(env_par, dict):
        raise DeviceConfigValidationError("env_sensors.par must be an object")
    if not isinstance(env_soil, dict):
        raise DeviceConfigValidationError("env_sensors.soil must be an object")
    normalized_env_sensors = {
        "par": {
            "enabled": _optional_bool(env_par, "enabled", True, "env_sensors.par.enabled"),
            "modbus_slave_id": _optional_int(env_par, "modbus_slave_id", 1, 1, 247, "env_sensors.par.modbus_slave_id"),
            "modbus_function": _optional_int(env_par, "modbus_function", 3, 3, 4, "env_sensors.par.modbus_function"),
            "register": _optional_int(env_par, "register", 0, 0, 65535, "env_sensors.par.register"),
        },
        "soil": {
            "enabled": _optional_bool(env_soil, "enabled", False, "env_sensors.soil.enabled"),
            "modbus_slave_id": _optional_int(env_soil, "modbus_slave_id", 2, 1, 247, "env_sensors.soil.modbus_slave_id"),
            "modbus_function": _optional_int(env_soil, "modbus_function", 4, 3, 4, "env_sensors.soil.modbus_function"),
            "start_register": _optional_int(env_soil, "start_register", 0, 0, 65535, "env_sensors.soil.start_register"),
        },
        "power_settle_ms": _optional_int(env_sensors, "power_settle_ms", 800, 0, 30000, "env_sensors.power_settle_ms"),
    }

    env_metric_keys = (
        "par_umol_m2_s",
        "soil_moisture_percent",
        "soil_temperature_c",
        "soil_ec_us_cm",
        "soil_ph",
        "soil_n_mg_kg",
        "soil_p_mg_kg",
        "soil_k_mg_kg",
    )
    env_calibration = config.get("env_calibration", {})
    if not isinstance(env_calibration, dict):
        raise DeviceConfigValidationError("env_calibration must be an object")
    env_calibration_mode = _optional_str(env_calibration, "mode", "normal", "env_calibration.mode", 24)
    allowed_env_calibration_modes = {"normal", "capture_reference", "reset"}
    if env_calibration_mode not in allowed_env_calibration_modes:
        raise DeviceConfigValidationError("env_calibration.mode must be normal, capture_reference, or reset")
    env_calibration_request_id = _optional_str(env_calibration, "request_id", "", "env_calibration.request_id", 39)
    if env_calibration_mode != "normal" and not env_calibration_request_id:
        raise DeviceConfigValidationError("env_calibration.request_id is required when mode is not normal")
    env_calibration_target = _optional_str(
        env_calibration,
        "target",
        "par_umol_m2_s",
        "env_calibration.target",
        32,
    )
    if env_calibration_target not in env_metric_keys:
        raise DeviceConfigValidationError("env_calibration.target is not supported")

    def _metric_calibration(metric: str):
        metric_config = env_calibration.get(metric, {})
        if not isinstance(metric_config, dict):
            raise DeviceConfigValidationError(f"env_calibration.{metric} must be an object")
        return {
            "calibrated": _optional_bool(metric_config, "calibrated", False, f"env_calibration.{metric}.calibrated"),
            "scale": _optional_float(metric_config, "scale", 1.0, 0.0001, 100000.0, f"env_calibration.{metric}.scale"),
            "offset": _optional_float(metric_config, "offset", 0.0, -100000.0, 100000.0, f"env_calibration.{metric}.offset"),
        }

    normalized_env_calibration = {
        "mode": env_calibration_mode,
        "request_id": env_calibration_request_id,
        "target": env_calibration_target,
        "reference_value": _optional_float(
            env_calibration,
            "reference_value",
            0.0,
            -100000.0,
            100000.0,
            "env_calibration.reference_value",
        ),
    }
    for metric in env_metric_keys:
        normalized_env_calibration[metric] = _metric_calibration(metric)

    wrs = config.get("wrs", {})
    if not isinstance(wrs, dict):
        raise DeviceConfigValidationError("wrs must be an object")
    wrs_watering = wrs.get("watering", {})
    wrs_sensors = wrs.get("sensors", {})
    if not isinstance(wrs_watering, dict):
        raise DeviceConfigValidationError("wrs.watering must be an object")
    if not isinstance(wrs_sensors, dict):
        raise DeviceConfigValidationError("wrs.sensors must be an object")
    wrs_soil = wrs_sensors.get("soil", {})
    wrs_par = wrs_sensors.get("par", {})
    if not isinstance(wrs_soil, dict):
        raise DeviceConfigValidationError("wrs.sensors.soil must be an object")
    if not isinstance(wrs_par, dict):
        raise DeviceConfigValidationError("wrs.sensors.par must be an object")
    normalized_wrs = {
        "watering": {
            "enabled": _optional_bool(wrs_watering, "enabled", True, "wrs.watering.enabled"),
            "auto_on_low_moisture": _optional_bool(wrs_watering, "auto_on_low_moisture", False, "wrs.watering.auto_on_low_moisture"),
            "require_soil_feedback": _optional_bool(wrs_watering, "require_soil_feedback", True, "wrs.watering.require_soil_feedback"),
            "force_watering": _optional_bool(wrs_watering, "force_watering", False, "wrs.watering.force_watering"),
            "moisture_threshold": _optional_int(wrs_watering, "moisture_threshold", moisture_threshold, 0, 100, "wrs.watering.moisture_threshold"),
            "stop_moisture_percent": _optional_int(wrs_watering, "stop_moisture_percent", 55, 0, 100, "wrs.watering.stop_moisture_percent"),
            "max_duration_sec": _optional_int(wrs_watering, "max_duration_sec", 60, 1, 3600, "wrs.watering.max_duration_sec"),
            "check_interval_sec": _optional_int(wrs_watering, "check_interval_sec", 10, 1, 600, "wrs.watering.check_interval_sec"),
            "channel_mask": _optional_int(wrs_watering, "channel_mask", 1, 1, 0xFFFFFFFF, "wrs.watering.channel_mask"),
        },
        "sensors": {
            "soil": {
                "enabled": _optional_bool(wrs_soil, "enabled", True, "wrs.sensors.soil.enabled"),
                "modbus_slave_id": _optional_int(wrs_soil, "modbus_slave_id", 2, 1, 247, "wrs.sensors.soil.modbus_slave_id"),
                "modbus_function": _optional_int(wrs_soil, "modbus_function", 4, 3, 4, "wrs.sensors.soil.modbus_function"),
                "start_register": _optional_int(wrs_soil, "start_register", 0, 0, 65535, "wrs.sensors.soil.start_register"),
            },
            "par": {
                "enabled": _optional_bool(wrs_par, "enabled", False, "wrs.sensors.par.enabled"),
                "modbus_slave_id": _optional_int(wrs_par, "modbus_slave_id", 1, 1, 247, "wrs.sensors.par.modbus_slave_id"),
                "modbus_function": _optional_int(wrs_par, "modbus_function", 3, 3, 4, "wrs.sensors.par.modbus_function"),
                "register": _optional_int(wrs_par, "register", 0, 0, 65535, "wrs.sensors.par.register"),
                "scale": _optional_float(wrs_par, "scale", 1.0, 0.0001, 100000.0, "wrs.sensors.par.scale"),
            },
            "power_settle_ms": _optional_int(wrs_sensors, "power_settle_ms", 800, 0, 30000, "wrs.sensors.power_settle_ms"),
        },
    }

    normalized_fgt = None
    if "fgt" in config:
        fgt = config["fgt"]
        if not isinstance(fgt, dict):
            raise DeviceConfigValidationError("fgt must be an object")
        recipe = fgt.get("recipe", {})
        limits = fgt.get("limits", {})
        sensors = fgt.get("sensors", {})
        if not isinstance(recipe, dict):
            raise DeviceConfigValidationError("fgt.recipe must be an object")
        if not isinstance(limits, dict):
            raise DeviceConfigValidationError("fgt.limits must be an object")
        if not isinstance(sensors, dict):
            raise DeviceConfigValidationError("fgt.sensors must be an object")
        soil = sensors.get("soil", {})
        par = sensors.get("par", {})
        if not isinstance(soil, dict):
            raise DeviceConfigValidationError("fgt.sensors.soil must be an object")
        if not isinstance(par, dict):
            raise DeviceConfigValidationError("fgt.sensors.par must be an object")

        normalized_fgt_recipe = {
            "total_water_ml": _optional_int(recipe, "total_water_ml", 4500, 100, 100000, "fgt.recipe.total_water_ml"),
            "initial_water_ml": _optional_int(recipe, "initial_water_ml", 1250, 50, 100000, "fgt.recipe.initial_water_ml"),
            "nutrient_a_ml": _optional_int(recipe, "nutrient_a_ml", 10, 0, 10000, "fgt.recipe.nutrient_a_ml"),
            "nutrient_b_ml": _optional_int(recipe, "nutrient_b_ml", 10, 0, 10000, "fgt.recipe.nutrient_b_ml"),
            "nutrient_a_rate_ml_min": _optional_int(recipe, "nutrient_a_rate_ml_min", 100, 1, 10000, "fgt.recipe.nutrient_a_rate_ml_min"),
            "nutrient_b_rate_ml_min": _optional_int(recipe, "nutrient_b_rate_ml_min", 100, 1, 10000, "fgt.recipe.nutrient_b_rate_ml_min"),
            "pre_mix_sec": _optional_int(recipe, "pre_mix_sec", 10, 1, 600, "fgt.recipe.pre_mix_sec"),
            "mix_after_a_sec": _optional_int(recipe, "mix_after_a_sec", 30, 0, 1800, "fgt.recipe.mix_after_a_sec"),
            "mix_after_b_sec": _optional_int(recipe, "mix_after_b_sec", 60, 0, 1800, "fgt.recipe.mix_after_b_sec"),
            "final_mix_sec": _optional_int(recipe, "final_mix_sec", 120, 1, 3600, "fgt.recipe.final_mix_sec"),
            "irrigation_max_sec": _optional_int(recipe, "irrigation_max_sec", 900, 1, 7200, "fgt.recipe.irrigation_max_sec"),
            "rinse_water_ml": _optional_int(recipe, "rinse_water_ml", 500, 0, 100000, "fgt.recipe.rinse_water_ml"),
            "rinse_mix_sec": _optional_int(recipe, "rinse_mix_sec", 30, 0, 1800, "fgt.recipe.rinse_mix_sec"),
            "rinse_drain_max_sec": _optional_int(recipe, "rinse_drain_max_sec", 180, 0, 3600, "fgt.recipe.rinse_drain_max_sec"),
        }
        normalized_fgt_limits = {
            "max_total_water_ml": _optional_int(limits, "max_total_water_ml", 10000, 100, 100000, "fgt.limits.max_total_water_ml"),
            "max_nutrient_ml": _optional_int(limits, "max_nutrient_ml", 100, 1, 10000, "fgt.limits.max_nutrient_ml"),
            "water_no_flow_timeout_sec": _optional_int(limits, "water_no_flow_timeout_sec", 15, 1, 300, "fgt.limits.water_no_flow_timeout_sec"),
            "max_fill_sec": _optional_int(limits, "max_fill_sec", 300, 1, 3600, "fgt.limits.max_fill_sec"),
            "max_batch_sec": _optional_int(limits, "max_batch_sec", 1800, 60, 14400, "fgt.limits.max_batch_sec"),
            "volume_tolerance_ml": _optional_int(limits, "volume_tolerance_ml", 100, 0, 5000, "fgt.limits.volume_tolerance_ml"),
        }
        if normalized_fgt_recipe["initial_water_ml"] >= normalized_fgt_recipe["total_water_ml"]:
            raise DeviceConfigValidationError("fgt.recipe.initial_water_ml must be less than total_water_ml")
        if normalized_fgt_recipe["total_water_ml"] > normalized_fgt_limits["max_total_water_ml"]:
            raise DeviceConfigValidationError("fgt.recipe.total_water_ml must not exceed fgt.limits.max_total_water_ml")
        if max(normalized_fgt_recipe["nutrient_a_ml"], normalized_fgt_recipe["nutrient_b_ml"]) > normalized_fgt_limits["max_nutrient_ml"]:
            raise DeviceConfigValidationError("fgt recipe nutrient volume must not exceed fgt.limits.max_nutrient_ml")
        if normalized_fgt_recipe["rinse_water_ml"] > normalized_fgt_limits["max_total_water_ml"]:
            raise DeviceConfigValidationError("fgt.recipe.rinse_water_ml must not exceed fgt.limits.max_total_water_ml")
        if normalized_fgt_recipe["rinse_water_ml"] > 0 and (normalized_fgt_recipe["rinse_mix_sec"] == 0 or normalized_fgt_recipe["rinse_drain_max_sec"] == 0):
            raise DeviceConfigValidationError("enabled FGT rinse requires rinse_mix_sec and rinse_drain_max_sec")

        normalized_fgt = {
            "enabled": _optional_bool(fgt, "enabled", False, "fgt.enabled"),
            "recovery_ack": _optional_int(fgt, "recovery_ack", 0, 0, 0xFFFFFFFF, "fgt.recovery_ack"),
            "recipe": normalized_fgt_recipe,
            "limits": normalized_fgt_limits,
            "sensors": {
                "soil": {
                    "enabled": _optional_bool(soil, "enabled", True, "fgt.sensors.soil.enabled"),
                    "modbus_slave_id": _optional_int(soil, "modbus_slave_id", 2, 1, 247, "fgt.sensors.soil.modbus_slave_id"),
                    "modbus_function": _optional_int(soil, "modbus_function", 4, 3, 4, "fgt.sensors.soil.modbus_function"),
                    "start_register": _optional_int(soil, "start_register", 0, 0, 65535, "fgt.sensors.soil.start_register"),
                },
                "par": {
                    "enabled": _optional_bool(par, "enabled", True, "fgt.sensors.par.enabled"),
                    "modbus_slave_id": _optional_int(par, "modbus_slave_id", 1, 1, 247, "fgt.sensors.par.modbus_slave_id"),
                    "modbus_function": _optional_int(par, "modbus_function", 3, 3, 4, "fgt.sensors.par.modbus_function"),
                    "register": _optional_int(par, "register", 0, 0, 65535, "fgt.sensors.par.register"),
                    "scale": _optional_float(par, "scale", 1.0, 0.0001, 100000.0, "fgt.sensors.par.scale"),
                },
                "power_settle_ms": _optional_int(sensors, "power_settle_ms", 800, 0, 30000, "fgt.sensors.power_settle_ms"),
                "flow_pulses_per_liter": _optional_int(sensors, "flow_pulses_per_liter", 450, 1, 1000000, "fgt.sensors.flow_pulses_per_liter"),
            },
        }

    mosfet_switches = config.get("mosfet_switches", [])
    if not isinstance(mosfet_switches, list):
        raise DeviceConfigValidationError("mosfet_switches must be an array")
    if len(mosfet_switches) > 16:
        raise DeviceConfigValidationError("mosfet_switches must contain 16 entries or less")

    normalized_mosfet_switches = []
    mosfet_switch_ids = set()
    for index, switch in enumerate(mosfet_switches):
        if not isinstance(switch, dict):
            raise DeviceConfigValidationError(f"mosfet_switches[{index}] must be an object")

        switch_id = _optional_str(switch, "switch_id", "", f"mosfet_switches[{index}].switch_id", 32)
        if not switch_id or not MOSFET_SWITCH_ID_RE.match(switch_id):
            raise DeviceConfigValidationError(f"mosfet_switches[{index}].switch_id must contain only letters, numbers, _, ., :, or -")
        if switch_id in mosfet_switch_ids:
            raise DeviceConfigValidationError(f"mosfet_switches[{index}].switch_id must be unique")
        mosfet_switch_ids.add(switch_id)

        name = _optional_str(switch, "name", switch_id, f"mosfet_switches[{index}].name", 64)
        if not name:
            raise DeviceConfigValidationError(f"mosfet_switches[{index}].name must be a non-empty string")

        normalized_mosfet_switches.append(
            {
                "switch_id": switch_id,
                "name": name,
                "enabled": _optional_bool(switch, "enabled", True, f"mosfet_switches[{index}].enabled"),
                "role": _optional_str(switch, "role", "", f"mosfet_switches[{index}].role", 32),
                "terminal": _optional_str(switch, "terminal", "", f"mosfet_switches[{index}].terminal", 32),
                "channel_mask": _optional_int(switch, "channel_mask", 0, 0, 0xFFFFFFFF, f"mosfet_switches[{index}].channel_mask"),
                "controlled_load": _optional_str(switch, "controlled_load", "", f"mosfet_switches[{index}].controlled_load", 96),
                "notes": _optional_str(switch, "notes", "", f"mosfet_switches[{index}].notes", 160),
            }
        )

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
                "enabled": _optional_bool(schedule, "enabled", True, f"schedules[{index}].enabled"),
                "frequency": normalized_frequency,
            }
        )

    if normalized_fgt is not None:
        enabled_fgt_schedules = [schedule for schedule in normalized_schedules if schedule["enabled"]]
        if any(schedule["frequency"]["mode"] != "daily" for schedule in enabled_fgt_schedules):
            raise DeviceConfigValidationError("enabled FGT schedules must use daily frequency")
        if len(enabled_fgt_schedules) > 4:
            raise DeviceConfigValidationError("FGT supports at most 4 enabled daily schedules")
        if normalized_fgt["enabled"] and not enabled_fgt_schedules:
            raise DeviceConfigValidationError("enabled FGT requires at least one enabled daily schedule")

    normalized = {
        "ntp_server": ntp_server.strip(),
        "timezone_offset_sec": timezone_offset_sec,
        "moisture_threshold": moisture_threshold,
        "force_watering": force_watering,
        "debug_log_on_wake": debug_log_on_wake,
        "sleep_sec": sleep_sec,
        "ota_check_interval_sec": ota_check_interval_sec,
        "watering_pattern": normalized_watering_pattern,
        "soil_calibration": normalized_soil_calibration,
        "env_sensors": normalized_env_sensors,
        "env_calibration": normalized_env_calibration,
        "wrs": normalized_wrs,
        "mosfet_switches": normalized_mosfet_switches,
        "schedules": normalized_schedules,
    }
    if normalized_fgt is not None:
        normalized["fgt"] = normalized_fgt
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) >= 4096:
        raise DeviceConfigValidationError("config payload must be less than 4096 bytes")
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
