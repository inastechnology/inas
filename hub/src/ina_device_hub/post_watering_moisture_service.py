import json
import math
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.general_log import logger
from ina_device_hub.json_repository_io import atomic_write_json
from ina_device_hub.setting import setting

WATERING_DEVICE_KINDS = {"WTR", "WRS", "FGT"}
SOIL_MOISTURE_DEVICE_KINDS = {"SOI", "ENV", "WTR", "WRS", "FGT"}
DEFAULT_MINIMUM_PERCENT = 55.0


class PostWateringMoistureValidationError(ValueError):
    pass


class PostWateringMoistureService:
    def __init__(self, settings_store=None, notification_service=None, state_path=None):
        self.settings_store = settings_store or setting()
        self.notification_service = notification_service or discord_notification_service()
        self.state_path = state_path or os.path.join(self.settings_store.get_work_dir(), ".post_watering_moisture_state.json")
        self._state_lock = threading.RLock()
        self.state = self._load_state()

    def list_rules(self):
        config = self.settings_store.get("post_watering_moisture") or {}
        rules = config.get("rules") if isinstance(config, dict) else []
        return [deepcopy(rule) for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []

    def save_rule(self, value: dict, devices: dict):
        rule = validate_post_watering_moisture_rule(value, devices)
        rules = [item for item in self.list_rules() if item.get("watering_device_id") != rule["watering_device_id"]]
        rules.append(rule)
        rules.sort(key=lambda item: str(item.get("watering_device_id") or ""))
        self.settings_store.set("post_watering_moisture", {"rules": rules})
        self._clear_rule_state(rule["watering_device_id"])
        return deepcopy(rule)

    def process_status(self, device_id: str, record: dict, status: dict):
        if not isinstance(status, dict) or record.get("state") != "active":
            return False
        rules = [rule for rule in self.list_rules() if rule.get("enabled") is True]
        if not rules:
            return False

        changed = False
        with self._state_lock:
            for rule in rules:
                watering_device_id = rule.get("watering_device_id")
                sensor_device_id = rule.get("sensor_device_id")
                if device_id == watering_device_id and _watering_was_performed(status):
                    changed |= self._start_watering_event(rule, record, status)
                    after_value = _explicit_post_watering_value(status)
                    if sensor_device_id == device_id and after_value is not None:
                        changed |= self._evaluate_pending(rule, record, after_value, record.get("last_status_at"), "潅水機の潅水後測定値")
                    continue
                if device_id != sensor_device_id:
                    continue
                sensor_value = soil_moisture_value(status)
                if sensor_value is None:
                    continue
                changed |= self._evaluate_pending(rule, record, sensor_value, record.get("last_status_at"), "選択センサーの次回測定値")
            if changed:
                self._save_state()
        return changed

    def _start_watering_event(self, rule: dict, record: dict, status: dict):
        watering_device_id = rule["watering_device_id"]
        event_id = _watering_event_id(record, status)
        current = self.state.get(watering_device_id)
        if isinstance(current, dict) and current.get("event_id") == event_id:
            return False
        self.state[watering_device_id] = {
            "event_id": event_id,
            "status": "pending",
            "watered_at": record.get("last_status_at") or datetime.now(UTC).isoformat(),
            "watering_device_name": record.get("name") or watering_device_id,
            "watering_device_location": record.get("location") or "未設定",
            "watering_device_kind": record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "",
            "sensor_device_id": rule["sensor_device_id"],
            "minimum_percent": rule["minimum_percent"],
        }
        return True

    def _evaluate_pending(self, rule: dict, sensor_record: dict, value: float, measured_at, source_label: str):
        watering_device_id = rule["watering_device_id"]
        current = self.state.get(watering_device_id)
        if not isinstance(current, dict) or current.get("status") != "pending":
            return False
        if current.get("sensor_device_id") != rule["sensor_device_id"]:
            return False
        watered_at = _parse_datetime(current.get("watered_at"))
        measurement_at = _parse_datetime(measured_at)
        if watered_at is None or measurement_at is None or measurement_at < watered_at:
            return False

        minimum_percent = float(rule["minimum_percent"])
        current.update(
            {
                "status": "alerted" if value < minimum_percent else "ok",
                "measured_at": measurement_at.isoformat(),
                "measured_percent": value,
                "minimum_percent": minimum_percent,
                "sensor_device_name": sensor_record.get("name") or rule["sensor_device_id"],
                "measurement_source": source_label,
            }
        )
        if value < minimum_percent:
            watering_record = {
                "name": current.get("watering_device_name") or watering_device_id,
                "location": current.get("watering_device_location") or "未設定",
                "device_kind": current.get("watering_device_kind") or "WTR",
                "state": "active",
            }
            details = {
                "watered_at": current.get("watered_at"),
                "measured_at": measurement_at.isoformat(),
                "measured_percent": value,
                "minimum_percent": minimum_percent,
                "sensor_device_id": rule["sensor_device_id"],
                "sensor_device_name": current["sensor_device_name"],
                "measurement_source": source_label,
            }
            try:
                self.notification_service.notify_health_alert(
                    "post_watering_moisture_low",
                    watering_device_id,
                    watering_record,
                    details,
                )
            except Exception:
                logger.exception("Post-watering soil moisture notification failed for device_id=%s", watering_device_id)
        return True

    def _clear_rule_state(self, watering_device_id: str):
        with self._state_lock:
            if watering_device_id not in self.state:
                return
            del self.state[watering_device_id]
            self._save_state()

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as file:
                state = json.load(file)
            return state.get("rules", {}) if isinstance(state, dict) and isinstance(state.get("rules"), dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        atomic_write_json(self.state_path, {"schema_version": 1, "rules": self.state})


def validate_post_watering_moisture_rule(value: dict, devices: dict):
    if not isinstance(value, dict):
        raise PostWateringMoistureValidationError("設定内容を読み取れませんでした。")
    watering_device_id = str(value.get("watering_device_id") or "").strip()
    sensor_device_id = str(value.get("sensor_device_id") or "").strip()
    watering_record = devices.get(watering_device_id) if isinstance(devices, dict) else None
    sensor_record = devices.get(sensor_device_id) if isinstance(devices, dict) else None
    if not _active_watering_device(watering_record):
        raise PostWateringMoistureValidationError("利用中の潅水機を選んでください。")
    if not _active_soil_moisture_sensor(sensor_record):
        raise PostWateringMoistureValidationError("土壌水分を測定できる利用中のセンサーを選んでください。")
    try:
        minimum_percent = float(value.get("minimum_percent"))
    except (TypeError, ValueError) as exc:
        raise PostWateringMoistureValidationError("最低水分率は0〜100%で入力してください。") from exc
    if not math.isfinite(minimum_percent) or not 0 <= minimum_percent <= 100:
        raise PostWateringMoistureValidationError("最低水分率は0〜100%で入力してください。")
    return {
        "watering_device_id": watering_device_id,
        "sensor_device_id": sensor_device_id,
        "minimum_percent": round(minimum_percent, 1),
        "enabled": value.get("enabled") is True,
    }


def post_watering_device_options(devices: dict):
    options = []
    for device_id, record in (devices or {}).items():
        if not _active_watering_device(record):
            continue
        options.append(_device_option(device_id, record))
    return sorted(options, key=lambda item: (item["name"].casefold(), item["id"]))


def soil_moisture_sensor_options(devices: dict):
    options = []
    for device_id, record in (devices or {}).items():
        if not _active_soil_moisture_sensor(record):
            continue
        option = _device_option(device_id, record)
        option["latest_percent"] = soil_moisture_value(record.get("last_status") or {})
        options.append(option)
    return sorted(options, key=lambda item: (item["name"].casefold(), item["id"]))


def post_watering_rule_views(rules: list[dict], devices: dict):
    views = []
    for rule in rules:
        watering = (devices or {}).get(rule.get("watering_device_id")) or {}
        sensor = (devices or {}).get(rule.get("sensor_device_id")) or {}
        views.append(
            {
                **deepcopy(rule),
                "watering_device_name": watering.get("name") or rule.get("watering_device_id") or "未設定",
                "sensor_device_name": sensor.get("name") or rule.get("sensor_device_id") or "未設定",
            }
        )
    return views


def soil_moisture_value(status: dict):
    if not isinstance(status, dict):
        return None
    percent_value = _first_number(status, ("soil_moisture_percent",))
    percent_failed = (status.get("soil_rs485_ok") is False and status.get("soil_moisture_ok") is not True) or (
        status.get("soil_moisture_ok") is False and status.get("soil_rs485_ok") is not True
    )
    if percent_value is not None and not percent_failed:
        return percent_value
    if status.get("soil_moisture_ok") is False:
        return None
    return _first_number(status, ("last_soil_moisture",))


def _explicit_post_watering_value(status: dict):
    if status.get("watering_completed") is not True or status.get("soil_rs485_ok") is False:
        return None
    return _first_number(status, ("soil_moisture_after_watering",))


def _watering_was_performed(status: dict):
    return status.get("watering_started") is True or status.get("batch_started") is True


def _watering_event_id(record: dict, status: dict):
    stable_part = status.get("schedule_epoch_utc") or status.get("batch_id") or status.get("seq") or "status"
    return f"{stable_part}:{record.get('last_status_at') or ''}"


def _active_watering_device(record):
    if not isinstance(record, dict) or record.get("state") != "active":
        return False
    kind = str(record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "").upper()
    return kind in WATERING_DEVICE_KINDS


def _active_soil_moisture_sensor(record):
    if not isinstance(record, dict) or record.get("state") != "active":
        return False
    kind = str(record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "").upper()
    return kind in SOIL_MOISTURE_DEVICE_KINDS


def _device_option(device_id: str, record: dict):
    return {
        "id": device_id,
        "name": record.get("name") or device_id,
        "location": record.get("location") or "場所未設定",
        "device_kind": record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "",
    }


def _first_number(value: dict, keys: tuple[str, ...]):
    if not isinstance(value, dict):
        return None
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, bool) or not isinstance(candidate, int | float):
            continue
        candidate = float(candidate)
        if math.isfinite(candidate):
            return candidate
    return None


def _parse_datetime(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@lru_cache(maxsize=1)
def post_watering_moisture_service():
    return PostWateringMoistureService()
