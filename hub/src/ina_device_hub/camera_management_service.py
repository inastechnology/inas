import ipaddress
import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache

from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.camera_credential_repository import camera_credential_repository
from ina_device_hub.camera_device_repository import camera_device_repository
from ina_device_hub.collection_search import matches_search, search_terms
from ina_device_hub.device_event_log import append_device_event
from ina_device_hub.field_layout_repository import field_layout_repository
from ina_device_hub.field_repository import field_repository
from ina_device_hub.setting import setting

CAMERA_TYPES = {"reolink", "tapo", "custom"}
CAMERA_STREAMS = {"main", "sub"}
HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class CameraValidationError(ValueError):
    pass


class CameraNotFoundError(LookupError):
    pass


class CameraRemovalConflictError(ValueError):
    def __init__(self, references: list[dict]):
        super().__init__("圃場、設置ビュー、またはInstagram設定から参照されているため削除できません")
        self.references = references


class CameraManagementService:
    def __init__(
        self,
        repository=None,
        credential_repository=None,
        field_repo=None,
        layout_repo=None,
        settings=None,
        connection_tester=None,
        event_writer=None,
    ):
        self.repository = repository or camera_device_repository()
        self.credential_repository = credential_repository or camera_credential_repository()
        self.field_repository = field_repo or field_repository()
        self.layout_repository = layout_repo or field_layout_repository()
        self.settings = settings or setting()
        self.connection_tester = connection_tester or camera_connector().test_connection_info
        self.event_writer = event_writer or append_device_event

    def list(self, *, query=""):
        terms = search_terms(query)
        records = []
        for device_id, record in self.repository.get_all().items():
            public = self._public_record(device_id, record)
            if matches_search(terms, [public["id"], public["name"], public["camera_type"], public["ip_address"]]):
                records.append(public)
        return sorted(records, key=lambda item: ((item.get("name") or item["id"]).casefold(), item["id"]))

    def get(self, device_id: str):
        record = self.repository.get(device_id)
        return self._public_record(device_id, record) if record else None

    def create(self, payload: dict):
        if not isinstance(payload, dict):
            raise CameraValidationError("request body must be a JSON object")
        device_id = f"INACD-{uuid.uuid4()}"
        metadata = self._normalize_metadata(payload)
        credentials = self._normalize_credentials(payload, require_complete=True)
        now = _utc_now()
        metadata.update({"id": device_id, "created_at": now, "updated_at": now})
        self.credential_repository.set(device_id, **credentials)
        try:
            saved = self.repository.upsert(device_id, metadata)
        except Exception:
            self.credential_repository.remove(device_id)
            raise
        self.event_writer(
            "camera_registered",
            "local",
            device_id,
            category="camera",
            action="create",
            payload={"name": saved.get("name"), "camera_type": saved.get("camera_type")},
        )
        return self._public_record(device_id, saved)

    def update(self, device_id: str, payload: dict):
        if not isinstance(payload, dict):
            raise CameraValidationError("request body must be a JSON object")
        current = self.repository.get(device_id)
        if current is None:
            raise CameraNotFoundError(device_id)
        current_credentials = self._credentials(device_id, current)
        metadata = self._normalize_metadata(payload, existing=current)
        credentials = self._normalize_credentials(payload, existing=current_credentials, require_complete=True)
        metadata.update(
            {
                "id": device_id,
                "created_at": current.get("created_at") or _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        self.credential_repository.set(device_id, **credentials)
        saved = self.repository.upsert(device_id, metadata)
        self.event_writer(
            "camera_updated",
            "local",
            device_id,
            category="camera",
            action="update",
            payload={"name": saved.get("name"), "camera_type": saved.get("camera_type")},
        )
        return self._public_record(device_id, saved)

    def test_connection(self, payload: dict, *, device_id: str | None = None):
        current = self.repository.get(device_id) if device_id else None
        if device_id and current is None:
            raise CameraNotFoundError(device_id)
        current_credentials = self._credentials(device_id, current) if current else None
        metadata = self._normalize_metadata(payload, existing=current)
        credentials = self._normalize_credentials(payload, existing=current_credentials, require_complete=True)
        info = {**metadata, **credentials, "id": device_id or "camera-connection-test"}
        return self.connection_tester(info)

    def delete(self, device_id: str, *, deleted_by: str = "unknown"):
        current = self.repository.get(device_id)
        if current is None:
            return None
        references = self.references(device_id)
        if references:
            raise CameraRemovalConflictError(references)
        deleted = self.repository.remove(device_id)
        self.credential_repository.remove(device_id)
        self.event_writer(
            "camera_deleted",
            "local",
            device_id,
            category="camera",
            action="delete",
            payload={"deleted_by": deleted_by, "name": (deleted or {}).get("name")},
        )
        return self._public_record(device_id, deleted) if deleted else None

    def references(self, device_id: str):
        references = []
        for field in self.field_repository.list():
            field_id = field.get("id")
            field_name = field.get("name") or field_id
            if device_id in set(field.get("camera_device_ids") or []):
                references.append({"type": "field", "field_id": field_id, "field_name": field_name})
            layout = self.layout_repository.get(field_id, field_name=field_name)
            for space in layout.get("spaces") or []:
                for placement in space.get("placements") or []:
                    binding = placement.get("binding") or {}
                    if binding.get("resource_type") == "camera" and binding.get("device_id") == device_id:
                        references.append(
                            {
                                "type": "layout",
                                "field_id": field_id,
                                "field_name": field_name,
                                "space_name": space.get("name") or space.get("id"),
                                "placement_name": placement.get("name") or placement.get("id"),
                            }
                        )
        instagram = self.settings.get("instagram") or {}
        if instagram.get("camera_id") == device_id:
            references.append({"type": "instagram", "name": "Instagram投稿元カメラ"})
        return references

    def _public_record(self, device_id: str, record: dict):
        credentials = self._credentials(device_id, record)
        camera_type = str(record.get("camera_type") or record.get("type") or "tapo").strip().lower()
        return {
            "id": device_id,
            "name": record.get("name") or device_id,
            "camera_type": camera_type,
            "ip_address": record.get("ip_address") or "",
            "port": _normalize_int(record.get("port"), default=554),
            "channel": _normalize_int(record.get("channel"), default=1),
            "stream": str(record.get("stream") or "main"),
            "rtsp_path": record.get("rtsp_path") or "",
            "timelapse": _normalize_bool(record.get("timelapse"), default=False),
            "username": credentials.get("username") or "",
            "credentials_configured": bool(credentials.get("username") and credentials.get("password")),
            "created_at": record.get("created_at") or "",
            "updated_at": record.get("updated_at") or "",
            "preview_url": f"/camera/{device_id}/preview",
            "images_url": f"/camera/{device_id}/images",
        }

    def _credentials(self, device_id: str | None, record: dict | None):
        stored = self.credential_repository.get(device_id) if device_id else {}
        record = record or {}
        return {
            "username": stored.get("username") or record.get("username") or "",
            "password": stored.get("password") or record.get("password") or "",
        }

    def _normalize_metadata(self, payload: dict, existing: dict | None = None):
        existing = existing or {}
        name = _field(payload, "name", existing.get("name"))
        camera_type = _field(payload, "camera_type", existing.get("camera_type") or existing.get("type") or "reolink").lower()
        ip_address = _field(payload, "ip_address", existing.get("ip_address"))
        port = _normalize_int(payload.get("port", existing.get("port", 554)), default=554)
        channel = _normalize_int(payload.get("channel", existing.get("channel", 1)), default=1)
        stream = _field(payload, "stream", existing.get("stream") or "main").lower()
        rtsp_path = _field(payload, "rtsp_path", existing.get("rtsp_path"), allow_empty=True)
        timelapse = _normalize_bool(payload.get("timelapse", existing.get("timelapse")), default=False)

        if not name or len(name) > 100:
            raise CameraValidationError("name must be between 1 and 100 characters")
        if camera_type not in CAMERA_TYPES:
            raise CameraValidationError("camera_type must be reolink, tapo, or custom")
        _validate_host(ip_address)
        if port < 1 or port > 65535:
            raise CameraValidationError("port must be between 1 and 65535")
        if channel < 1 or channel > 64:
            raise CameraValidationError("channel must be between 1 and 64")
        if stream not in CAMERA_STREAMS:
            raise CameraValidationError("stream must be main or sub")
        if len(rtsp_path) > 240 or any(character in rtsp_path for character in ("\r", "\n")):
            raise CameraValidationError("rtsp_path is invalid")
        if rtsp_path and not rtsp_path.startswith("/"):
            rtsp_path = f"/{rtsp_path}"
        if camera_type == "custom" and not rtsp_path:
            raise CameraValidationError("rtsp_path is required for a custom camera")

        return {
            "name": name,
            "camera_type": camera_type,
            "ip_address": ip_address,
            "port": port,
            "channel": channel,
            "stream": stream,
            "rtsp_path": rtsp_path,
            "timelapse": timelapse,
        }

    def _normalize_credentials(self, payload: dict, existing: dict | None = None, *, require_complete: bool):
        existing = existing or {}
        username = _field(payload, "username", existing.get("username"), allow_empty=True)
        supplied_password = payload.get("password")
        password = str(supplied_password) if supplied_password not in (None, "") else str(existing.get("password") or "")
        if len(username) > 200 or len(password) > 500:
            raise CameraValidationError("camera credentials are too long")
        if require_complete and (not username or not password):
            raise CameraValidationError("username and password are required")
        return {"username": username, "password": password}


def _field(payload: dict, key: str, default=None, *, allow_empty=False):
    value = payload.get(key, default)
    value = "" if value is None else str(value).strip()
    if not allow_empty and not value:
        return ""
    return value


def _normalize_int(value, *, default):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CameraValidationError("numeric camera fields must be integers") from exc


def _normalize_bool(value, *, default=False):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise CameraValidationError("timelapse must be a boolean")


def _validate_host(value: str):
    if not value or len(value) > 253 or any(character in value for character in ("/", "@", " ", "\r", "\n")):
        raise CameraValidationError("ip_address must be an IP address or hostname")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not HOSTNAME_RE.fullmatch(value):
            raise CameraValidationError("ip_address must be an IP address or hostname") from None


def _utc_now():
    return datetime.now(UTC).isoformat()


@lru_cache(maxsize=1)
def camera_management_service():
    return CameraManagementService()
