import json
import mimetypes
import os
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BlockingScheduler

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.general_log import logger
from ina_device_hub.ina_db_connector import InaDBConnector
from ina_device_hub.instagram_client import InstagramClient
from ina_device_hub.instagram_feedback_policy import (
    collect_comment_feedback,
    is_weekly_recap_day,
)
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.timelapse_media_service import timelapse_media_service
from ina_device_hub.weather_forecast_service import weather_forecast_service


class InstagramPostTask:
    INSTAGRAM_VIDEO_MAX_WIDTH = 1080
    INSTAGRAM_VIDEO_MAX_HEIGHT = 1350
    INSTAGRAM_VIDEO_BITRATE = "4M"
    WEEKDAY_NAMES_JA = ["月", "火", "水", "木", "金", "土", "日"]
    WEEKDAY_STYLE_GUIDES = {
        0: "月曜: 新しい週の観察開始として、落ち着いた導入と今週の注目点を1つ入れる。",
        1: "火曜: 変化を具体的に描写し、前日との差分を短く入れる。",
        2: "水曜: 週の中間記録として、成長や姿勢の中間評価を入れる。",
        3: "木曜: 細部観察の日として、葉や茎のディテールを1つ強調する。",
        4: "金曜: 1週間の流れを感じる文脈で、今週の傾向を短くまとめる。",
        5: "土曜: 週末らしく軽快なトーンで、見て楽しい変化を中心に書く。",
        6: "日曜: 週次の振り返りとして、全体の印象をやさしく締める。",
    }

    def __init__(self):
        self.settings = setting()
        self.ai_settings = self.settings.get("ai")
        self.instagram_settings = self.settings.get("instagram")
        self.storage_connector = storage_connector()
        self.timelapse_media_service = timelapse_media_service()
        self.sensor_data_repository = sensor_data_repository(InaDBConnector())
        self.camera_repository = camera_device_repository()
        self.ai_content_service = ai_content_service()
        self.weather_forecast_service = weather_forecast_service(
            forecast_url=self.instagram_settings.get("weather_forecast_url"),
            area_name=self.instagram_settings.get("weather_area_name"),
            office_name=self.instagram_settings.get("weather_office_name"),
            forecast_title=self.instagram_settings.get("weather_forecast_title"),
        )
        self.scheduler = BlockingScheduler()
        self.state_file_path = os.path.join(
            self.settings.get_work_dir(),
            "instagram_post_task_state.json",
        )

    def start(self):
        if not self.is_enabled() or self.scheduler.running:
            return

        hour, minute = self._parse_schedule()
        self.scheduler.add_job(
            self._run,
            "cron",
            hour=hour,
            minute=minute,
            max_instances=1,
        )
        logger.info(f"Start {self.__class__.__name__}(schedule: {hour:02d}:{minute:02d})")
        worker_thread = threading.Thread(target=self.scheduler.start)
        worker_thread.daemon = True
        worker_thread.start()

    def is_enabled(self):
        required_values = [
            self.ai_settings.get("enabled"),
            self.instagram_settings.get("user_id"),
            self.instagram_settings.get("access_token"),
            self.instagram_settings.get("camera_id"),
        ]
        if not all(required_values):
            logger.info("InstagramPostTask is disabled by configuration")
            return False
        if not self.storage_connector.is_temporary_storage_configured():
            logger.warning("Temporary storage is not configured; skip Instagram posting")
            return False
        return True

    def _run(self):
        camera_id = self.instagram_settings.get("camera_id")
        state = self._load_state()
        instagram_client = InstagramClient(
            self.instagram_settings.get("user_id"),
            self.instagram_settings.get("access_token"),
        )
        end_at = datetime.now()
        last_post_at = self._parse_datetime(state.get("last_post_at"))
        is_weekly_recap = self._is_weekly_recap_day(end_at)
        if is_weekly_recap:
            start_at = end_at - timedelta(days=7)
            logger.info(
                f"Weekly recap mode enabled for Sunday post: start_at={start_at.isoformat(timespec='seconds')}, end_at={end_at.isoformat(timespec='seconds')}"
            )
        else:
            start_at = last_post_at + timedelta(seconds=1) if last_post_at else (end_at - timedelta(days=1))

        try:
            publish_result = self._publish_reel_for_window(
                camera_id=camera_id,
                start_at=start_at,
                end_at=end_at,
                state=state,
                instagram_client=instagram_client,
            )
        except RuntimeError:
            if not is_weekly_recap:
                raise
            logger.exception("Weekly recap Instagram post failed; retrying with daily fallback")
            fallback_start_at = last_post_at + timedelta(seconds=1) if last_post_at else (end_at - timedelta(days=1))
            publish_result = self._publish_reel_for_window(
                camera_id=camera_id,
                start_at=fallback_start_at,
                end_at=end_at,
                state=state,
                instagram_client=instagram_client,
                mode="daily_fallback",
            )

        if not publish_result:
            return

        weather_forecast_for_next_post = self._fetch_weather_forecast_for_next_post()
        self._save_state(
            {
                "last_post_at": end_at.isoformat(),
                "last_media_id": publish_result["media_id"],
                "last_video_url": publish_result["video_url"],
                "last_caption": publish_result["caption"],
                "last_post_mode": publish_result["mode"],
                "weather_forecast_used": state.get("weather_forecast_for_next_post") or {},
                "weather_forecast_for_next_post": weather_forecast_for_next_post,
            }
        )
        logger.info(f"Instagram reel published: {publish_result['media_id']}")

    def _publish_reel_for_window(
        self,
        camera_id: str,
        start_at: datetime,
        end_at: datetime,
        state: dict,
        instagram_client: InstagramClient,
        mode: str = "default",
    ):
        video_path = self.timelapse_media_service.create_video(
            camera_id,
            start_at=start_at,
            end_at=end_at,
            max_width=self.INSTAGRAM_VIDEO_MAX_WIDTH,
            max_height=self.INSTAGRAM_VIDEO_MAX_HEIGHT,
            video_bitrate=self.INSTAGRAM_VIDEO_BITRATE,
        )
        if not video_path:
            logger.info(f"Skip Instagram post because no timelapse is available: {camera_id}")
            return

        frame_paths = self.timelapse_media_service.list_frames(
            camera_id,
            start_at=start_at,
            end_at=end_at,
        )
        image_paths = self._select_key_frames(frame_paths)
        image_urls = [self._upload_public_asset(image_path) for image_path in image_paths]
        image_urls = [image_url for image_url in image_urls if image_url]

        video_url = self._upload_public_asset(video_path)
        if not video_url:
            logger.error("Failed to upload timelapse video for Instagram")
            return

        comment_feedback = self._collect_previous_comment_feedback(
            instagram_client=instagram_client,
            previous_media_id=state.get("last_media_id"),
        )
        media_context = self._build_media_context(
            camera_id=camera_id,
            start_at=start_at,
            end_at=end_at,
            frame_paths=frame_paths,
            image_urls=image_urls,
            video_url=video_url,
            comment_feedback=comment_feedback,
            weather_forecast=state.get("weather_forecast_for_next_post") or {},
        )
        caption = self.ai_content_service.generate_instagram_caption(media_context)
        media_id = instagram_client.publish_reel(
            video_url=video_url,
            caption=caption,
            cover_url=image_urls[-1] if image_urls else None,
        )
        return {
            "media_id": media_id,
            "video_url": video_url,
            "caption": caption,
            "mode": mode,
        }

    def _build_media_context(
        self,
        camera_id: str,
        start_at: datetime,
        end_at: datetime,
        frame_paths: list[str],
        image_urls: list[str],
        video_url: str,
        comment_feedback: dict,
        weather_forecast: dict,
    ):
        sensor_id = self.instagram_settings.get("sensor_id")
        sensor_snapshot = {}
        if sensor_id:
            latest_sensor = self.sensor_data_repository.get_latest(sensor_id)
            sensor_snapshot = latest_sensor or {}

        camera_info = self.camera_repository.get(camera_id) or {}
        return {
            "posting_weekday": self._format_weekday(end_at),
            "weekday_style_guide": self._get_weekday_style_guide(end_at),
            "camera_id": camera_id,
            "camera_name": camera_info.get("name", camera_id),
            "frame_count": len(frame_paths),
            "start_at": start_at.isoformat(timespec="seconds"),
            "end_at": end_at.isoformat(timespec="seconds"),
            "image_urls": image_urls,
            "video_url": video_url,
            "sensor_snapshot": sensor_snapshot,
            "plant_position_prompt": self.instagram_settings.get("plant_position_prompt"),
            "comment_feedback": comment_feedback,
            "weather_forecast": weather_forecast,
        }

    def _format_weekday(self, at: datetime):
        index = at.weekday()
        return f"{self.WEEKDAY_NAMES_JA[index]}曜"

    def _get_weekday_style_guide(self, at: datetime):
        return self.WEEKDAY_STYLE_GUIDES.get(
            at.weekday(),
            "曜日に合わせて表現を少し変え、前日投稿と似すぎない語彙を選ぶ。",
        )

    def _is_weekly_recap_day(self, at: datetime):
        # Sunday: use a 7-day window so the weekly recap text matches the media span.
        return is_weekly_recap_day(at.weekday())

    def _collect_previous_comment_feedback(
        self,
        instagram_client: InstagramClient,
        previous_media_id: str | None,
    ):
        if not previous_media_id:
            return {
                "source_media_id": None,
                "admin_username": self._get_admin_username(),
                "admin_instructions": [],
                "general_topics": [],
                "total_comments": 0,
            }

        try:
            comments = instagram_client.get_media_comments(previous_media_id, limit=50)
        except RuntimeError:
            logger.exception("Failed to fetch comments from previous Instagram post")
            comments = []

        feedback = collect_comment_feedback(
            comments,
            admin_username=self._get_admin_username(),
            max_items=10,
        )
        feedback["source_media_id"] = previous_media_id
        return feedback

    def _fetch_weather_forecast_for_next_post(self):
        try:
            forecast = self.weather_forecast_service.fetch_forecast()
        except RuntimeError:
            logger.exception("Failed to fetch weather forecast for next Instagram post")
            return {}
        if not forecast.get("daily_weather"):
            logger.warning("Weather forecast for next Instagram post has no daily weather")
            return {}
        return forecast

    def _get_admin_username(self):
        username = self.instagram_settings.get("admin_username") or "inas_technologies.ja"
        return username.strip().lower()

    def _select_key_frames(self, frame_paths: list[str]):
        if len(frame_paths) <= 3:
            return frame_paths
        midpoint = len(frame_paths) // 2
        return [
            frame_paths[0],
            frame_paths[midpoint],
            frame_paths[-1],
        ]

    def _upload_public_asset(self, local_path: str):
        relative_key = os.path.join(
            "instagram_publish",
            datetime.now().strftime("%Y%m%d"),
            os.path.basename(local_path),
        )
        with open(local_path, "rb") as file:
            file_bytes = file.read()
        content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        uploaded_key = self.storage_connector.save_bytes_to_temporary_cloud(
            relative_key,
            file_bytes,
            content_type=content_type,
        )
        if not uploaded_key:
            return None
        return self.storage_connector.get_temporary_public_url(uploaded_key)

    def _parse_schedule(self):
        schedule = self.ai_settings.get("agent_schedule_start", "09:01")
        hour_str, minute_str = schedule.split(":", maxsplit=1)
        return int(hour_str), int(minute_str)

    def _load_state(self):
        if not os.path.exists(self.state_file_path):
            return {}
        with open(self.state_file_path, encoding="utf-8") as file:
            return json.load(file)

    def _save_state(self, state: dict):
        with open(self.state_file_path, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

    def _parse_datetime(self, value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


__instance = None


def instagram_post_task():
    global __instance
    if not __instance:
        __instance = InstagramPostTask()
    return __instance
