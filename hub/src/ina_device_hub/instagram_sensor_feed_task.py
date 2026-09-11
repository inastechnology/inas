import json
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.general_log import logger
from ina_device_hub.instagram_client import InstagramClient
from ina_device_hub.json_repository_io import atomic_write_json
from ina_device_hub.sensor_measurement_repository import sensor_measurement_repository
from ina_device_hub.sensor_trend_card_service import SensorTrendCardService, default_sensor_trend_window
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector


class InstagramSensorFeedTask:
    JOB_ID = "instagram-sensor-feed"
    DEFAULT_SCHEDULE = "20:00"
    ELIGIBLE_DEVICE_KINDS = {"ENV", "SOI", "WTR", "WRS", "FGT"}
    HISTORY_LIMIT = 7

    def __init__(self):
        self.settings = setting()
        self.instagram_settings = self.settings.get("instagram") or {}
        self.storage_connector = storage_connector()
        self.measurement_repository = sensor_measurement_repository()
        self.device_service = device_config_service()
        self.ai_content_service = ai_content_service()
        self.card_service = SensorTrendCardService()
        self.timezone = self._load_timezone()
        self.scheduler = BlockingScheduler(timezone=self.timezone)
        self.state_file_path = os.path.join(self.settings.get_work_dir(), "instagram_sensor_feed_task_state.json")

    def start(self):
        if not self.is_enabled() or self.scheduler.running:
            return
        hour, minute = self._parse_schedule()
        self.scheduler.add_job(
            self._run,
            "cron",
            id=self.JOB_ID,
            hour=hour,
            minute=minute,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30 * 60,
        )
        logger.info(f"Start {self.__class__.__name__}(schedule: {hour:02d}:{minute:02d})")
        worker_thread = threading.Thread(target=self.scheduler.start, daemon=True)
        worker_thread.start()

    def reload_settings(self):
        self.instagram_settings = self.settings.get("instagram") or {}
        if self.scheduler.running and not self.is_enabled():
            self.scheduler.shutdown(wait=False)
            self.scheduler = BlockingScheduler(timezone=self.timezone)
            return
        if not self.scheduler.running:
            self.start()
            return
        hour, minute = self._parse_schedule()
        self.scheduler.reschedule_job(self.JOB_ID, trigger="cron", hour=hour, minute=minute)

    def is_enabled(self):
        if self.instagram_settings.get("posting_paused") or not self.instagram_settings.get("sensor_feed_enabled"):
            return False
        required_values = [self.instagram_settings.get("user_id"), self.instagram_settings.get("access_token")]
        if not all(required_values):
            logger.info("InstagramSensorFeedTask is disabled by configuration")
            return False
        if not self.storage_connector.is_temporary_storage_configured():
            logger.warning("Temporary storage is not configured; skip Instagram sensor feed posting")
            return False
        return True

    def _run(self):
        if not self.is_enabled():
            logger.info("Skip Instagram sensor feed because automatic posting is disabled")
            return
        try:
            self.publish_for_window(datetime.now(self.timezone))
        except Exception:
            logger.exception("Instagram sensor feed post failed")

    def publish_for_window(self, end_at: datetime, instagram_client: InstagramClient | None = None):
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=self.timezone)
        else:
            end_at = end_at.astimezone(self.timezone)
        start_at, end_at = default_sensor_trend_window(end_at)
        device_ids, device_names = self._sensor_sources()
        if not device_ids:
            logger.warning("Skip Instagram sensor feed because no eligible sensor device is registered")
            return None

        measurements = self.measurement_repository.between_for_devices(
            device_ids,
            start_at.isoformat(),
            end_at.isoformat(),
            limit=20000,
        )
        series = self.card_service.build_series(
            measurements,
            start_at=start_at,
            end_at=end_at,
            device_names=device_names,
        )
        if not series:
            logger.info("Skip Instagram sensor feed because no target measurements are available")
            return None

        previous_state = self._load_state()
        recent_posts = self._recent_posts(previous_state)
        recent_impressions = [post["impression"] for post in recent_posts if post.get("impression")]
        editorial_context = self.card_service.build_editorial_context(
            series,
            end_at=end_at,
            previous_focus_metric=previous_state.get("last_focus_metric"),
        )
        series = self.card_service.prioritize_series(series, editorial_context)
        raw_impression = self.ai_content_service.generate_sensor_trend_impression(
            self.card_service.summarize_for_ai(series),
            editorial_context=editorial_context,
            recent_impressions=recent_impressions,
        )
        impression = self.card_service.choose_impression(
            raw_impression,
            series,
            editorial_context=editorial_context,
            recent_impressions=recent_impressions,
        )
        image_bytes = self.card_service.render_jpeg(
            series,
            impression,
            start_at=start_at,
            end_at=end_at,
            editorial_context=editorial_context,
        )
        image_url = self._upload_public_image(image_bytes, end_at)
        if not image_url:
            raise RuntimeError("Failed to upload Instagram sensor trend image")
        caption = self.card_service.build_caption(
            series,
            impression,
            start_at=start_at,
            end_at=end_at,
            editorial_context=editorial_context,
        )
        instagram_client = instagram_client or InstagramClient(
            self.instagram_settings.get("user_id"),
            self.instagram_settings.get("access_token"),
        )
        media_id = instagram_client.post_photo(image_url=image_url, caption=caption)
        result = {
            "last_post_at": end_at.isoformat(),
            "last_media_id": media_id,
            "last_image_url": image_url,
            "last_impression": impression,
            "last_caption": caption,
            "last_focus_metric": editorial_context.get("focus_metric"),
            "last_editorial_angle": editorial_context.get("angle"),
            "last_metrics": [item["metric"] for item in series],
            "last_source_device_ids": sorted({item["device_id"] for item in series}),
        }
        result["recent_posts"] = (
            recent_posts
            + [
                {
                    "posted_at": end_at.isoformat(),
                    "impression": impression,
                    "focus_metric": editorial_context.get("focus_metric"),
                    "editorial_angle": editorial_context.get("angle"),
                }
            ]
        )[-self.HISTORY_LIMIT :]
        atomic_write_json(self.state_file_path, result)
        logger.info(f"Instagram sensor feed published: {media_id}")
        return result

    def _sensor_sources(self):
        records = self.device_service.get_all_records() or {}
        selected_sensor_id = str(self.instagram_settings.get("sensor_id") or "").strip()
        if selected_sensor_id:
            record = records.get(selected_sensor_id) or {}
            return [selected_sensor_id], {selected_sensor_id: record.get("name") or selected_sensor_id}

        eligible = {
            str(device_id): record or {}
            for device_id, record in records.items()
            if str((record or {}).get("device_kind") or "").upper() in self.ELIGIBLE_DEVICE_KINDS and (record or {}).get("state") != "retired"
        }
        return sorted(eligible), {device_id: record.get("name") or device_id for device_id, record in eligible.items()}

    def _upload_public_image(self, image_bytes: bytes, end_at: datetime):
        relative_key = os.path.join(
            "instagram_publish",
            end_at.strftime("%Y%m%d"),
            f"sensor-trend-{end_at:%H%M%S}.jpg",
        )
        uploaded_key = self.storage_connector.save_bytes_to_temporary_cloud(relative_key, image_bytes, content_type="image/jpeg")
        if not uploaded_key:
            return None
        return self.storage_connector.get_temporary_public_url(uploaded_key)

    def _parse_schedule(self):
        schedule = self.instagram_settings.get("sensor_feed_schedule_start", self.DEFAULT_SCHEDULE)
        hour_str, minute_str = schedule.split(":", maxsplit=1)
        return int(hour_str), int(minute_str)

    def _load_state(self):
        if not os.path.exists(self.state_file_path):
            return {}
        try:
            with open(self.state_file_path, encoding="utf-8") as file:
                state = json.load(file)
        except (OSError, ValueError):
            logger.warning("Could not read Instagram sensor feed state; starting a new post history")
            return {}
        return state if isinstance(state, dict) else {}

    def _recent_posts(self, state: dict):
        recent_posts = [post for post in (state.get("recent_posts") or []) if isinstance(post, dict)]
        if not recent_posts and state.get("last_impression"):
            recent_posts = [
                {
                    "posted_at": state.get("last_post_at"),
                    "impression": state.get("last_impression"),
                    "focus_metric": state.get("last_focus_metric"),
                    "editorial_angle": state.get("last_editorial_angle"),
                }
            ]
        return recent_posts[-self.HISTORY_LIMIT :]

    def _load_timezone(self):
        timezone_name = str((self.settings.get("weather") or {}).get("timezone") or "Asia/Tokyo")
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning(f"Unknown Hub timezone for Instagram sensor feed: {timezone_name}; using Asia/Tokyo")
            return ZoneInfo("Asia/Tokyo")


__instance = None


def instagram_sensor_feed_task():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = InstagramSensorFeedTask()
    return __instance


def reload_instagram_sensor_feed_task_settings():
    if __instance:
        __instance.reload_settings()
