import os
import shutil
import tempfile
import threading
from datetime import datetime
from urllib.parse import quote

import ffmpeg

from ina_device_hub.general_log import logger
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector


class TimelapseMediaService:
    VIDEO_ASPECT_RATIO_WIDTH = 4
    VIDEO_ASPECT_RATIO_HEIGHT = 5

    def __init__(self):
        self.local_storage_base_dir = setting().get("local_storage_base_dir")
        self.storage_connector = storage_connector()
        self._video_lock = threading.Lock()

    def save_frame(
        self,
        device_id: str,
        image_bytes: bytes,
        captured_at: datetime | None = None,
    ):
        captured_at = captured_at or datetime.now()
        relative_path = self.get_frame_relative_path(device_id, captured_at)
        return self.storage_connector.save_bytes_to_local_path(relative_path, image_bytes)

    def get_frame_relative_path(self, device_id: str, captured_at: datetime):
        return os.path.join(
            "timelapse_frames",
            device_id,
            captured_at.strftime("%Y%m%d"),
            captured_at.strftime("%Y%m%d_%H%M%S") + ".jpg",
        )

    def list_frames(
        self,
        device_id: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ):
        device_dir = os.path.join(
            self.local_storage_base_dir,
            "timelapse_frames",
            device_id,
        )
        if not os.path.exists(device_dir):
            return []

        frames = []
        for root, _, files in os.walk(device_dir):
            for file_name in sorted(files):
                if not file_name.endswith(".jpg"):
                    continue
                file_timestamp = self._parse_frame_timestamp(file_name)
                if file_timestamp is None:
                    continue
                if start_at and file_timestamp < start_at:
                    continue
                if end_at and file_timestamp > end_at:
                    continue
                frames.append(os.path.join(root, file_name))
        return sorted(frames)

    def list_frame_records(
        self,
        device_id: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 100,
    ):
        frame_paths = self.list_frames(device_id, start_at=start_at, end_at=end_at)
        records = []
        for frame_path in reversed(frame_paths[-limit:]):
            timestamp = self._parse_frame_timestamp(os.path.basename(frame_path))
            if timestamp is None:
                continue
            relative_path = os.path.relpath(frame_path, self.local_storage_base_dir)
            records.append(
                {
                    "camera_id": device_id,
                    "captured_at": timestamp.isoformat(),
                    "relative_path": relative_path,
                    "url": f"/local/api/camera-images/{quote(relative_path, safe='/')}",
                }
            )
        return records

    def resolve_frame_path(self, relative_path: str):
        normalized = os.path.normpath(relative_path).lstrip(os.sep)
        if not normalized.startswith(os.path.join("timelapse_frames", "")):
            return None
        full_path = os.path.abspath(os.path.join(self.local_storage_base_dir, normalized))
        base_path = os.path.abspath(os.path.join(self.local_storage_base_dir, "timelapse_frames"))
        if not full_path.startswith(base_path + os.sep):
            return None
        if not os.path.isfile(full_path):
            return None
        return full_path

    def create_video(
        self,
        device_id: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        fps: int = 12,
        max_width: int | None = None,
        max_height: int | None = None,
        video_bitrate: str | None = None,
        max_frames: int | None = None,
    ):
        frame_paths = self.list_frames(
            device_id,
            start_at=start_at,
            end_at=end_at,
        )
        if max_frames:
            frame_paths = frame_paths[-max(2, max_frames) :]
        if len(frame_paths) < 2:
            return None

        output_relative_path = self.get_video_relative_path(device_id, end_at or datetime.now())
        output_path = os.path.join(self.local_storage_base_dir, output_relative_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="timelapse-") as staging_dir:
            for index, frame_path in enumerate(frame_paths, start=1):
                staged_path = os.path.join(staging_dir, f"frame_{index:06d}.jpg")
                shutil.copyfile(frame_path, staged_path)

            input_pattern = os.path.join(staging_dir, "frame_%06d.jpg")
            try:
                video_input = ffmpeg.input(input_pattern, framerate=fps, start_number=1)
                video_output = video_input.filter(
                    "crop",
                    f"min(iw,ih*{self.VIDEO_ASPECT_RATIO_WIDTH}/{self.VIDEO_ASPECT_RATIO_HEIGHT})",
                    f"min(ih,iw*{self.VIDEO_ASPECT_RATIO_HEIGHT}/{self.VIDEO_ASPECT_RATIO_WIDTH})",
                    "(iw-ow)/2",
                    "(ih-oh)/2",
                )
                if max_width and max_height:
                    video_output = video_output.filter(
                        "scale",
                        f"min(iw,{max_width})",
                        f"min(ih,{max_height})",
                        force_original_aspect_ratio="decrease",
                    )
                video_output = video_output.filter(
                    "scale",
                    "trunc(iw/2)*2",
                    "trunc(ih/2)*2",
                ).filter("format", "yuv420p")

                output_options = {
                    "vcodec": "libx264",
                    "pix_fmt": "yuv420p",
                    "movflags": "+faststart",
                }
                if video_bitrate:
                    output_options["video_bitrate"] = video_bitrate

                (
                    video_output.output(
                        output_path,
                        **output_options,
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error as error:
                logger.error(error.stderr.decode())
                try:
                    if os.path.isfile(output_path):
                        os.remove(output_path)
                except OSError:
                    logger.warning("Could not remove incomplete timelapse video: %s", output_path)
                return None

        return output_path

    def ensure_recent_video(
        self,
        device_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
        fps: int = 8,
        max_frames: int = 96,
    ):
        frame_paths = self.list_frames(device_id, start_at=start_at, end_at=end_at)
        frame_paths = frame_paths[-max(2, max_frames) :]
        if len(frame_paths) < 2:
            return None

        latest_frame_at = self._parse_frame_timestamp(os.path.basename(frame_paths[-1]))
        if latest_frame_at is None:
            return None
        relative_path = self.get_video_relative_path(device_id, latest_frame_at)
        output_path = os.path.join(self.local_storage_base_dir, relative_path)
        with self._video_lock:
            if not self._is_nonempty_file(output_path):
                output_path = self.create_video(
                    device_id,
                    start_at=start_at,
                    end_at=latest_frame_at,
                    fps=fps,
                    max_width=960,
                    max_height=1200,
                    video_bitrate="1800k",
                    max_frames=max_frames,
                )
            if not output_path:
                return None
        return {
            "camera_id": device_id,
            "captured_at": latest_frame_at.isoformat(),
            "frame_count": len(frame_paths),
            "relative_path": relative_path,
            "url": f"/local/api/camera-videos/{quote(relative_path, safe='/')}",
        }

    def list_video_records(self, device_id: str, limit: int = 20):
        device_dir = os.path.join(
            self.local_storage_base_dir,
            "timelapse_videos",
            device_id,
        )
        if not os.path.exists(device_dir):
            return []

        records = []
        for root, _, files in os.walk(device_dir):
            for file_name in files:
                if not file_name.endswith(".mp4"):
                    continue
                timestamp = self._parse_video_timestamp(file_name)
                if timestamp is None:
                    continue
                full_path = os.path.join(root, file_name)
                if not self._is_nonempty_file(full_path):
                    continue
                relative_path = os.path.relpath(full_path, self.local_storage_base_dir)
                records.append(
                    {
                        "camera_id": device_id,
                        "captured_at": timestamp.isoformat(),
                        "relative_path": relative_path,
                        "url": f"/local/api/camera-videos/{quote(relative_path, safe='/')}",
                    }
                )
        return sorted(records, key=lambda item: item["captured_at"], reverse=True)[: max(1, limit)]

    def resolve_video_path(self, relative_path: str):
        normalized = os.path.normpath(relative_path).lstrip(os.sep)
        if not normalized.startswith(os.path.join("timelapse_videos", "")):
            return None
        full_path = os.path.abspath(os.path.join(self.local_storage_base_dir, normalized))
        base_path = os.path.abspath(os.path.join(self.local_storage_base_dir, "timelapse_videos"))
        if not full_path.startswith(base_path + os.sep):
            return None
        if not self._is_nonempty_file(full_path):
            return None
        return full_path

    def get_video_relative_path(self, device_id: str, captured_at: datetime):
        return os.path.join(
            "timelapse_videos",
            device_id,
            captured_at.strftime("%Y%m%d"),
            captured_at.strftime("%Y%m%d_%H%M%S") + ".mp4",
        )

    def _parse_frame_timestamp(self, file_name: str):
        stem, _ = os.path.splitext(file_name)
        try:
            return datetime.strptime(stem, "%Y%m%d_%H%M%S")
        except ValueError:
            return None

    def _parse_video_timestamp(self, file_name: str):
        return self._parse_frame_timestamp(file_name)

    @staticmethod
    def _is_nonempty_file(path: str):
        try:
            return os.path.isfile(path) and os.path.getsize(path) > 0
        except OSError:
            return False


__instance = None


def timelapse_media_service():
    global __instance
    if not __instance:
        __instance = TimelapseMediaService()
    return __instance
