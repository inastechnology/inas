import json
import os
import threading
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.device_config_repository import device_config_repository
from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting


class HealthMonitorTask:
    def __init__(self, notification_service=None):
        self.settings = setting().get("health_monitor") or {}
        self.notification_service = notification_service or discord_notification_service()
        self.device_repository = device_config_repository()
        self.state_path = os.path.join(setting().get_work_dir(), ".health_monitor_state.json")
        self.state = self._load_state()
        self.scheduler = BlockingScheduler()
        self.worker_thread = None

    def start(self):
        if not self.settings.get("enabled", False):
            logger.info("Skip HealthMonitorTask because it is disabled")
            return
        if self.scheduler.running:
            return

        interval_seconds = max(60, int(self.settings.get("interval_seconds") or 1800))
        self.scheduler.add_job(
            self.run_once,
            "interval",
            seconds=interval_seconds,
            max_instances=1,
            next_run_time=datetime.now(UTC) + timedelta(seconds=10),
        )
        logger.info(f"Start {self.__class__.__name__}(interval: {interval_seconds})")
        self.worker_thread = threading.Thread(target=self.scheduler.start)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
        if self.worker_thread:
            self.worker_thread.join()

    def run_once(self, now: datetime | None = None):
        now = now or datetime.now(UTC)
        devices = self.device_repository.get_all()
        changed = False
        for device_id, record in devices.items():
            if record.get("state") != "active":
                changed |= self._clear_device_alerts(device_id)
                continue

            changed |= self._check_device_offline(device_id, record, now)
            changed |= self._check_watering_missing(device_id, record, now)
            changed |= self._check_soil_calibration_suggested(device_id, record)

        if changed:
            self._save_state()

    def _check_device_offline(self, device_id: str, record: dict, now: datetime):
        threshold_hours = int(self.settings.get("device_offline_after_hours") or 12)
        if threshold_hours <= 0:
            return self._clear_alert(device_id, "device_offline")

        last_seen = _parse_datetime(record.get("last_seen_at") or record.get("last_status_at"))
        if last_seen is None:
            return self._raise_alert(
                device_id,
                "device_offline",
                record,
                {
                    "last_seen_at": "未確認",
                    "offline_threshold_hours": threshold_hours,
                },
            )

        offline_for = now - last_seen
        if offline_for >= timedelta(hours=threshold_hours):
            return self._raise_alert(
                device_id,
                "device_offline",
                record,
                {
                    "last_seen_at": _format_local_datetime(last_seen),
                    "offline_hours": offline_for.total_seconds() / 3600,
                    "offline_threshold_hours": threshold_hours,
                },
            )
        return self._clear_alert(device_id, "device_offline")

    def _check_watering_missing(self, device_id: str, record: dict, now: datetime):
        if not _is_watering_device(record):
            return self._clear_alert(device_id, "watering_missing")

        threshold_days = int(self.settings.get("watering_missing_after_days") or 2)
        if threshold_days <= 0:
            return self._clear_alert(device_id, "watering_missing")

        last_watering = _last_watering_at(record)
        if last_watering is None:
            first_seen = _parse_datetime(record.get("first_seen_at") or record.get("created_at"))
            reference = first_seen or now
            days_since = (now - reference).total_seconds() / 86400
            if days_since < threshold_days:
                return self._clear_alert(device_id, "watering_missing")
            return self._raise_alert(
                device_id,
                "watering_missing",
                record,
                {
                    "last_watering_at": "未確認",
                    "days_since_watering": days_since,
                    "watering_threshold_days": threshold_days,
                },
            )

        days_since = (now - last_watering).total_seconds() / 86400
        if days_since >= threshold_days:
            return self._raise_alert(
                device_id,
                "watering_missing",
                record,
                {
                    "last_watering_at": _format_local_datetime(last_watering),
                    "days_since_watering": days_since,
                    "watering_threshold_days": threshold_days,
                },
            )
        return self._clear_alert(device_id, "watering_missing")

    def _check_soil_calibration_suggested(self, device_id: str, record: dict):
        if not _is_watering_device(record):
            return self._clear_alert(device_id, "soil_calibration_suggested")

        payload = record.get("last_status") or {}
        if not isinstance(payload, dict) or payload.get("soil_calibration_suggested") is not True:
            return self._clear_alert(device_id, "soil_calibration_suggested")

        return self._raise_alert(
            device_id,
            "soil_calibration_suggested",
            record,
            {
                "soil_raw_before_watering": payload.get("soil_raw_before_watering"),
                "soil_raw_after_watering": payload.get("soil_raw_after_watering"),
                "soil_calibration_dry_raw": payload.get("soil_calibration_dry_raw"),
                "soil_calibration_wet_raw": payload.get("soil_calibration_wet_raw"),
                "soil_calibration_suggested_dry_raw": payload.get("soil_calibration_suggested_dry_raw"),
                "soil_calibration_suggested_wet_raw": payload.get("soil_calibration_suggested_wet_raw"),
                "soil_calibration_applied": payload.get("soil_calibration_applied"),
            },
        )

    def _raise_alert(self, device_id: str, alert_type: str, record: dict, details: dict):
        device_state = self.state.setdefault(device_id, {})
        if device_state.get(alert_type):
            return False
        self.notification_service.notify_health_alert(alert_type, device_id, record, details)
        device_state[alert_type] = {
            "notified_at": datetime.now(UTC).isoformat(),
            "details": details,
        }
        return True

    def _clear_alert(self, device_id: str, alert_type: str):
        device_state = self.state.get(device_id)
        if not device_state or alert_type not in device_state:
            return False
        del device_state[alert_type]
        if not device_state:
            del self.state[device_id]
        return True

    def _clear_device_alerts(self, device_id: str):
        if device_id not in self.state:
            return False
        del self.state[device_id]
        return True

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as file:
                state = json.load(file)
                return state if isinstance(state, dict) else {}
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning("Health monitor state is invalid JSON: %s", self.state_path)
            return {}

    def _save_state(self):
        with open(self.state_path, "w", encoding="utf-8") as file:
            json.dump(self.state, file, ensure_ascii=True, indent=2)


def _is_watering_device(record: dict):
    if record.get("device_kind") == "WTR":
        return True
    config = record.get("runtime_config") or record.get("config") or {}
    return bool(config.get("schedules"))


def _last_watering_at(record: dict):
    for entry in reversed(record.get("status_history") or []):
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        if payload.get("watering_started") is True:
            return _parse_datetime(entry.get("received_at"))
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


def _format_local_datetime(value: datetime):
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


__instance = None


def health_monitor_task():
    global __instance
    if not __instance:
        __instance = HealthMonitorTask()
    return __instance
