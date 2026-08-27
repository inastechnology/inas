import json
import math
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.general_log import logger
from ina_device_hub.json_repository_io import atomic_write_json
from ina_device_hub.sensor_measurement_repository import sensor_measurement_repository
from ina_device_hub.setting import setting

WATERING_DEVICE_KINDS = {"WTR", "WRS", "FGT"}
SOIL_MOISTURE_DEVICE_KINDS = {"SOI", "ENV", "WTR", "WRS", "FGT"}
DEFAULT_MINIMUM_PERCENT = 55.0
DEFAULT_WINDOW_DAYS = 3
DEFAULT_MEASUREMENT_SOURCE = "device"
AVERAGE_MEASUREMENT_SOURCE = "rs485:average"
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 14
MINIMUM_WINDOW_SAMPLES = 3
RENOTIFY_INTERVAL = timedelta(hours=24)
MEASUREMENT_LIMIT = 20000


class PostWateringMoistureValidationError(ValueError):
    pass


class PostWateringMoistureService:
    """Monitor whether soil moisture reached a configured value in a rolling window.

    Historical class and setting names are retained so installed Hubs can migrate
    existing post-watering rules without losing their selected sensor or threshold.
    """

    def __init__(self, settings_store=None, notification_service=None, measurement_repository=None, state_path=None):
        self.settings_store = settings_store or setting()
        self.notification_service = notification_service or discord_notification_service()
        self.measurement_repository = measurement_repository or sensor_measurement_repository()
        self.state_path = state_path or os.path.join(self.settings_store.get_work_dir(), ".post_watering_moisture_state.json")
        self._state_lock = threading.RLock()
        self._migrate_rules()
        self.state = self._load_state()

    def list_rules(self):
        config = self.settings_store.get("post_watering_moisture") or {}
        rules = config.get("rules") if isinstance(config, dict) else []
        return [deepcopy(rule) for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []

    def save_rule(self, value: dict, devices: dict):
        rule = validate_post_watering_moisture_rule(value, devices)
        rules = [item for item in self.list_rules() if item.get("sensor_device_id") != rule["sensor_device_id"]]
        rules.append(rule)
        rules.sort(key=lambda item: str(item.get("sensor_device_id") or ""))
        self.settings_store.set("post_watering_moisture", {"rules": rules})
        self._clear_rule_state(rule["sensor_device_id"])
        return deepcopy(rule)

    def delete_rule(self, sensor_device_id: str):
        sensor_device_id = str(sensor_device_id or "").strip()
        if not sensor_device_id:
            raise PostWateringMoistureValidationError("削除するセンサーを選んでください。")
        rules = self.list_rules()
        deleted = next((item for item in rules if item.get("sensor_device_id") == sensor_device_id), None)
        if deleted is None:
            raise PostWateringMoistureValidationError("削除する通知条件が見つかりませんでした。")
        remaining = [item for item in rules if item.get("sensor_device_id") != sensor_device_id]
        self.settings_store.set("post_watering_moisture", {"rules": remaining})
        self._clear_rule_state(sensor_device_id)
        return deepcopy(deleted)

    def process_status(self, device_id: str, record: dict, status: dict):
        if not isinstance(status, dict) or record.get("state") != "active":
            return False
        rule = next(
            (item for item in self.list_rules() if item.get("enabled") is True and item.get("sensor_device_id") == device_id),
            None,
        )
        if rule is None:
            return False
        if soil_moisture_source_value(status, rule.get("measurement_source")) is None:
            return False
        measured_at = _parse_datetime(record.get("last_status_at")) or datetime.now(UTC)
        return self._evaluate_rule(rule, record, measured_at)

    def evaluate_rules(self, devices: dict, *, now: datetime | None = None):
        evaluation_time = _as_utc(now or datetime.now(UTC))
        changed = False
        for rule in self.list_rules():
            if rule.get("enabled") is not True:
                continue
            sensor_device_id = str(rule.get("sensor_device_id") or "")
            sensor_record = (devices or {}).get(sensor_device_id) or {}
            if sensor_record.get("state") != "active":
                changed |= self._set_non_evaluated_state(sensor_device_id, "sensor_unavailable", evaluation_time)
                continue
            changed |= self._evaluate_rule(rule, sensor_record, evaluation_time)
        return changed

    def rule_status(self, sensor_device_id: str):
        with self._state_lock:
            value = self.state.get(str(sensor_device_id or ""))
            return deepcopy(value) if isinstance(value, dict) else {}

    def _evaluate_rule(self, rule: dict, sensor_record: dict, now: datetime):
        sensor_device_id = rule["sensor_device_id"]
        window_days = int(rule["window_days"])
        measurement_source = rule.get("measurement_source") or DEFAULT_MEASUREMENT_SOURCE
        measurement_source_label = soil_moisture_source_label(sensor_record, measurement_source)
        range_start = now - timedelta(days=window_days)
        try:
            if measurement_source == DEFAULT_MEASUREMENT_SOURCE:
                measurements = self.measurement_repository.between_for_devices(
                    [sensor_device_id],
                    range_start.isoformat(),
                    (now + timedelta(microseconds=1)).isoformat(),
                    limit=MEASUREMENT_LIMIT,
                    metric="soil_moisture_percent",
                )
            else:
                measurements = soil_moisture_measurements_from_status_history(sensor_record.get("status_history"), measurement_source)
            evaluation = analyze_moisture_window(measurements, rule, now=now)
        except Exception:  # noqa: BLE001
            logger.exception("Unable to evaluate soil moisture window for sensor_device_id=%s", sensor_device_id)
            return self._set_non_evaluated_state(sensor_device_id, "data_unavailable", now)

        with self._state_lock:
            previous = self.state.get(sensor_device_id) if isinstance(self.state.get(sensor_device_id), dict) else {}
            current = {
                **evaluation,
                "sensor_device_id": sensor_device_id,
                "measurement_source": measurement_source,
                "measurement_source_label": measurement_source_label,
                "minimum_percent": float(rule["minimum_percent"]),
                "window_days": window_days,
                "evaluated_at": now.isoformat(),
            }
            previous_notified_at = _parse_datetime(previous.get("last_notified_at"))
            if evaluation["status"] == "not_reached":
                should_notify = previous_notified_at is None or now - previous_notified_at >= RENOTIFY_INTERVAL
                if should_notify:
                    details = {
                        "sensor_device_id": sensor_device_id,
                        "sensor_device_name": sensor_record.get("name") or sensor_device_id,
                        "measurement_source": measurement_source,
                        "measurement_source_label": measurement_source_label,
                        "measured_percent": evaluation.get("latest_percent"),
                        "measured_at": evaluation.get("latest_measured_at"),
                        "minimum_percent": float(rule["minimum_percent"]),
                        "window_days": window_days,
                        "measurement_count": evaluation.get("measurement_count"),
                        "last_reached_at": previous.get("last_reached_at") or evaluation.get("last_reached_at"),
                    }
                    try:
                        self.notification_service.notify_health_alert(
                            "post_watering_moisture_low",
                            sensor_device_id,
                            sensor_record,
                            details,
                        )
                    except Exception:
                        logger.exception("Soil moisture not-reached notification failed for sensor_device_id=%s", sensor_device_id)
                    current["last_notified_at"] = now.isoformat()
                elif previous.get("last_notified_at"):
                    current["last_notified_at"] = previous["last_notified_at"]
                if previous.get("last_reached_at") and not current.get("last_reached_at"):
                    current["last_reached_at"] = previous["last_reached_at"]
            elif evaluation["status"] == "insufficient_data":
                if previous.get("last_notified_at"):
                    current["last_notified_at"] = previous["last_notified_at"]
                if previous.get("last_reached_at") and not current.get("last_reached_at"):
                    current["last_reached_at"] = previous["last_reached_at"]

            if current == previous:
                return False
            self.state[sensor_device_id] = current
            self._save_state()
            return True

    def _set_non_evaluated_state(self, sensor_device_id: str, status: str, now: datetime):
        if not sensor_device_id:
            return False
        with self._state_lock:
            previous = self.state.get(sensor_device_id) if isinstance(self.state.get(sensor_device_id), dict) else {}
            current = {
                "sensor_device_id": sensor_device_id,
                "status": status,
                "evaluated_at": now.isoformat(),
            }
            for key in ("last_notified_at", "last_reached_at", "latest_percent", "latest_measured_at"):
                if previous.get(key) is not None:
                    current[key] = previous[key]
            if current == previous:
                return False
            self.state[sensor_device_id] = current
            self._save_state()
            return True

    def _migrate_rules(self):
        config = self.settings_store.get("post_watering_moisture") or {}
        source_rules = config.get("rules") if isinstance(config, dict) else []
        source_rules = source_rules if isinstance(source_rules, list) else []
        by_sensor = {}
        for source_rule in source_rules:
            migrated = _normalize_stored_rule(source_rule)
            if migrated:
                by_sensor[migrated["sensor_device_id"]] = migrated
        migrated_rules = sorted(by_sensor.values(), key=lambda item: item["sensor_device_id"])
        if migrated_rules != source_rules:
            self.settings_store.set("post_watering_moisture", {"rules": migrated_rules})

    def _clear_rule_state(self, sensor_device_id: str):
        with self._state_lock:
            if sensor_device_id not in self.state:
                return
            del self.state[sensor_device_id]
            self._save_state()

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as file:
                state = json.load(file)
            if not isinstance(state, dict) or state.get("schema_version") != 2 or not isinstance(state.get("rules"), dict):
                return {}
            return state["rules"]
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        atomic_write_json(self.state_path, {"schema_version": 2, "rules": self.state})


def validate_post_watering_moisture_rule(value: dict, devices: dict):
    if not isinstance(value, dict):
        raise PostWateringMoistureValidationError("設定内容を読み取れませんでした。")
    sensor_device_id = str(value.get("sensor_device_id") or "").strip()
    sensor_record = devices.get(sensor_device_id) if isinstance(devices, dict) else None
    if not _active_soil_moisture_sensor(sensor_record):
        raise PostWateringMoistureValidationError("土壌水分を測定できる利用中のセンサーを選んでください。")
    measurement_source = str(value.get("measurement_source") or DEFAULT_MEASUREMENT_SOURCE).strip()
    available_sources = {item["id"] for item in soil_moisture_source_options(sensor_record)}
    if measurement_source not in available_sources:
        raise PostWateringMoistureValidationError("判定に使う土壌水分の値を選んでください。")
    try:
        minimum_percent = float(value.get("minimum_percent"))
    except (TypeError, ValueError) as exc:
        raise PostWateringMoistureValidationError("到達判定値は0〜100%で入力してください。") from exc
    if not math.isfinite(minimum_percent) or not 0 <= minimum_percent <= 100:
        raise PostWateringMoistureValidationError("到達判定値は0〜100%で入力してください。")
    try:
        window_days = int(value.get("window_days"))
    except (TypeError, ValueError) as exc:
        raise PostWateringMoistureValidationError("監視期間は1〜14日で入力してください。") from exc
    if not MIN_WINDOW_DAYS <= window_days <= MAX_WINDOW_DAYS:
        raise PostWateringMoistureValidationError("監視期間は1〜14日で入力してください。")
    return {
        "sensor_device_id": sensor_device_id,
        "measurement_source": measurement_source,
        "minimum_percent": round(minimum_percent, 1),
        "window_days": window_days,
        "enabled": value.get("enabled") is True,
    }


def analyze_moisture_window(measurements: list[dict], rule: dict, *, now: datetime):
    now = _as_utc(now)
    window_days = int(rule["window_days"])
    range_start = now - timedelta(days=window_days)
    minimum_percent = float(rule["minimum_percent"])
    points = []
    for measurement in measurements or []:
        if measurement.get("metric") != "soil_moisture_percent":
            continue
        measured_at = _parse_datetime(measurement.get("measured_at"))
        value = measurement.get("value")
        if measured_at is None or measured_at < range_start or measured_at > now:
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or not 0 <= numeric_value <= 100:
            continue
        points.append((measured_at, numeric_value))
    points.sort(key=lambda item: item[0])

    last_reached_at = next((measured_at for measured_at, value in reversed(points) if value >= minimum_percent), None)

    latest_at, latest_percent = points[-1] if points else (None, None)
    result = {
        "status": "reached" if last_reached_at else "insufficient_data",
        "range_start": range_start.isoformat(),
        "range_end": now.isoformat(),
        "measurement_count": len(points),
        "latest_percent": latest_percent,
        "latest_measured_at": latest_at.isoformat() if latest_at else None,
        "last_reached_at": last_reached_at.isoformat() if last_reached_at else None,
    }
    if last_reached_at:
        return result
    if not _history_covers_window(points, range_start, now):
        return result
    result["status"] = "not_reached"
    return result


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
        option["measurement_sources"] = soil_moisture_source_options(record)
        option["latest_percent"] = option["measurement_sources"][0]["latest_percent"]
        options.append(option)
    return sorted(options, key=lambda item: (item["name"].casefold(), item["id"]))


def post_watering_rule_views(rules: list[dict], devices: dict):
    views = []
    for rule in rules:
        sensor = (devices or {}).get(rule.get("sensor_device_id")) or {}
        views.append(
            {
                **deepcopy(rule),
                "sensor_device_name": sensor.get("name") or rule.get("sensor_device_id") or "未設定",
                "sensor_location": sensor.get("location") or "場所未設定",
                "measurement_source_label": soil_moisture_source_label(sensor, rule.get("measurement_source")),
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


def soil_moisture_source_options(record: dict):
    status = record.get("last_status") if isinstance(record, dict) and isinstance(record.get("last_status"), dict) else {}
    options = [
        {
            "id": DEFAULT_MEASUREMENT_SOURCE,
            "label": "デバイス代表値（従来どおり）",
            "latest_percent": soil_moisture_value(status),
        }
    ]
    soil_devices = _rs485_soil_devices(status)
    for position, device in soil_devices:
        options.append(
            {
                "id": _rs485_source_id(device, position),
                "label": _rs485_source_label(device, position),
                "latest_percent": _rs485_moisture_value(device),
            }
        )
    if len(soil_devices) >= 2:
        options.append(
            {
                "id": AVERAGE_MEASUREMENT_SOURCE,
                "label": f"全土壌センサーの平均（{len(soil_devices)}台）",
                "latest_percent": soil_moisture_source_value(status, AVERAGE_MEASUREMENT_SOURCE),
            }
        )
    return options


def soil_moisture_source_label(record: dict, measurement_source: str | None):
    measurement_source = str(measurement_source or DEFAULT_MEASUREMENT_SOURCE)
    option = next((item for item in soil_moisture_source_options(record) if item["id"] == measurement_source), None)
    return option["label"] if option else "選択した土壌水分値"


def soil_moisture_source_value(status: dict, measurement_source: str | None):
    measurement_source = str(measurement_source or DEFAULT_MEASUREMENT_SOURCE)
    if measurement_source == DEFAULT_MEASUREMENT_SOURCE:
        return soil_moisture_value(status)
    soil_devices = _rs485_soil_devices(status)
    if measurement_source == AVERAGE_MEASUREMENT_SOURCE:
        if len(soil_devices) < 2:
            return None
        values = [_rs485_moisture_value(device) for _position, device in soil_devices]
        if any(value is None for value in values):
            return None
        return sum(values) / len(values)
    for position, device in soil_devices:
        if _rs485_source_id(device, position) == measurement_source:
            return _rs485_moisture_value(device)
    return None


def soil_moisture_measurements_from_status_history(status_history: list[dict] | None, measurement_source: str):
    measurements = []
    for entry in status_history or []:
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        measured_at = entry.get("received_at")
        value = soil_moisture_source_value(payload, measurement_source)
        if not isinstance(measured_at, str) or value is None:
            continue
        measurements.append(
            {
                "metric": "soil_moisture_percent",
                "measured_at": measured_at,
                "value": value,
            }
        )
    return measurements


def _normalize_stored_rule(value):
    if not isinstance(value, dict):
        return None
    sensor_device_id = str(value.get("sensor_device_id") or "").strip()
    if not sensor_device_id:
        return None
    try:
        minimum_percent = float(value.get("minimum_percent"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(minimum_percent) or not 0 <= minimum_percent <= 100:
        return None
    try:
        window_days = int(value.get("window_days", DEFAULT_WINDOW_DAYS))
    except (TypeError, ValueError):
        window_days = DEFAULT_WINDOW_DAYS
    window_days = min(MAX_WINDOW_DAYS, max(MIN_WINDOW_DAYS, window_days))
    return {
        "sensor_device_id": sensor_device_id,
        "measurement_source": _normalize_measurement_source(value.get("measurement_source")),
        "minimum_percent": round(minimum_percent, 1),
        "window_days": window_days,
        "enabled": value.get("enabled") is True,
    }


def _history_covers_window(points, range_start: datetime, now: datetime):
    if len(points) < MINIMUM_WINDOW_SAMPLES:
        return False
    window = now - range_start
    start_grace = max(timedelta(hours=6), window / 10)
    latest_grace = min(timedelta(hours=24), window / 2)
    return points[0][0] <= range_start + start_grace and points[-1][0] >= now - latest_grace


def _normalize_measurement_source(value):
    source = str(value or DEFAULT_MEASUREMENT_SOURCE).strip()
    if source in {DEFAULT_MEASUREMENT_SOURCE, AVERAGE_MEASUREMENT_SOURCE}:
        return source
    if source.startswith(("rs485:index:", "rs485:bus:", "rs485:position:")) and len(source) <= 128:
        return source
    return DEFAULT_MEASUREMENT_SOURCE


def _rs485_soil_devices(status: dict):
    devices = status.get("rs485_devices") if isinstance(status, dict) else None
    if not isinstance(devices, list):
        return []
    return [
        (position, device)
        for position, device in enumerate(devices)
        if isinstance(device, dict) and str(device.get("type") or "").lower() == "soil" and device.get("enabled") is not False
    ]


def _rs485_source_id(device: dict, position: int):
    index = device.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        return f"rs485:index:{index}"
    slave_id = device.get("modbus_slave_id")
    if isinstance(slave_id, int) and not isinstance(slave_id, bool):
        return f"rs485:bus:{str(device.get('type') or '').lower()}:{device.get('baud') or ''}:{slave_id}"
    return f"rs485:position:{position}"


def _rs485_source_label(device: dict, position: int):
    name = str(device.get("name") or "").strip() or f"土壌センサー{position + 1}"
    location = str(device.get("location") or "").strip()
    return f"{name}（{location}）" if location else name


def _rs485_moisture_value(device: dict):
    if device.get("attempted") is False or device.get("bus_ready") is False or device.get("ok") is False:
        return None
    value = _first_number(device, ("moisture_percent", "soil_moisture_percent"))
    return value if value is not None and 0 <= value <= 100 else None


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
    return _as_utc(parsed)


def _as_utc(value: datetime):
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@lru_cache(maxsize=1)
def post_watering_moisture_service():
    return PostWateringMoistureService()
