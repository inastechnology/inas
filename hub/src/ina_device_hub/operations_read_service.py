"""Authorized collection of field records and stored images, independent of Flask."""

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

from ina_device_hub.collection_search import matches_search, search_terms
from ina_device_hub.field_layout_repository import field_layout_repository
from ina_device_hub.field_record_media_service import MAX_IMAGE_BYTES, field_record_media_service
from ina_device_hub.field_repository import field_repository
from ina_device_hub.operations_access import IDENTIFIER, ReadGrant
from ina_device_hub.timelapse_media_service import timelapse_media_service

API_PREFIX = "/operations/api/v1"
FRAME_ID = re.compile(r"\d{8}_\d{6}\Z")


class OperationsReadError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise OperationsReadError("invalid resource identifier")
    return value


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC).isoformat()
    except (ValueError, TypeError) as exc:
        raise OperationsReadError("since must be an ISO 8601 timestamp with a timezone") from exc


def _dates(date_from: str, date_to: str):
    for value in (date_from, date_to):
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise OperationsReadError("dates must use YYYY-MM-DD") from exc
    if date_from and date_to and date_from > date_to:
        raise OperationsReadError("date_from must be on or before date_to")


def _page(items: list[dict], *, cursor: str, limit, context: dict, key):
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise OperationsReadError("limit must be an integer from 1 to 100") from exc
    if not 1 <= limit <= 100:
        raise OperationsReadError("limit must be an integer from 1 to 100")
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    after = None
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError
            value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if value["query"] != fingerprint or not isinstance(value["after"], list) or not all(isinstance(item, str) for item in value["after"]):
                raise ValueError
            after = tuple(value["after"])
            if len(after) != context["key_size"]:
                raise ValueError
        except (ValueError, TypeError, KeyError, binascii.Error, RecursionError) as exc:
            raise OperationsReadError("invalid cursor or changed query") from exc
    ordered = sorted(items, key=key)
    if after is not None:
        ordered = [item for item in ordered if key(item) > after]
    selected = ordered[:limit]
    has_more = len(ordered) > limit
    next_cursor = None
    if has_more:
        next_cursor = base64.urlsafe_b64encode(json.dumps({"query": fingerprint, "after": key(selected[-1])}, separators=(",", ":")).encode()).decode()
    return {"items": selected, "count": len(selected), "has_more": has_more, "next_cursor": next_cursor}


