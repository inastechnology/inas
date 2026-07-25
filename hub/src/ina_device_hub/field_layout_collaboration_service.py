import copy
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")
VALID_PRESENCE_STATES = {"viewing", "editing", "saving", "conflict"}
DEFAULT_PRESENCE_TTL_SECONDS = 30


class FieldLayoutCollaborationValidationError(ValueError):
    pass


class FieldLayoutCollaborationService:
    def __init__(
        self,
        *,
        presence_ttl_seconds: int = DEFAULT_PRESENCE_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ):
        self._presence_ttl = timedelta(seconds=max(5, int(presence_ttl_seconds)))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._rooms: dict[str, dict] = {}

    def touch(
        self,
        field_id: str,
        *,
        client_id: str,
        actor_email: str,
        active_space_id: str = "",
        selected_placement_id: str = "",
        state: str = "viewing",
        layout: dict | None = None,
    ) -> dict:
        values = _validate_presence(
            field_id=field_id,
            client_id=client_id,
            actor_email=actor_email,
            active_space_id=active_space_id,
            selected_placement_id=selected_placement_id,
            state=state,
        )
        now = _utc(self._clock())
        with self._lock:
            room = self._room(values["field_id"])
            self._prune(room, now)
            self._update_layout(room, layout)
            room["participants"][values["client_id"]] = {
                "client_id": values["client_id"],
                "email": values["actor_email"],
                "active_space_id": values["active_space_id"],
                "selected_placement_id": values["selected_placement_id"],
                "state": values["state"],
                "last_seen_at": now.isoformat(),
                "_last_seen": now,
            }
            return self._snapshot(room, current_client_id=values["client_id"])

    def leave(
        self,
        field_id: str,
        client_id: str,
        *,
        actor_email: str,
        layout: dict | None = None,
    ) -> dict:
        clean_field_id = _required_text(field_id, "field_id", 120)
        clean_client_id = _client_id(client_id)
        clean_actor_email = _required_text(actor_email, "actor_email", 254).lower()
        now = _utc(self._clock())
        with self._lock:
            room = self._room(clean_field_id)
            participant = room["participants"].get(clean_client_id)
            if participant and participant["email"] == clean_actor_email:
                room["participants"].pop(clean_client_id, None)
            self._prune(room, now)
            self._update_layout(room, layout)
            return self._snapshot(room, current_client_id=clean_client_id)

    def publish_layout(self, field_id: str, layout: dict) -> None:
        clean_field_id = _required_text(field_id, "field_id", 120)
        with self._lock:
            room = self._room(clean_field_id)
            self._update_layout(room, layout)

    def snapshot(self, field_id: str, *, current_client_id: str = "", layout: dict | None = None) -> dict:
        clean_field_id = _required_text(field_id, "field_id", 120)
        clean_client_id = _optional_client_id(current_client_id)
        now = _utc(self._clock())
        with self._lock:
            room = self._room(clean_field_id)
            self._prune(room, now)
            self._update_layout(room, layout)
            return self._snapshot(room, current_client_id=clean_client_id)

    def _room(self, field_id: str) -> dict:
        return self._rooms.setdefault(
            field_id,
            {
                "field_id": field_id,
                "layout": {"revision": 0, "updated_at": "", "updated_by": ""},
                "participants": {},
            },
        )

    def _prune(self, room: dict, now: datetime) -> None:
        expired = [client_id for client_id, participant in room["participants"].items() if now - participant["_last_seen"] > self._presence_ttl]
        for client_id in expired:
            room["participants"].pop(client_id, None)

    @staticmethod
    def _update_layout(room: dict, layout: dict | None) -> None:
        if not isinstance(layout, dict):
            return
        try:
            revision = int(layout.get("revision", 0))
        except (TypeError, ValueError):
            return
        if revision < int(room["layout"].get("revision", 0)):
            return
        room["layout"] = {
            "revision": max(0, revision),
            "updated_at": _optional_text(layout.get("updated_at"), 80),
            "updated_by": _optional_text(layout.get("updated_by"), 254),
        }

    @staticmethod
    def _snapshot(room: dict, *, current_client_id: str) -> dict:
        participants = []
        for participant in sorted(
            room["participants"].values(),
            key=lambda value: (value["email"], value["client_id"]),
        ):
            public = {key: value for key, value in participant.items() if not key.startswith("_")}
            public["is_current"] = participant["client_id"] == current_client_id
            participants.append(public)
        return {
            "field_id": room["field_id"],
            "layout": copy.deepcopy(room["layout"]),
            "participants": participants,
        }


def _validate_presence(
    *,
    field_id: str,
    client_id: str,
    actor_email: str,
    active_space_id: str,
    selected_placement_id: str,
    state: str,
) -> dict:
    clean_state = _required_text(state, "state", 20)
    if clean_state not in VALID_PRESENCE_STATES:
        raise FieldLayoutCollaborationValidationError("state is unsupported")
    return {
        "field_id": _required_text(field_id, "field_id", 120),
        "client_id": _client_id(client_id),
        "actor_email": _required_text(actor_email, "actor_email", 254).lower(),
        "active_space_id": _optional_text(active_space_id, 80),
        "selected_placement_id": _optional_text(selected_placement_id, 80),
        "state": clean_state,
    }


def _client_id(value) -> str:
    text = _required_text(value, "client_id", 80)
    if not CLIENT_ID_PATTERN.fullmatch(text):
        raise FieldLayoutCollaborationValidationError("client_id has an unsupported format")
    return text


def _optional_client_id(value) -> str:
    return "" if value in (None, "") else _client_id(value)


def _required_text(value, field_name: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise FieldLayoutCollaborationValidationError(f"{field_name} is required")
    if len(text) > maximum:
        raise FieldLayoutCollaborationValidationError(f"{field_name} must be {maximum} characters or less")
    return text


def _optional_text(value, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__instance = None


def field_layout_collaboration_service():
    global __instance  # noqa: PLW0603
    if not __instance:
        __instance = FieldLayoutCollaborationService()
    return __instance
