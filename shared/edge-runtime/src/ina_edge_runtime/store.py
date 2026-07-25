import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from ina_edge_runtime.identity import parse_node_id, validate_device_id, validate_uuid_v4
from ina_edge_runtime.models import ApplyDesiredResult, DesiredResource, StoredCommand, StoredCommandResult, StoredEvent
from ina_edge_runtime.protocol import (
    COMMAND_STATUSES,
    RESULT_STATUSES,
    canonical_json,
    content_hash,
    format_timestamp,
    normalize_timestamp,
    parse_timestamp,
    utc_now,
    validate_event_type,
    validate_sha256,
)

_DESIRED_RESOURCE_TYPES = {"device.runtime_config", "device.assignment", "device.firmware_target", "node.policy"}
_DESIRED_OPERATIONS = {"upsert", "delete"}
_MAX_RESOURCE_ID_LENGTH = 200
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_ERROR_CODE_LENGTH = 100
_MAX_MESSAGE_LENGTH = 1000
_MAX_CURSOR_LENGTH = 1000
_MAX_METADATA_KEY_LENGTH = 200
_MAX_METADATA_VALUE_LENGTH = 4000
_COMMAND_TRANSITIONS = {
    "pending": {"accepted", "rejected", "expired"},
    "accepted": {"running", "succeeded", "failed", "expired", "rejected"},
    "running": {"succeeded", "failed", "expired"},
    "succeeded": set(),
    "failed": set(),
    "expired": set(),
    "rejected": set(),
}


class EventConflictError(ValueError):
    pass


class RevisionConflictError(ValueError):
    pass


class CommandConflictError(ValueError):
    pass


class CommandStateError(ValueError):
    pass


class CommandExpiredError(CommandStateError):
    def __init__(self, command: StoredCommand):
        self.command = command
        super().__init__(f"command {command.command_id} expired before activation")


