import json
import os
import threading
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.discord_notification_service import discord_notification_service
from ina_device_hub.field_repository import field_repository
from ina_device_hub.general_log import logger
from ina_device_hub.json_repository_io import atomic_write_json
from ina_device_hub.plant_management_repository import plant_management_repository
from ina_device_hub.setting import setting

NOTIFICATION_TIMEZONE = ZoneInfo("Asia/Tokyo")


class PlantTaskNotificationTask:
    def __init__(
        self,
        plant_repository=None,
        field_repo=None,
        notification_service=None,
        state_path=None,
        settings_provider=None,
    ):
        self.plant_repository = plant_repository or plant_management_repository()
        self.field_repository = field_repo or field_repository()
        self.notification_service = notification_service or discord_notification_service()
        self.state_path = state_path or os.path.join(setting().get_work_dir(), ".plant_task_notification_state.json")
        self.settings_provider = settings_provider or (lambda: setting().get("discord") or {})
        self.state = self._load_state()
        self.scheduler = BlockingScheduler(timezone=NOTIFICATION_TIMEZONE)
        self.worker_thread = None

    def start(self):
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self.run_once,
            "cron",
            hour=4,
            minute=0,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        logger.info("Start %s(daily at 04:00 Asia/Tokyo)", self.__class__.__name__)
        self.worker_thread = threading.Thread(target=self.scheduler.start, daemon=True)
        self.worker_thread.start()

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
        if self.worker_thread:
            self.worker_thread.join()

    def run_once(self, now: datetime | None = None):
        current = (now or datetime.now(UTC)).astimezone(NOTIFICATION_TIMEZONE)
        digest_date = current.date().isoformat()
        if self.state.get("last_digest_date") == digest_date:
            return False

        preferences = _notification_preferences(self.settings_provider())
        inventory = self.plant_repository.list_notification_actions(
            today=digest_date,
            lead_days=preferences["reminder_days_before"],
        )
        current_ids = {item["action"]["id"] for item in inventory}
        initialized = bool(self.state.get("initialized"))
        known_ids = set(self.state.get("known_action_ids") or [])
        new_ids = current_ids - known_ids if initialized else set()

        if not initialized:
            self.state["initialized"] = True
            self.state["known_action_ids"] = sorted(current_ids)
            known_ids = current_ids
            self._save_state()

        field_names = {field.get("id"): field.get("name") for field in self.field_repository.list()}
        prepared = []
        for item in inventory:
            prepared_item = {
                **item,
                "field_name": field_names.get(item.get("field_id")) or item.get("field_id"),
                "is_new": item["action"]["id"] in new_ids,
                "timing_state": _notification_timing_state(item, current.date(), preferences),
            }
            prepared.append(prepared_item)

        digest = {
            "date": digest_date,
            "due": [item for item in prepared if item.get("timing_state") == "due"],
            "upcoming": [item for item in prepared if item.get("timing_state") == "upcoming"],
            "new": [item for item in prepared if preferences["notify_new"] and item.get("is_new") and item.get("timing_state") is None],
            "reminder": {
                "days_before": preferences["reminder_days_before"],
                "on_start_day": preferences["notify_on_start_day"],
                "during_window": preferences["notify_during_window"],
            },
        }
        has_items = any(digest[key] for key in ("due", "upcoming", "new"))
        if has_items and not self.notification_service.notify_plant_task_digest(digest):
            return False

        self.state["initialized"] = True
        self.state["known_action_ids"] = sorted(known_ids | current_ids)
        self.state["last_digest_date"] = digest_date
        self.state["last_successful_at"] = current.isoformat()
        self._save_state()
        return has_items

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as file:
                value = json.load(file)
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        atomic_write_json(self.state_path, self.state)


def _notification_preferences(value):
    source = value if isinstance(value, dict) else {}
    try:
        reminder_days = int(source.get("plant_task_reminder_days_before", 7))
    except (TypeError, ValueError):
        reminder_days = 7
    return {
        "notify_new": bool(source.get("plant_task_notify_new", True)),
        "reminder_days_before": max(0, min(30, reminder_days)),
        "notify_on_start_day": bool(source.get("plant_task_notify_on_start_day", True)),
        "notify_during_window": bool(source.get("plant_task_notify_during_window", True)),
    }


def _notification_timing_state(item, today: date, preferences):
    action = item.get("action") if isinstance(item.get("action"), dict) else {}
    try:
        window_start = date.fromisoformat(str(action.get("window_start") or ""))
        window_end = date.fromisoformat(str(action.get("window_end") or action.get("window_start") or ""))
    except ValueError:
        return None
    window_end = max(window_end, window_start)
    days_until_start = (window_start - today).days
    if days_until_start > 0:
        reminder_days = preferences["reminder_days_before"]
        return "upcoming" if reminder_days > 0 and days_until_start == reminder_days else None
    if days_until_start == 0:
        return "due" if preferences["notify_on_start_day"] else None
    if today <= window_end and preferences["notify_during_window"]:
        return "due"
    return None


__instance = None


def plant_task_notification_task():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = PlantTaskNotificationTask()
    return __instance
