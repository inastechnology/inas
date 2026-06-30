from urllib.parse import quote

import ffmpeg

from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.general_log import logger


class CameraConnector:
    DEFAULT_CAMERA_TYPE = "tapo"
    REOLINK_MAIN_STREAM = "main"
    REOLINK_SUB_STREAM = "sub"

    def __init__(self):
        self.camera_device_repository = camera_device_repository()

    def take_picture(self, device_id: str):
        rtsp_url = self.construct_rtsp_url(device_id)
        if not rtsp_url:
            return None

        # take picture
        try:
            # RTSP の入力を受け取り、出力先をパイプに設定。
            # format='image2' で画像出力、vframes=1 で1フレームのみ取得
            img_bytes, _ = (
                ffmpeg.input(rtsp_url, rtsp_transport="tcp").output("pipe:", format="image2", vframes=1).run(capture_stdout=True, capture_stderr=True)
            )
            if not img_bytes:
                logger.error(f"Failed to take picture: {device_id}")
                return None

            return img_bytes  # バイト列として画像データが返される
        except ffmpeg.Error as e:
            print("エラーが発生しました:")
            print(e.stderr.decode())
            return None

    def stream_rtsp(self, device_id: str):
        rtsp_url = self.construct_rtsp_url(device_id)
        if not rtsp_url:
            return None
        logger.info(f"Starting RTSP stream from {device_id}")
        # ffmpeg プロセスを非同期実行（MJPEG 形式で出力）
        process = ffmpeg.input(rtsp_url, rtsp_transport="tcp").output("pipe:", format="mjpeg", r=10).run_async(pipe_stdout=True, pipe_stderr=True)
        if process.poll() is not None:
            logger.error("Failed to start ffmpeg process")
            return

        logger.info(f"[{device_id}]Started ffmpeg process: PID={process.pid}")
        return process

    def stop_stream(self, device_id: str, process):
        if process.poll() is None:
            process.kill()
        process.wait()
        logger.info(f"[{device_id}]Stopped ffmpeg process: PID={process.pid}")
        process.stdout.close()

    def construct_rtsp_url(self, device_id: str):
        info = self.camera_device_repository.get(device_id)
        if not info:
            logger.error(f"Device not found: {device_id}")
            return None
        ip_address = info.get("ip_address")
        username = info.get("username")
        password = info.get("password")
        if not ip_address or not username or not password:
            logger.error(f"Invalid device info: ip_address={ip_address}, username={username}, password=[REDACTED]")
            return None

        return self.get_rtsp_url(
            ip_address,
            username,
            password,
            camera_type=info.get("camera_type") or info.get("type") or self.DEFAULT_CAMERA_TYPE,
            channel=info.get("channel", 1),
            stream=info.get("stream", self.REOLINK_MAIN_STREAM),
            rtsp_path=info.get("rtsp_path"),
        )

    @staticmethod
    def get_rtsp_url(
        ip_address: str,
        username: str,
        password: str,
        camera_type: str = DEFAULT_CAMERA_TYPE,
        channel: int | str = 1,
        stream: str = REOLINK_MAIN_STREAM,
        rtsp_path: str | None = None,
    ):
        encoded_username = quote(username, safe="")
        encoded_password = quote(password, safe="")
        authority = f"{encoded_username}:{encoded_password}@{ip_address}"

        if rtsp_path:
            normalized_path = rtsp_path if rtsp_path.startswith("/") else f"/{rtsp_path}"
            return f"rtsp://{authority}{normalized_path}"

        normalized_camera_type = camera_type.lower().strip()
        if normalized_camera_type == "reolink":
            normalized_stream = stream.lower().strip()
            if normalized_stream not in {CameraConnector.REOLINK_MAIN_STREAM, CameraConnector.REOLINK_SUB_STREAM}:
                raise ValueError(f"Unsupported Reolink stream: {stream}")
            channel_number = int(channel)
            return f"rtsp://{authority}/Preview_{channel_number:02d}_{normalized_stream}"

        if normalized_camera_type == "tapo":
            return f"rtsp://{authority}/stream1"

        raise ValueError(f"Unsupported camera_type: {camera_type}")

    @staticmethod
    def generate_frames(device_id):
        process = camera_connector().stream_rtsp(device_id)
        if process is None:
            return

        buffer = b""
        try:
            while True:
                chunk = process.stdout.read(1024)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")
                    if start != -1 and end != -1 and end > start:
                        frame = buffer[start : end + 2]
                        buffer = buffer[end + 2 :]
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
                    else:
                        break
        except GeneratorExit:
            logger.info(f"[{device_id}]Rtsp client disconnected. Stopping ffmpeg process")
        except Exception as e:
            logger.error(f"Error: {e}")
            raise
        finally:
            camera_connector().stop_stream(device_id, process)


__instance = None


def camera_connector():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = CameraConnector()

    return __instance


if __name__ == "__main__":
    # example
    device_id = "INACD-a0b189d8-d789-4087-96d9-db91ecaf25c0"
    camera = camera_connector()
    img_bytes = camera.take_picture(device_id)
    if img_bytes:
        with open("image.jpg", "wb") as f:
            f.write(img_bytes)
    else:
        print("Failed to take picture")
