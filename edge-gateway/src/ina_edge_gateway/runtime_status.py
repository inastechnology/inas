import threading
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeStatus:
    def __init__(self, *, node_id: str, parent_configured: bool):
        self._lock = threading.RLock()
        self._values: dict[str, Any] = {
            "node_id": node_id,
            "started_at": _utc_now(),
            "mqtt_connected": False,
            "parent_configured": parent_configured,
            "last_sync_attempt_at": None,
            "last_sync_success_at": None,
            "last_sync_error": None,
            "next_poll_seconds": None,
        }

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self._values["mqtt_connected"] = bool(connected)

    def record_sync_attempt(self) -> None:
        with self._lock:
            self._values["last_sync_attempt_at"] = _utc_now()

    def record_sync_success(self, next_poll_seconds: int) -> None:
        with self._lock:
            self._values["last_sync_success_at"] = _utc_now()
            self._values["last_sync_error"] = None
            self._values["next_poll_seconds"] = next_poll_seconds

    def record_sync_failure(self, error: BaseException) -> None:
        with self._lock:
            self._values["last_sync_error"] = type(error).__name__

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)
