import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

PROTOCOL_VERSION = "1.0"
EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMAND_STATUSES = {"pending", "accepted", "running", "succeeded", "failed", "expired", "rejected"}
RESULT_STATUSES = COMMAND_STATUSES - {"pending"}
TERMINAL_COMMAND_STATUSES = {"succeeded", "failed", "expired", "rejected"}
MAX_IDENTIFIER_LENGTH = 100


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be an RFC 3339 timestamp")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_timestamp(value: str, *, field_name: str) -> str:
    return format_timestamp(parse_timestamp(value, field_name=field_name))


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be finite JSON data") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError("content_sha256 must be 64 lowercase hexadecimal characters")
    return value


def validate_event_type(value: str, *, field_name: str = "event_type") -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER_LENGTH or EVENT_TYPE_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must use lowercase dot-separated identifier characters")
    return value