class EdgeStore:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        self.close()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS edge_schema (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS origin_sequences (
                    origin_node_id TEXT PRIMARY KEY,
                    last_sequence INTEGER NOT NULL CHECK (last_sequence >= 0)
                );

                CREATE TABLE IF NOT EXISTS outbox_events (
                    local_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    origin_node_id TEXT NOT NULL,
                    origin_sequence INTEGER NOT NULL CHECK (origin_sequence > 0),
                    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    device_id TEXT,
                    payload_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (origin_node_id, origin_sequence)
                );

                CREATE TABLE IF NOT EXISTS desired_resources (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    operation TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id)
                );

                CREATE TABLE IF NOT EXISTS inbox_commands (
                    command_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    command_type TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    device_id TEXT,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox_command_results (
                    local_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id TEXT NOT NULL UNIQUE,
                    command_id TEXT NOT NULL,
                    origin_node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    error_code TEXT,
                    message TEXT,
                    payload_json TEXT,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS command_completions (
                    command_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL UNIQUE,
                    origin_node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    error_code TEXT,
                    message TEXT,
                    payload_json TEXT,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (command_id) REFERENCES inbox_commands(command_id)
                );

                CREATE TABLE IF NOT EXISTS sync_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO edge_schema (version, applied_at) VALUES (?, ?)",
                (1, format_timestamp(utc_now())),
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO edge_schema (version, applied_at) VALUES (?, ?)",
                (2, format_timestamp(utc_now())),
            )

    def enqueue_event(
        self,
        *,
        event_id: str,
        origin_node_id: str,
        event_type: str,
        occurred_at: str,
        payload: Any,
        device_id: str | None = None,
        schema_version: int = 1,
        sequence: int | None = None,
    ) -> StoredEvent:
        validate_uuid_v4(event_id, field_name="event_id")
        parse_node_id(origin_node_id)
        validate_event_type(event_type)
        occurred_at = normalize_timestamp(occurred_at, field_name="occurred_at")
        if device_id is not None:
            validate_device_id(device_id)
        if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
            raise ValueError("schema_version must be a positive integer")
        if sequence is not None and (not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1):
            raise ValueError("sequence must be a positive integer")
        payload_json = canonical_json(payload)

        with self._lock, self._connection:
            existing = self._connection.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
            if existing is not None:
                candidate_sequence = sequence if sequence is not None else existing["origin_sequence"]
                candidate_hash = _event_hash(
                    origin_node_id=origin_node_id,
                    sequence=candidate_sequence,
                    schema_version=schema_version,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    device_id=device_id,
                    payload=payload,
                )
                if existing["content_sha256"] != candidate_hash:
                    raise EventConflictError(f"event_id {event_id} was reused with different content")
                return _event_from_row(existing)

            origin_sequence = sequence if sequence is not None else self._next_origin_sequence(origin_node_id)
            if sequence is not None:
                self._advance_origin_sequence(origin_node_id, sequence)
            event_sha256 = _event_hash(
                origin_node_id=origin_node_id,
                sequence=origin_sequence,
                schema_version=schema_version,
                event_type=event_type,
                occurred_at=occurred_at,
                device_id=device_id,
                payload=payload,
            )
            try:
                cursor = self._connection.execute(
                    """
                    INSERT INTO outbox_events (
                        event_id, origin_node_id, origin_sequence, schema_version, event_type,
                        occurred_at, device_id, payload_json, content_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        origin_node_id,
                        origin_sequence,
                        schema_version,
                        event_type,
                        occurred_at,
                        device_id,
                        payload_json,
                        event_sha256,
                        format_timestamp(utc_now()),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise EventConflictError(f"origin sequence {origin_node_id}/{origin_sequence} is already used") from exc
            row = self._connection.execute("SELECT * FROM outbox_events WHERE local_order = ?", (cursor.lastrowid,)).fetchone()
            return _event_from_row(row)

    def pending_events(self, *, limit: int = 500) -> list[StoredEvent]:
        limit = _bounded_limit(limit, maximum=500)
        with self._lock:
            rows = self._connection.execute("SELECT * FROM outbox_events ORDER BY local_order LIMIT ?", (limit,)).fetchall()
        return [_event_from_row(row) for row in rows]

    def ack_events(self, event_ids: Iterable[str]) -> int:
        values = _validated_ids(event_ids, field_name="event_id", maximum=500)
        if not values:
            return 0
        placeholders = ",".join("?" for _ in values)
        with self._lock, self._connection:
            cursor = self._connection.execute(f"DELETE FROM outbox_events WHERE event_id IN ({placeholders})", values)
            return cursor.rowcount

    def outbox_depth(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM outbox_events").fetchone()
        return int(row["count"])

    def command_result_outbox_depth(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS count FROM outbox_command_results").fetchone()
        return int(row["count"])

    def sync_outbox_depth(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT (SELECT COUNT(*) FROM outbox_events) + (SELECT COUNT(*) FROM outbox_command_results) AS count").fetchone()
        return int(row["count"])

    def apply_desired_resource(
        self,
        *,
        resource_type: str,
        resource_id: str,
        target_node_id: str,
        revision: int,
        operation: str,
        content_sha256: str,
        updated_at: str,
        payload: Any,
    ) -> ApplyDesiredResult:
        if resource_type not in _DESIRED_RESOURCE_TYPES:
            raise ValueError(f"unsupported desired resource type: {resource_type}")
        if not isinstance(resource_id, str) or not resource_id or len(resource_id) > _MAX_RESOURCE_ID_LENGTH:
            raise ValueError("resource_id must be a non-empty string up to 200 characters")
        parse_node_id(target_node_id)
        if resource_type.startswith("device."):
            validate_device_id(resource_id)
        elif resource_type == "node.policy" and parse_node_id(resource_id).value != target_node_id:
            raise ValueError("node.policy resource_id must equal target_node_id")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValueError("revision must be a positive integer")
        if operation not in _DESIRED_OPERATIONS:
            raise ValueError("operation must be upsert or delete")
        if operation == "upsert" and not isinstance(payload, dict):
            raise ValueError("upsert payload must be an object")
        if operation == "delete" and payload is not None:
            raise ValueError("delete payload must be null")
        validate_sha256(content_sha256)
        updated_at = normalize_timestamp(updated_at, field_name="updated_at")
        payload_json = canonical_json(payload)
        incoming = DesiredResource(
            resource_type=resource_type,
            resource_id=resource_id,
            target_node_id=target_node_id,
            revision=revision,
            operation=operation,
            content_sha256=content_sha256,
            updated_at=updated_at,
            payload=payload,
        )

        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM desired_resources WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchone()
            if row is not None:
                current = _desired_from_row(row)
                if revision < current.revision:
                    return ApplyDesiredResult(status="stale", resource=current)
                if revision == current.revision:
                    if (
                        current.content_sha256 != content_sha256
                        or current.target_node_id != target_node_id
                        or current.operation != operation
                        or canonical_json(current.payload) != payload_json
                    ):
                        raise RevisionConflictError(f"{resource_type}/{resource_id} revision {revision} has conflicting content")
                    return ApplyDesiredResult(status="unchanged", resource=current)

            self._connection.execute(
                """
                INSERT INTO desired_resources (
                    resource_type, resource_id, target_node_id, revision, operation,
                    content_sha256, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_type, resource_id) DO UPDATE SET
                    target_node_id = excluded.target_node_id,
                    revision = excluded.revision,
                    operation = excluded.operation,
                    content_sha256 = excluded.content_sha256,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (resource_type, resource_id, target_node_id, revision, operation, content_sha256, updated_at, payload_json),
            )
        return ApplyDesiredResult(status="applied", resource=incoming)

    def get_desired_resource(self, resource_type: str, resource_id: str) -> DesiredResource | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM desired_resources WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchone()
        return _desired_from_row(row) if row is not None else None

    def receive_command(
        self,
        *,
        command_id: str,
        idempotency_key: str,
        command_type: str,
        target_node_id: str,
        issued_at: str,
        expires_at: str,
        payload: dict[str, Any],
        device_id: str | None = None,
        now: datetime | None = None,
    ) -> StoredCommand:
        validate_uuid_v4(command_id, field_name="command_id")
        if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
        validate_event_type(command_type, field_name="command_type")
        parse_node_id(target_node_id)
        if device_id is not None:
            validate_device_id(device_id)
        issued = parse_timestamp(issued_at, field_name="issued_at")
        expires = parse_timestamp(expires_at, field_name="expires_at")
        if expires <= issued:
            raise ValueError("expires_at must be later than issued_at")
        issued_at = format_timestamp(issued)
        expires_at = format_timestamp(expires)
        if not isinstance(payload, dict):
            raise ValueError("command payload must be an object")
        payload_json = canonical_json(payload)
        command_sha256 = content_hash(
            {
                "command_id": command_id,
                "idempotency_key": idempotency_key,
                "command_type": command_type,
                "target_node_id": target_node_id,
                "device_id": device_id,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "payload": payload,
            }
        )
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")
        status = "expired" if expires <= now.astimezone(expires.tzinfo) else "pending"
        timestamp = format_timestamp(now)

        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM inbox_commands WHERE command_id = ? OR idempotency_key = ?",
                (command_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["command_id"] != command_id or existing["content_sha256"] != command_sha256:
                    raise CommandConflictError("command ID or idempotency key was reused with different content")
                return _command_from_row(existing)

            self._connection.execute(
                """
                INSERT INTO inbox_commands (
                    command_id, idempotency_key, command_type, target_node_id, device_id,
                    issued_at, expires_at, payload_json, content_sha256, status, error,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    command_id,
                    idempotency_key,
                    command_type,
                    target_node_id,
                    device_id,
                    issued_at,
                    expires_at,
                    payload_json,
                    command_sha256,
                    status,
                    timestamp,
                    timestamp,
                ),
            )
            row = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
            return _command_from_row(row)

    def pending_commands(self, *, now: datetime | None = None, limit: int = 100) -> list[StoredCommand]:
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")
        now_text = format_timestamp(now)
        limit = _bounded_limit(limit, maximum=100)
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE inbox_commands SET status = 'expired', updated_at = ? WHERE status IN ('pending', 'accepted') AND expires_at <= ?",
                (now_text, now_text),
            )
            rows = self._connection.execute(
                "SELECT * FROM inbox_commands WHERE status IN ('pending', 'accepted') ORDER BY issued_at, command_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [_command_from_row(row) for row in rows]

    def get_command(self, command_id: str) -> StoredCommand | None:
        validate_uuid_v4(command_id, field_name="command_id")
        with self._lock:
            row = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
        return _command_from_row(row) if row is not None else None

    def commands_with_status(self, statuses: Iterable[str], *, limit: int = 100) -> list[StoredCommand]:
        values = tuple(dict.fromkeys(statuses))
        if not values or any(status not in COMMAND_STATUSES for status in values):
            raise ValueError("statuses must contain supported command statuses")
        limit = _bounded_limit(limit, maximum=100)
        placeholders = ",".join("?" for _ in values)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM inbox_commands WHERE status IN ({placeholders}) ORDER BY issued_at, command_id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [_command_from_row(row) for row in rows]

    def set_command_status(self, command_id: str, status: str, *, error: str | None = None, now: datetime | None = None) -> StoredCommand:
        validate_uuid_v4(command_id, field_name="command_id")
        if status not in COMMAND_STATUSES - {"pending"}:
            raise ValueError("unsupported command status")
        now = now or utc_now()
        timestamp = format_timestamp(now)
        expired_command = None
        with self._lock, self._connection:
            row = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
            if row is None:
                raise KeyError(command_id)
            current = row["status"]
            expires_at = parse_timestamp(row["expires_at"], field_name="expires_at")
            if status in {"accepted", "running"} and current in {"pending", "accepted"} and expires_at <= now.astimezone(expires_at.tzinfo):
                self._connection.execute(
                    "UPDATE inbox_commands SET status = 'expired', error = ?, updated_at = ? WHERE command_id = ?",
                    ("command expired before activation", timestamp, command_id),
                )
                updated = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
                expired_command = _command_from_row(updated)
            elif current == status:
                return _command_from_row(row)
            elif status not in _COMMAND_TRANSITIONS[current]:
                raise CommandStateError(f"command cannot change from {current} to {status}")
            else:
                self._connection.execute(
                    "UPDATE inbox_commands SET status = ?, error = ?, updated_at = ? WHERE command_id = ?",
                    (status, error, timestamp, command_id),
                )
                updated = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
        if expired_command is not None:
            raise CommandExpiredError(expired_command)
        return _command_from_row(updated)

    def record_command_result(
        self,
        *,
        result_id: str,
        command_id: str,
        origin_node_id: str,
        status: str,
        occurred_at: str,
        error_code: str | None = None,
        message: str | None = None,
        payload: Any = None,
    ) -> StoredCommandResult:
        validate_uuid_v4(result_id, field_name="result_id")
        validate_uuid_v4(command_id, field_name="command_id")
        parse_node_id(origin_node_id)
        if status not in RESULT_STATUSES:
            raise ValueError("unsupported command result status")
        if error_code is not None and (not error_code or len(error_code) > _MAX_ERROR_CODE_LENGTH):
            raise ValueError("error_code must be 1 to 100 characters")
        if message is not None and len(message) > _MAX_MESSAGE_LENGTH:
            raise ValueError("message must be at most 1000 characters")
        occurred_at = normalize_timestamp(occurred_at, field_name="occurred_at")
        payload_json = canonical_json(payload) if payload is not None else None
        result_sha256 = content_hash(
            {
                "command_id": command_id,
                "origin_node_id": origin_node_id,
                "status": status,
                "occurred_at": occurred_at,
                "error_code": error_code,
                "message": message,
                "payload": payload,
            }
        )

        with self._lock, self._connection:
            existing = self._connection.execute("SELECT * FROM outbox_command_results WHERE result_id = ?", (result_id,)).fetchone()
            if existing is not None:
                if existing["content_sha256"] != result_sha256:
                    raise CommandConflictError(f"result_id {result_id} was reused with different content")
                return _command_result_from_row(existing)
            cursor = self._connection.execute(
                """
                INSERT INTO outbox_command_results (
                    result_id, command_id, origin_node_id, status, occurred_at,
                    error_code, message, payload_json, content_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    command_id,
                    origin_node_id,
                    status,
                    occurred_at,
                    error_code,
                    message,
                    payload_json,
                    result_sha256,
                    format_timestamp(utc_now()),
                ),
            )
            row = self._connection.execute("SELECT * FROM outbox_command_results WHERE local_order = ?", (cursor.lastrowid,)).fetchone()
            return _command_result_from_row(row)

    def complete_command(
        self,
        command_id: str,
        status: str,
        *,
        origin_node_id: str,
        error_code: str | None = None,
        message: str | None = None,
        payload: Any = None,
        result_id: str | None = None,
        now: datetime | None = None,
    ) -> StoredCommandResult:
        validate_uuid_v4(command_id, field_name="command_id")
        if status not in {"succeeded", "failed", "expired", "rejected"}:
            raise ValueError("command completion status must be terminal")
        parse_node_id(origin_node_id)
        if error_code is not None and (not error_code or len(error_code) > _MAX_ERROR_CODE_LENGTH):
            raise ValueError("error_code must be 1 to 100 characters")
        if message is not None and len(message) > _MAX_MESSAGE_LENGTH:
            raise ValueError("message must be at most 1000 characters")
        payload_json = canonical_json(payload) if payload is not None else None
        if result_id is not None:
            validate_uuid_v4(result_id, field_name="result_id")
        now = now or utc_now()
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")

        with self._lock, self._connection:
            completion = self._connection.execute("SELECT * FROM command_completions WHERE command_id = ?", (command_id,)).fetchone()
            if completion is not None:
                if completion["status"] != status or completion["origin_node_id"] != origin_node_id:
                    raise CommandConflictError(f"command {command_id} already has a different terminal result")
                outbox_row = self._connection.execute(
                    "SELECT * FROM outbox_command_results WHERE result_id = ?",
                    (completion["result_id"],),
                ).fetchone()
                return _command_result_from_row(outbox_row) if outbox_row is not None else _command_result_from_completion(completion)

            command = self._connection.execute("SELECT * FROM inbox_commands WHERE command_id = ?", (command_id,)).fetchone()
            if command is None:
                raise KeyError(command_id)
            if command["target_node_id"] != origin_node_id:
                raise ValueError("origin_node_id must match the command target node")
            current_status = command["status"]
            if current_status != status:
                if status not in _COMMAND_TRANSITIONS[current_status]:
                    raise CommandStateError(f"command cannot change from {current_status} to {status}")
                self._connection.execute(
                    "UPDATE inbox_commands SET status = ?, error = ?, updated_at = ? WHERE command_id = ?",
                    (status, message, format_timestamp(now), command_id),
                )

            result_id = result_id or str(uuid.uuid4())
            occurred_at = format_timestamp(now)
            result_sha256 = content_hash(
                {
                    "command_id": command_id,
                    "origin_node_id": origin_node_id,
                    "status": status,
                    "occurred_at": occurred_at,
                    "error_code": error_code,
                    "message": message,
                    "payload": payload,
                }
            )
            created_at = format_timestamp(utc_now())
            self._connection.execute(
                """
                INSERT INTO command_completions (
                    command_id, result_id, origin_node_id, status, occurred_at,
                    error_code, message, payload_json, content_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    result_id,
                    origin_node_id,
                    status,
                    occurred_at,
                    error_code,
                    message,
                    payload_json,
                    result_sha256,
                    created_at,
                ),
            )
            cursor = self._connection.execute(
                """
                INSERT INTO outbox_command_results (
                    result_id, command_id, origin_node_id, status, occurred_at,
                    error_code, message, payload_json, content_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    command_id,
                    origin_node_id,
                    status,
                    occurred_at,
                    error_code,
                    message,
                    payload_json,
                    result_sha256,
                    created_at,
                ),
            )
            row = self._connection.execute("SELECT * FROM outbox_command_results WHERE local_order = ?", (cursor.lastrowid,)).fetchone()
            return _command_result_from_row(row)

    def pending_command_results(self, *, limit: int = 200) -> list[StoredCommandResult]:
        limit = _bounded_limit(limit, maximum=200)
        with self._lock:
            rows = self._connection.execute("SELECT * FROM outbox_command_results ORDER BY local_order LIMIT ?", (limit,)).fetchall()
        return [_command_result_from_row(row) for row in rows]

    def ack_command_results(self, result_ids: Iterable[str]) -> int:
        values = _validated_ids(result_ids, field_name="result_id", maximum=200)
        if not values:
            return 0
        placeholders = ",".join("?" for _ in values)
        with self._lock, self._connection:
            cursor = self._connection.execute(f"DELETE FROM outbox_command_results WHERE result_id IN ({placeholders})", values)
            return cursor.rowcount

    def get_sync_cursor(self) -> str | None:
        return self.get_metadata("parent_cursor")

    def set_sync_cursor(self, value: str | None) -> None:
        if value is not None and (not isinstance(value, str) or not value or len(value) > _MAX_CURSOR_LENGTH):
            raise ValueError("sync cursor must be null or a non-empty string up to 1000 characters")
        self.set_metadata("parent_cursor", value)

    def get_metadata(self, key: str) -> str | None:
        _validate_metadata_key(key)
        with self._lock:
            row = self._connection.execute("SELECT value FROM sync_metadata WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None

    def set_metadata(self, key: str, value: str | None) -> None:
        _validate_metadata_key(key)
        if value is not None and (not isinstance(value, str) or len(value) > _MAX_METADATA_VALUE_LENGTH):
            raise ValueError("metadata value must be null or a string up to 4000 characters")
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO sync_metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _next_origin_sequence(self, origin_node_id: str) -> int:
        row = self._connection.execute("SELECT last_sequence FROM origin_sequences WHERE origin_node_id = ?", (origin_node_id,)).fetchone()
        next_sequence = int(row["last_sequence"]) + 1 if row is not None else 1
        self._connection.execute(
            """
            INSERT INTO origin_sequences (origin_node_id, last_sequence) VALUES (?, ?)
            ON CONFLICT(origin_node_id) DO UPDATE SET last_sequence = excluded.last_sequence
            """,
            (origin_node_id, next_sequence),
        )
        return next_sequence

    def _advance_origin_sequence(self, origin_node_id: str, sequence: int) -> None:
        row = self._connection.execute("SELECT last_sequence FROM origin_sequences WHERE origin_node_id = ?", (origin_node_id,)).fetchone()
        if row is None or sequence > int(row["last_sequence"]):
            self._connection.execute(
                """
                INSERT INTO origin_sequences (origin_node_id, last_sequence) VALUES (?, ?)
                ON CONFLICT(origin_node_id) DO UPDATE SET last_sequence = excluded.last_sequence
                """,
                (origin_node_id, sequence),
            )


def _event_hash(**values) -> str:
    return content_hash(values)


def _event_from_row(row: sqlite3.Row) -> StoredEvent:
    return StoredEvent(
        local_order=int(row["local_order"]),
        event_id=row["event_id"],
        origin_node_id=row["origin_node_id"],
        sequence=int(row["origin_sequence"]),
        schema_version=int(row["schema_version"]),
        event_type=row["event_type"],
        occurred_at=row["occurred_at"],
        device_id=row["device_id"],
        payload=json.loads(row["payload_json"]),
    )


def _desired_from_row(row: sqlite3.Row) -> DesiredResource:
    return DesiredResource(
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        target_node_id=row["target_node_id"],
        revision=int(row["revision"]),
        operation=row["operation"],
        content_sha256=row["content_sha256"],
        updated_at=row["updated_at"],
        payload=json.loads(row["payload_json"]),
    )


def _command_from_row(row: sqlite3.Row) -> StoredCommand:
    return StoredCommand(
        command_id=row["command_id"],
        idempotency_key=row["idempotency_key"],
        command_type=row["command_type"],
        target_node_id=row["target_node_id"],
        device_id=row["device_id"],
        issued_at=row["issued_at"],
        expires_at=row["expires_at"],
        payload=json.loads(row["payload_json"]),
        status=row["status"],
        error=row["error"],
    )


def _command_result_from_row(row: sqlite3.Row) -> StoredCommandResult:
    return StoredCommandResult(
        local_order=int(row["local_order"]),
        result_id=row["result_id"],
        command_id=row["command_id"],
        origin_node_id=row["origin_node_id"],
        status=row["status"],
        occurred_at=row["occurred_at"],
        error_code=row["error_code"],
        message=row["message"],
        payload=json.loads(row["payload_json"]) if row["payload_json"] is not None else None,
    )


def _command_result_from_completion(row: sqlite3.Row) -> StoredCommandResult:
    return StoredCommandResult(
        local_order=0,
        result_id=row["result_id"],
        command_id=row["command_id"],
        origin_node_id=row["origin_node_id"],
        status=row["status"],
        occurred_at=row["occurred_at"],
        error_code=row["error_code"],
        message=row["message"],
        payload=json.loads(row["payload_json"]) if row["payload_json"] is not None else None,
    )


def _bounded_limit(value: int, *, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return value


def _validated_ids(values: Iterable[str], *, field_name: str, maximum: int) -> list[str]:
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) > maximum:
        raise ValueError(f"at most {maximum} {field_name} values may be acknowledged")
    for value in unique_values:
        validate_uuid_v4(value, field_name=field_name)
    return unique_values


def _validate_metadata_key(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > _MAX_METADATA_KEY_LENGTH:
        raise ValueError("metadata key must be a non-empty string up to 200 characters")
