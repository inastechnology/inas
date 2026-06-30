import json
import time
from urllib import error, parse, request

from ina_device_hub.general_log import logger


class InstagramClient:
    DEFAULT_API_VERSION = "v22.0"
    DEFAULT_TIMEOUT_PHOTO = 300
    DEFAULT_INTERVAL_PHOTO = 5
    DEFAULT_TIMEOUT_REEL = 600
    DEFAULT_INTERVAL_REEL = 10
    DEFAULT_RETRY_LIMIT = 3

    def __init__(
        self,
        user_id: str,
        access_token: str,
        api_version: str | None = None,
    ):
        self.user_id = user_id
        self.access_token = access_token
        self.api_version = api_version or self.DEFAULT_API_VERSION
        self.graph_base_url = f"https://graph.facebook.com/{self.api_version}"
        self.timeout_photo = self.DEFAULT_TIMEOUT_PHOTO
        self.interval_photo = self.DEFAULT_INTERVAL_PHOTO
        self.timeout_reel = self.DEFAULT_TIMEOUT_REEL
        self.interval_reel = self.DEFAULT_INTERVAL_REEL
        self.retry_limit = self.DEFAULT_RETRY_LIMIT

    def post_photo(self, image_url: str, caption: str = ""):
        payload = {
            "image_url": image_url,
            "caption": caption,
        }
        return self._post_media(
            payload,
            timeout=self.timeout_photo,
            interval=self.interval_photo,
        )

    def publish_reel(
        self,
        video_url: str,
        caption: str,
        cover_url: str | None = None,
    ):
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        }
        if cover_url:
            payload["cover_url"] = cover_url

        return self._post_media(
            payload,
            timeout=self.timeout_reel,
            interval=self.interval_reel,
        )

    def get_media_comments(self, media_id: str, limit: int = 50):
        query = {
            "fields": "id,text,username,timestamp,like_count,replies{id,text,username,timestamp}",
            "limit": str(limit),
        }
        response = self._get(f"/{media_id}/comments", query)
        comments = list(response.get("data") or [])
        next_url = (response.get("paging") or {}).get("next")
        while next_url and len(comments) < limit:
            next_response = self._get_url(next_url)
            comments.extend(next_response.get("data") or [])
            next_url = (next_response.get("paging") or {}).get("next")
        return comments[:limit]

    def _post_media(
        self,
        create_params: dict,
        *,
        timeout: int,
        interval: int,
    ):
        for retry in range(1, self.retry_limit + 1):
            try:
                creation_id = self._create_container(create_params)
                logger.info(f"Waiting for media container {creation_id} to finish")
                self._wait_until_finished(
                    creation_id,
                    timeout=timeout,
                    interval=interval,
                )
                time.sleep(1)
                return self._publish_container(creation_id)
            except Exception as exc:
                logger.error(f"Error posting media: {exc}")
                if retry >= self.retry_limit:
                    raise RuntimeError("Failed to post media after multiple attempts") from exc
                logger.warning(f"Retrying Instagram media post ({retry}/{self.retry_limit})")
                time.sleep(retry * 2 + 1)

        raise RuntimeError("Failed to post media after retries")

    def _create_container(self, payload: dict):
        logger.info(f"Creating Instagram media container with payload: {json.dumps(payload, ensure_ascii=False)}")
        response = self._post(f"/{self.user_id}/media", payload)
        creation_id = response.get("id")
        if not creation_id:
            raise RuntimeError("Instagram media container was not created")
        return creation_id

    def _wait_until_finished(self, creation_id: str, timeout: int, interval: int):
        started_at = time.time()
        poll_count = 0
        while True:
            response = self._get(
                f"/{creation_id}",
                {"fields": "status_code,status"},
            )
            status_code = response.get("status_code")
            if status_code == "FINISHED":
                logger.info(f"Instagram media container is ready: {creation_id}")
                return
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(json.dumps(response))
            if time.time() - started_at > timeout:
                raise TimeoutError("Instagram media container did not finish in time")
            poll_count += 1
            logger.info(f"Polling Instagram container {creation_id}: status_code={status_code}, count={poll_count}")
            time.sleep(interval)

    def _publish_container(self, creation_id: str):
        response = self._post(
            f"/{self.user_id}/media_publish",
            {"creation_id": creation_id},
        )
        media_id = response.get("id")
        if not media_id:
            raise RuntimeError("Instagram media container publish failed")
        return media_id

    def _get(self, path: str, params: dict | None = None):
        query = params or {}
        query["access_token"] = self.access_token
        url = f"{self.graph_base_url}{path}?{parse.urlencode(query)}"
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail) from exc

    def _post(self, path: str, payload: dict):
        body = dict(payload)
        body["access_token"] = self.access_token
        data = parse.urlencode(body).encode("utf-8")
        req = request.Request(
            f"{self.graph_base_url}{path}",
            data=data,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail) from exc

    def _get_url(self, url: str):
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail) from exc
