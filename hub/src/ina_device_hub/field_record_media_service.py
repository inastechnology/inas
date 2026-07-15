import os
import re
import uuid
from datetime import date
from urllib.parse import quote

from ina_device_hub.storage_connector import storage_connector

MAX_IMAGES_PER_RECORD = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class FieldRecordMediaValidationError(ValueError):
    pass


class FieldRecordMediaStorageError(RuntimeError):
    pass


class FieldRecordMediaService:
    def __init__(self, connector=None):
        self.connector = connector or storage_connector()

    def upload_images(self, field_id: str, occurred_at: str, files: list):
        uploads = [file for file in files if file and getattr(file, "filename", "")]
        if len(uploads) > MAX_IMAGES_PER_RECORD:
            raise FieldRecordMediaValidationError(f"images must contain {MAX_IMAGES_PER_RECORD} files or less")

        prepared = [self._prepare_image(file) for file in uploads]
        uploaded_keys = []
        attachments = []
        record_day = _record_day(occurred_at)
        field_key = _safe_key_part(field_id)
        try:
            for image in prepared:
                attachment_id = str(uuid.uuid4())
                object_key = f"field-records/{field_key}/{record_day}/{attachment_id}.{image['extension']}"
                saved_key = self.connector.save_bytes_to_cloud(object_key, image["bytes"], image["content_type"])
                if not saved_key:
                    raise FieldRecordMediaStorageError("failed to upload an image to R2")
                uploaded_keys.append(saved_key)
                attachments.append(
                    {
                        "id": attachment_id,
                        "storage": "r2",
                        "object_key": saved_key,
                        "content_type": image["content_type"],
                        "size_bytes": len(image["bytes"]),
                        "original_filename": image["filename"],
                        "url": f"/local/api/fields/{quote(field_id, safe='')}/record-images/{attachment_id}",
                    }
                )
        except Exception:
            for object_key in uploaded_keys:
                self.connector.delete_from_cloud(object_key)
            raise
        return attachments

    def fetch_image(self, attachment: dict):
        object_key = str(attachment.get("object_key") or "")
        if not object_key.startswith("field-records/"):
            raise FieldRecordMediaValidationError("invalid field record image key")
        image_bytes = self.connector.fetch_from_cloud_as_bytes(object_key)
        if image_bytes is None:
            raise FieldRecordMediaStorageError("failed to read an image from R2")
        return image_bytes

    def _prepare_image(self, file):
        image_bytes = file.read(MAX_IMAGE_BYTES + 1)
        if not image_bytes:
            raise FieldRecordMediaValidationError("image must not be empty")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise FieldRecordMediaValidationError(f"each image must be {MAX_IMAGE_BYTES // (1024 * 1024)} MB or less")
        content_type, extension = _detect_image_type(image_bytes)
        if not content_type:
            raise FieldRecordMediaValidationError("images must be JPEG, PNG, or WebP")
        filename = os.path.basename(str(file.filename or "image"))[:180]
        return {
            "bytes": image_bytes,
            "content_type": content_type,
            "extension": extension,
            "filename": filename,
        }


def _detect_image_type(value: bytes):
    if value.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if value.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "", ""


def _record_day(value: str):
    candidate = str(value or "")[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return date.today().isoformat()


def _safe_key_part(value: str):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned[:120] or "field"


__instance = None


def field_record_media_service():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = FieldRecordMediaService()
    return __instance
