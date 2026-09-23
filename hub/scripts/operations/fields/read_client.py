"""Typed collection operations; callers never need browser URLs or storage keys."""

import re

from common.api_client import OperationsApiClient, OperationsApiError


def _id(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,179}", value):
        raise OperationsApiError("invalid resource identifier")
    return value


class FieldReadClient:
    def __init__(self, api: OperationsApiClient):
        self.api = api

    def list_fields(self, *, cursor: str = "", limit: int = 50):
        return self.api.get("fields", query={"cursor": cursor, "limit": limit})

    def search_records(
        self, field_id: str, *, query: str = "", source: str = "", date_from: str = "", date_to: str = "", since: str = "", cursor: str = "", limit: int = 50
    ):
        return self.api.get(
            f"fields/{_id(field_id)}/records",
            query={"q": query, "source": source, "date_from": date_from, "date_to": date_to, "since": since, "cursor": cursor, "limit": limit},
        )

    def list_cameras(self, field_id: str, *, cursor: str = "", limit: int = 50):
        return self.api.get(f"fields/{_id(field_id)}/cameras", query={"cursor": cursor, "limit": limit})

    def list_camera_images(self, field_id: str, camera_id: str, *, date_from: str = "", date_to: str = "", cursor: str = "", limit: int = 50):
        return self.api.get(
            f"fields/{_id(field_id)}/cameras/{_id(camera_id)}/images",
            query={"date_from": date_from, "date_to": date_to, "cursor": cursor, "limit": limit},
        )

    def camera_image(self, field_id: str, camera_id: str, image_id: str):
        return self.api.get_image(f"fields/{_id(field_id)}/cameras/{_id(camera_id)}/images/{_id(image_id)}")

    def record_image(self, field_id: str, attachment_id: str):
        return self.api.get_image(f"fields/{_id(field_id)}/record-images/{_id(attachment_id)}")