class OperationsReadService:
    def __init__(self, fields=None, layouts=None, frames=None, attachments=None):
        self.fields = fields if fields is not None else field_repository()
        self._layouts = layouts
        self._frames = frames
        self._attachments = attachments

    @property
    def layouts(self):
        if self._layouts is None:
            self._layouts = field_layout_repository()
        return self._layouts

    @property
    def frames(self):
        if self._frames is None:
            self._frames = timelapse_media_service()
        return self._frames

    def _field(self, grant: ReadGrant, field_id: str, scope: str):
        grant.require(scope, field_id)
        _identifier(field_id)
        field = self.fields.get(field_id)
        if field is None:
            raise OperationsReadError("field not found", 404)
        return field

    def list_fields(self, grant: ReadGrant, *, cursor="", limit=50):
        items = [
            {key: field.get(key) or "" for key in ("id", "name", "crop", "stage", "updated_at")}
            for field in self.fields.list()
            if grant.allows_field(str(field.get("id") or ""))
        ]
        return _page(items, cursor=cursor, limit=limit, context={"type": "fields", "key_size": 1}, key=lambda item: (item["id"],))

    def search_records(self, grant: ReadGrant, field_id: str, *, query="", source="", date_from="", date_to="", since="", cursor="", limit=50):
        self._field(grant, field_id, "records:read")
        _dates(date_from, date_to)
        if source not in {"", "note", "event"}:
            raise OperationsReadError("source must be note or event")
        if len(query) > 200:
            raise OperationsReadError("query must contain at most 200 characters")
        since = _timestamp(since) if since else ""
        terms = search_terms(query)
        records = []
        for item in self.fields.list_record_items(field_id):
            created_at = _timestamp(item["created_at"]) if item.get("created_at") else ""
            occurred_day = str(item.get("occurred_at") or "")[:10]
            if source and item["source"] != source:
                continue
            if (date_from and occurred_day < date_from) or (date_to and occurred_day > date_to) or (since and created_at < since):
                continue
            if not matches_search(terms, [item.get(key) for key in ("title", "body", "tags", "kind", "target_name")]):
                continue
            records.append(
                {
                    **{key: item.get(key) for key in ("id", "source", "kind", "occurred_at", "title", "body", "rating", "tags", "record_values")},
                    "field_id": field_id,
                    "created_at": created_at,
                    "attachments": [self._attachment_summary(field_id, attachment) for attachment in item.get("attachments") or []],
                }
            )
        context = {
            "type": "records",
            "field_id": field_id,
            "query": query,
            "source": source,
            "date_from": date_from,
            "date_to": date_to,
            "since": since,
            "key_size": 3,
        }
        return _page(records, cursor=cursor, limit=limit, context=context, key=lambda item: (item["created_at"], item["source"], item["id"]))

    @staticmethod
    def _attachment_summary(field_id: str, attachment: dict):
        attachment_id = _identifier(str(attachment.get("id") or ""))
        return {
            "id": attachment_id,
            "content_type": attachment.get("content_type"),
            "size_bytes": attachment.get("size_bytes"),
            "original_filename": attachment.get("original_filename"),
            "url": f"{API_PREFIX}/fields/{quote(field_id, safe='')}/record-images/{quote(attachment_id, safe='')}",
        }

    def _camera_ids(self, field: dict):
        layout = self.layouts.get(field["id"], field_name=field.get("name", ""))
        bindings = [placement.get("binding") or {} for space in layout.get("spaces") or [] for placement in space.get("placements") or []]
        # Match the Hub UI: populated layout bindings supersede legacy assignments.
        if any(binding.get("device_id") for binding in bindings):
            candidates = [binding.get("device_id") for binding in bindings if binding.get("resource_type") == "camera"]
        else:
            candidates = field.get("camera_device_ids") or []
        return sorted({value for value in candidates if isinstance(value, str) and IDENTIFIER.fullmatch(value)})

    def list_cameras(self, grant: ReadGrant, field_id: str, *, cursor="", limit=50):
        field = self._field(grant, field_id, "images:read")
        items = [{"id": camera_id, "field_id": field_id} for camera_id in self._camera_ids(field)]
        return _page(items, cursor=cursor, limit=limit, context={"type": "cameras", "field_id": field_id, "key_size": 1}, key=lambda item: (item["id"],))

    def _camera(self, grant: ReadGrant, field_id: str, camera_id: str):
        field = self._field(grant, field_id, "images:read")
        _identifier(camera_id)
        if camera_id not in self._camera_ids(field):
            raise OperationsReadError("camera is not assigned to this field", 404)

    def list_camera_images(self, grant: ReadGrant, field_id: str, camera_id: str, *, date_from="", date_to="", cursor="", limit=50):
        self._camera(grant, field_id, camera_id)
        _dates(date_from, date_to)
        items = []
        for filename in self.frames.list_frames(camera_id):
            image_id = Path(filename).stem
            if not FRAME_ID.fullmatch(image_id):
                continue
            captured_at = datetime.strptime(image_id, "%Y%m%d_%H%M%S").isoformat()
            if (date_from and captured_at[:10] < date_from) or (date_to and captured_at[:10] > date_to):
                continue
            path = self._frame_path(camera_id, image_id)
            if path is None:
                continue
            items.append(
                {
                    "id": image_id,
                    "camera_id": camera_id,
                    "field_id": field_id,
                    "captured_at": captured_at,
                    "time_basis": "hub_local",
                    "content_type": "image/jpeg",
                    "size_bytes": path.stat().st_size,
                    "url": f"{API_PREFIX}/fields/{field_id}/cameras/{camera_id}/images/{image_id}",
                }
            )
        context = {"type": "frames", "field_id": field_id, "camera_id": camera_id, "date_from": date_from, "date_to": date_to, "key_size": 1}
        return _page(items, cursor=cursor, limit=limit, context=context, key=lambda item: (item["id"],))

    def _frame_path(self, camera_id: str, image_id: str):
        relative_path = f"timelapse_frames/{camera_id}/{image_id[:8]}/{image_id}.jpg"
        resolved = self.frames.resolve_frame_path(relative_path)
        if resolved is None:
            return None
        path = Path(resolved).resolve()
        camera_dir = (Path(self.frames.local_storage_base_dir) / "timelapse_frames" / camera_id).absolute()
        # Resolve against the lexical camera directory, so symlink escapes fail too.
        if not path.is_relative_to(camera_dir) or not path.is_file():
            return None
        return path

    def camera_image(self, grant: ReadGrant, field_id: str, camera_id: str, image_id: str):
        self._camera(grant, field_id, camera_id)
        if not FRAME_ID.fullmatch(image_id):
            raise OperationsReadError("invalid image identifier")
        path = self._frame_path(camera_id, image_id)
        if path is None:
            raise OperationsReadError("image not found", 404)
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
        return self._image(data, "image/jpeg")

    def record_image(self, grant: ReadGrant, field_id: str, attachment_id: str):
        field = self._field(grant, field_id, "images:read")
        _identifier(attachment_id)
        for record in [*(field.get("notes") or []), *(field.get("events") or [])]:
            for attachment in record.get("attachments") or []:
                if attachment.get("id") != attachment_id:
                    continue
                object_key = str(attachment.get("object_key") or "")
                if not object_key.startswith(f"field-records/{field_id}/") or ".." in object_key.split("/"):
                    raise OperationsReadError("image does not belong to this field", 404)
                media = self._attachments if self._attachments is not None else field_record_media_service()
                data = media.fetch_image(attachment)
                return self._image(data, attachment.get("content_type"))
        raise OperationsReadError("image not found", 404)

    @staticmethod
    def _image(data: bytes, content_type: str):
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise OperationsReadError("image is empty or exceeds the 10 MiB limit", 413)
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise OperationsReadError("unsupported image type", 415)
        return data, content_type
