import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from ina_edge_runtime import NodeType, parse_node_id, validate_device_id
from ina_edge_runtime.identity import validate_uuid_v4
from ina_edge_runtime.protocol import (
    canonical_json,
    content_hash,
    format_timestamp,
    normalize_timestamp,
    parse_timestamp,
    utc_now,
    validate_event_type,
    validate_sha256,
)

_CHILD_STATUSES = {"active", "revoked"}
_RESOURCE_TYPES = {"device.runtime_config", "device.assignment", "device.firmware_target", "node.policy"}
_RESOURCE_OPERATIONS = {"upsert", "delete"}
_MAX_DESIRED_PER_CHILD = 500
_MAX_COMMANDS_PER_CHILD = 100
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_DISPLAY_NAME_LENGTH = 200
_MAX_ERROR_CODE_LENGTH = 100
_MAX_MESSAGE_LENGTH = 1000
_NODE_BEARER_TOKEN = re.compile(r"^inas_sync_v1_[A-Za-z0-9_-]{43}$")
UPSTREAM_PARENT_BINDING_KEY = "upstream_parent_base_url"


class HierarchyConflictError(ValueError):
    pass


class HierarchyAuthenticationError(ValueError):
    pass


class HierarchyNotFoundError(KeyError):
    pass


class HierarchyCapacityError(ValueError):
    pass


class HierarchyRepository:
    def __init__(self, path: str | os.PathLike[str], *, parent_node_id: str):
        parent = parse_node_id(parent_node_id)
        if parent.node_type != NodeType.LOCAL_HUB:
            raise ValueError("hierarchy parent must be a Local Hub node")
        self.parent_node_id = parent.value
        self.path = str(path)
        Path(self.path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hierarchy_schema (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS child_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    parent_node_id TEXT NOT NULL,
                    display_name TEXT,
                    credential_salt BLOB NOT NULL,
                    credential_digest BLOB NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    last_request_id TEXT,
                    last_health_json TEXT,
                    response_generation INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS origin_routes (
                    origin_node_id TEXT PRIMARY KEY,
                    direct_child_node_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (direct_child_node_id) REFERENCES child_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS child_events (
                    local_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    direct_child_node_id TEXT NOT NULL,
                    origin_node_id TEXT NOT NULL,
                    origin_sequence INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    device_id TEXT,
                    payload_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    forwarded_at TEXT,
                    UNIQUE (origin_node_id, origin_sequence),
                    FOREIGN KEY (direct_child_node_id) REFERENCES child_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS child_command_results (
                    local_order INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id TEXT NOT NULL UNIQUE,
                    direct_child_node_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    origin_node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    error_code TEXT,
                    message TEXT,
                    payload_json TEXT,
                    content_sha256 TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    forwarded_at TEXT,
                    FOREIGN KEY (direct_child_node_id) REFERENCES child_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS downstream_desired_resources (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    direct_child_node_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id),
                    FOREIGN KEY (direct_child_node_id) REFERENCES child_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS downstream_commands (
                    command_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    command_type TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    direct_child_node_id TEXT NOT NULL,
                    device_id TEXT,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    terminal_result_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (direct_child_node_id) REFERENCES child_nodes(node_id)
                );

                CREATE TABLE IF NOT EXISTS upstream_desired_resources (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id)
                );

                CREATE TABLE IF NOT EXISTS hierarchy_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO hierarchy_schema (version, applied_at) VALUES (1, ?)",
                (format_timestamp(utc_now()),),
            )

    def enroll_child(
        self,
        node_id: str,
        *,
        display_name: str | None = None,
        descendant_node_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        identity = parse_node_id(node_id)
        if identity.value == self.parent_node_id:
            raise HierarchyConflictError("a Local Hub cannot enroll itself as a child")
        display_name = _optional_display_name(display_name)
        descendants = tuple(dict.fromkeys(parse_node_id(value).value for value in descendant_node_ids))
        if identity.node_type == NodeType.EDGE_GATEWAY and descendants:
            raise HierarchyConflictError("an Edge Gateway cannot own descendant node routes")
        if identity.value in descendants:
            raise HierarchyConflictError("descendant_node_ids must not repeat the direct child")
        if self.parent_node_id in descendants:
            raise HierarchyConflictError("the parent Local Hub cannot be a descendant")
        token = f"inas_sync_v1_{secrets.token_urlsafe(32)}"
        salt = secrets.token_bytes(16)
        digest = _credential_digest(salt, token)
        timestamp = format_timestamp(utc_now())

        with self._lock, self._connection:
            claimed_origins = (identity.value, *descendants)
            for origin_node_id in claimed_origins:
                route = self._connection.execute(
                    "SELECT direct_child_node_id FROM origin_routes WHERE origin_node_id = ?",
                    (origin_node_id,),
                ).fetchone()
                if route is not None and route["direct_child_node_id"] != identity.value:
                    raise HierarchyConflictError(f"origin node is already routed through another child: {origin_node_id}")

            existing = self._connection.execute("SELECT created_at FROM child_nodes WHERE node_id = ?", (identity.value,)).fetchone()
            created_at = existing["created_at"] if existing is not None else timestamp
            self._connection.execute(
                """
                INSERT INTO child_nodes (
                    node_id, node_type, parent_node_id, display_name, credential_salt,
                    credential_digest, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_type = excluded.node_type,
                    parent_node_id = excluded.parent_node_id,
                    display_name = excluded.display_name,
                    credential_salt = excluded.credential_salt,
                    credential_digest = excluded.credential_digest,
                    status = 'active',
                    updated_at = excluded.updated_at
                """,
                (
                    identity.value,
                    identity.node_type.value,
                    self.parent_node_id,
                    display_name,
                    salt,
                    digest,
                    created_at,
                    timestamp,
                ),
            )
            self._connection.execute("DELETE FROM origin_routes WHERE direct_child_node_id = ?", (identity.value,))
            self._connection.executemany(
                "INSERT INTO origin_routes (origin_node_id, direct_child_node_id, created_at) VALUES (?, ?, ?)",
                [(origin_node_id, identity.value, timestamp) for origin_node_id in claimed_origins],
            )
        return {
            "node_id": identity.value,
            "node_type": identity.node_type.value,
            "parent_node_id": self.parent_node_id,
            "display_name": display_name,
            "descendant_node_ids": list(descendants),
            "bearer_token": token,
            "created_at": created_at,
            "updated_at": timestamp,
        }

    def revoke_child(self, node_id: str) -> dict[str, Any]:
        node_id = parse_node_id(node_id).value
        timestamp = format_timestamp(utc_now())
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE child_nodes SET status = 'revoked', updated_at = ? WHERE node_id = ?",
                (timestamp, node_id),
            )
            if cursor.rowcount == 0:
                raise HierarchyNotFoundError(node_id)
        return self.get_child(node_id)

    def authenticate_child(self, node_id: str, token: str) -> dict[str, Any]:
        node_id = parse_node_id(node_id).value
        if not isinstance(token, str) or _NODE_BEARER_TOKEN.fullmatch(token) is None:
            raise HierarchyAuthenticationError("invalid node credential")
        with self._lock:
            row = self._connection.execute("SELECT * FROM child_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            hmac.compare_digest(_credential_digest(b"\0" * 16, token), b"\0" * 32)
            raise HierarchyAuthenticationError("invalid node credential")
        candidate = _credential_digest(row["credential_salt"], token)
        if row["status"] != "active" or not hmac.compare_digest(candidate, row["credential_digest"]):
            raise HierarchyAuthenticationError("invalid node credential")
        return _public_child(row, descendant_node_ids=self.descendant_node_ids(node_id))

    def allowed_origins(self, direct_child_node_id: str) -> frozenset[str]:
        direct_child_node_id = parse_node_id(direct_child_node_id).value
        with self._lock:
            rows = self._connection.execute(
                "SELECT origin_node_id FROM origin_routes WHERE direct_child_node_id = ?",
                (direct_child_node_id,),
            ).fetchall()
        origins = frozenset(row["origin_node_id"] for row in rows)
        if direct_child_node_id not in origins:
            raise HierarchyNotFoundError(direct_child_node_id)
        return origins

    def managed_node_ids(self) -> frozenset[str]:
        with self._lock:
            rows = self._connection.execute("SELECT origin_node_id FROM origin_routes").fetchall()
        return frozenset({self.parent_node_id, *(row["origin_node_id"] for row in rows)})

    def descendant_node_ids(self, direct_child_node_id: str) -> list[str]:
        direct_child_node_id = parse_node_id(direct_child_node_id).value
        with self._lock:
            rows = self._connection.execute(
                "SELECT origin_node_id FROM origin_routes WHERE direct_child_node_id = ? AND origin_node_id != ? ORDER BY origin_node_id",
                (direct_child_node_id, direct_child_node_id),
            ).fetchall()
        return [row["origin_node_id"] for row in rows]

    def get_child(self, node_id: str) -> dict[str, Any]:
        node_id = parse_node_id(node_id).value
        with self._lock:
            row = self._connection.execute("SELECT * FROM child_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            raise HierarchyNotFoundError(node_id)
        return _public_child(row, descendant_node_ids=self.descendant_node_ids(node_id))

    def list_children(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM child_nodes ORDER BY created_at, node_id").fetchall()
        return [_public_child(row, descendant_node_ids=self.descendant_node_ids(row["node_id"])) for row in rows]

    def ingest_exchange(self, direct_child_node_id: str, request: dict[str, Any]) -> dict[str, Any]:
        direct_child_node_id = parse_node_id(direct_child_node_id).value
        received_at = format_timestamp(utc_now())
        with self._lock, self._connection:
            child = self._connection.execute(
                "SELECT status, response_generation FROM child_nodes WHERE node_id = ?",
                (direct_child_node_id,),
            ).fetchone()
            if child is None or child["status"] != "active":
                raise HierarchyAuthenticationError("invalid node credential")
            acknowledged_events = [self._store_event(direct_child_node_id, event, received_at=received_at) for event in request["events"]]
            acknowledged_results = [self._store_command_result(direct_child_node_id, result, received_at=received_at) for result in request["command_results"]]
            generation = int(child["response_generation"]) + 1
            self._connection.execute(
                """
                UPDATE child_nodes SET
                    last_seen_at = ?,
                    last_request_id = ?,
                    last_health_json = ?,
                    response_generation = ?,
                    updated_at = ?
                WHERE node_id = ?
                """,
                (
                    received_at,
                    request["request_id"],
                    canonical_json(request["health"]),
                    generation,
                    received_at,
                    direct_child_node_id,
                ),
            )
        return {
            "ack_event_ids": acknowledged_events,
            "ack_command_result_ids": acknowledged_results,
            "next_cursor": f"local-hub:{generation}",
        }

    def _store_event(self, direct_child_node_id: str, event: dict[str, Any], *, received_at: str) -> str:
        event_hash = content_hash(event)
        existing = self._connection.execute(
            """
            SELECT event_id, direct_child_node_id, content_sha256
            FROM child_events
            WHERE event_id = ? OR (origin_node_id = ? AND origin_sequence = ?)
            """,
            (event["event_id"], event["origin_node_id"], event["sequence"]),
        ).fetchone()
        if existing is not None:
            if (
                existing["event_id"] != event["event_id"]
                or existing["direct_child_node_id"] != direct_child_node_id
                or existing["content_sha256"] != event_hash
            ):
                raise HierarchyConflictError("event ID or origin sequence was reused with different content")
            return event["event_id"]
        self._connection.execute(
            """
            INSERT INTO child_events (
                event_id, direct_child_node_id, origin_node_id, origin_sequence,
                schema_version, event_type, occurred_at, device_id, payload_json,
                content_sha256, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                direct_child_node_id,
                event["origin_node_id"],
                event["sequence"],
                event["schema_version"],
                event["event_type"],
                event["occurred_at"],
                event.get("device_id"),
                canonical_json(event["payload"]),
                event_hash,
                received_at,
            ),
        )
        return event["event_id"]

    def _store_command_result(self, direct_child_node_id: str, result: dict[str, Any], *, received_at: str) -> str:
        result_hash = content_hash(result)
        existing = self._connection.execute(
            "SELECT direct_child_node_id, content_sha256 FROM child_command_results WHERE result_id = ?",
            (result["result_id"],),
        ).fetchone()
        if existing is not None:
            if existing["direct_child_node_id"] != direct_child_node_id or existing["content_sha256"] != result_hash:
                raise HierarchyConflictError("command result ID was reused with different content")
            return result["result_id"]

        command = self._connection.execute(
            "SELECT target_node_id FROM downstream_commands WHERE command_id = ?",
            (result["command_id"],),
        ).fetchone()
        if command is not None and command["target_node_id"] != result["origin_node_id"]:
            raise HierarchyConflictError("command result origin does not match its target node")
        self._connection.execute(
            """
            INSERT INTO child_command_results (
                result_id, direct_child_node_id, command_id, origin_node_id, status,
                occurred_at, error_code, message, payload_json, content_sha256, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["result_id"],
                direct_child_node_id,
                result["command_id"],
                result["origin_node_id"],
                result["status"],
                result["occurred_at"],
                result.get("error_code"),
                result.get("message"),
                canonical_json(result.get("payload")) if "payload" in result else None,
                result_hash,
                received_at,
            ),
        )
        if command is not None:
            self._connection.execute(
                """
                UPDATE downstream_commands
                SET status = ?, terminal_result_id = ?, updated_at = ?
                WHERE command_id = ?
                """,
                (result["status"], result["result_id"], received_at, result["command_id"]),
            )
        return result["result_id"]

    def route_for_target(self, target_node_id: str) -> str:
        target_node_id = parse_node_id(target_node_id).value
        with self._lock:
            row = self._connection.execute(
                """
                SELECT routes.direct_child_node_id, children.status
                FROM origin_routes AS routes
                JOIN child_nodes AS children ON children.node_id = routes.direct_child_node_id
                WHERE routes.origin_node_id = ?
                """,
                (target_node_id,),
            ).fetchone()
        if row is None or row["status"] != "active":
            raise HierarchyNotFoundError(target_node_id)
        return row["direct_child_node_id"]

    def apply_upstream_desired(self, resource: dict[str, Any]) -> str:
        resource = _normalize_desired_resource(resource)
        target_node_id = resource["target_node_id"]
        if target_node_id == self.parent_node_id:
            return self._apply_desired_table("upstream_desired_resources", resource, direct_child_node_id=None)
        direct_child_node_id = self.route_for_target(target_node_id)
        return self._apply_desired_table("downstream_desired_resources", resource, direct_child_node_id=direct_child_node_id)

    def set_downstream_desired(
        self,
        *,
        resource_type: str,
        resource_id: str,
        target_node_id: str,
        operation: str,
        payload: Any,
    ) -> dict[str, Any]:
        target_node_id = parse_node_id(target_node_id).value
        direct_child_node_id = self.route_for_target(target_node_id)
        with self._lock:
            current = self._connection.execute(
                "SELECT revision FROM downstream_desired_resources WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            ).fetchone()
        revision = int(current["revision"]) + 1 if current is not None else 1
        timestamp = format_timestamp(utc_now())
        resource = _normalize_desired_resource(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "target_node_id": target_node_id,
                "revision": revision,
                "operation": operation,
                "content_sha256": content_hash(payload),
                "updated_at": timestamp,
                "payload": payload,
            }
        )
        self._apply_desired_table("downstream_desired_resources", resource, direct_child_node_id=direct_child_node_id)
        return resource

    def _apply_desired_table(self, table: str, resource: dict[str, Any], *, direct_child_node_id: str | None) -> str:
        if table not in {"upstream_desired_resources", "downstream_desired_resources"}:
            raise ValueError("unsupported desired-resource table")
        with self._lock, self._connection:
            current = self._connection.execute(
                f"SELECT * FROM {table} WHERE resource_type = ? AND resource_id = ?",
                (resource["resource_type"], resource["resource_id"]),
            ).fetchone()
            if current is not None:
                if resource["revision"] < int(current["revision"]):
                    return "stale"
                if resource["revision"] == int(current["revision"]):
                    if (
                        current["target_node_id"] != resource["target_node_id"]
                        or current["operation"] != resource["operation"]
                        or current["content_sha256"] != resource["content_sha256"]
                        or current["payload_json"] != canonical_json(resource["payload"])
                    ):
                        raise HierarchyConflictError("desired-resource revision has conflicting content")
                    return "unchanged"
            elif table == "downstream_desired_resources":
                count = self._connection.execute(
                    "SELECT COUNT(*) AS count FROM downstream_desired_resources WHERE direct_child_node_id = ?",
                    (direct_child_node_id,),
                ).fetchone()
                if int(count["count"]) >= _MAX_DESIRED_PER_CHILD:
                    raise HierarchyCapacityError("a child subtree may have at most 500 desired resources")

            columns = "resource_type, resource_id, target_node_id, revision, operation, content_sha256, updated_at, payload_json"
            values = (
                resource["resource_type"],
                resource["resource_id"],
                resource["target_node_id"],
                resource["revision"],
                resource["operation"],
                resource["content_sha256"],
                resource["updated_at"],
                canonical_json(resource["payload"]),
            )
            if table == "downstream_desired_resources":
                columns = f"{columns}, direct_child_node_id"
                values = (*values, direct_child_node_id)
            placeholders = ", ".join("?" for _ in values)
            update_direct_child = ", direct_child_node_id = excluded.direct_child_node_id" if table == "downstream_desired_resources" else ""
            self._connection.execute(
                f"""
                INSERT INTO {table} ({columns}) VALUES ({placeholders})
                ON CONFLICT(resource_type, resource_id) DO UPDATE SET
                    target_node_id = excluded.target_node_id,
                    revision = excluded.revision,
                    operation = excluded.operation,
                    content_sha256 = excluded.content_sha256,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                    {update_direct_child}
                """,
                values,
            )
        return "applied"

    def desired_for_child(self, direct_child_node_id: str) -> list[dict[str, Any]]:
        direct_child_node_id = parse_node_id(direct_child_node_id).value
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM downstream_desired_resources
                WHERE direct_child_node_id = ?
                ORDER BY resource_type, resource_id
                LIMIT ?
                """,
                (direct_child_node_id, _MAX_DESIRED_PER_CHILD),
            ).fetchall()
        return [_desired_from_row(row) for row in rows]

    def queue_command(self, command: dict[str, Any]) -> str:
        command = _normalize_command(command)
        direct_child_node_id = self.route_for_target(command["target_node_id"])
        command_hash = content_hash(command)
        timestamp = format_timestamp(utc_now())
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM downstream_commands WHERE command_id = ? OR idempotency_key = ?",
                (command["command_id"], command["idempotency_key"]),
            ).fetchone()
            if existing is not None:
                if existing["command_id"] != command["command_id"] or existing["content_sha256"] != command_hash:
                    raise HierarchyConflictError("command ID or idempotency key was reused with different content")
                return "unchanged"
            count = self._connection.execute(
                """
                SELECT COUNT(*) AS count FROM downstream_commands
                WHERE direct_child_node_id = ? AND status = 'pending' AND expires_at > ?
                """,
                (direct_child_node_id, timestamp),
            ).fetchone()
            if int(count["count"]) >= _MAX_COMMANDS_PER_CHILD:
                raise HierarchyCapacityError("a child subtree may have at most 100 active commands")
            self._connection.execute(
                """
                INSERT INTO downstream_commands (
                    command_id, idempotency_key, command_type, target_node_id,
                    direct_child_node_id, device_id, issued_at, expires_at, payload_json,
                    content_sha256, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    command["command_id"],
                    command["idempotency_key"],
                    command["command_type"],
                    command["target_node_id"],
                    direct_child_node_id,
                    command.get("device_id"),
                    command["issued_at"],
                    command["expires_at"],
                    canonical_json(command["payload"]),
                    command_hash,
                    timestamp,
                    timestamp,
                ),
            )
        return "applied"

    def create_command(
        self,
        *,
        target_node_id: str,
        command_type: str,
        payload: dict[str, Any],
        expires_at: str,
        device_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        command = _normalize_command(
            {
                "command_id": str(uuid.uuid4()),
                "idempotency_key": idempotency_key or str(uuid.uuid4()),
                "command_type": command_type,
                "target_node_id": target_node_id,
                "device_id": device_id,
                "issued_at": format_timestamp(utc_now()),
                "expires_at": expires_at,
                "payload": payload,
            }
        )
        self.queue_command(command)
        return command

    def commands_for_child(self, direct_child_node_id: str, *, now: datetime | None = None) -> list[dict[str, Any]]:
        direct_child_node_id = parse_node_id(direct_child_node_id).value
        now = now or utc_now()
        now_text = format_timestamp(now)
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE downstream_commands SET status = 'expired', updated_at = ?
                WHERE direct_child_node_id = ? AND status = 'pending' AND expires_at <= ?
                """,
                (now_text, direct_child_node_id, now_text),
            )
            rows = self._connection.execute(
                """
                SELECT * FROM downstream_commands
                WHERE direct_child_node_id = ? AND status = 'pending' AND expires_at > ?
                ORDER BY issued_at, command_id
                LIMIT ?
                """,
                (direct_child_node_id, now_text, _MAX_COMMANDS_PER_CHILD),
            ).fetchall()
        return [_command_from_row(row) for row in rows]

    def unforwarded_events(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM child_events WHERE forwarded_at IS NULL ORDER BY local_order LIMIT ?",
                (_bounded_limit(limit, 500),),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def mark_events_forwarded(self, event_ids: Iterable[str]) -> int:
        return self._mark_forwarded("child_events", "event_id", event_ids, maximum=500)

    def unforwarded_command_results(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM child_command_results WHERE forwarded_at IS NULL ORDER BY local_order LIMIT ?",
                (_bounded_limit(limit, 200),),
            ).fetchall()
        return [_command_result_from_row(row) for row in rows]

    def mark_command_results_forwarded(self, result_ids: Iterable[str]) -> int:
        return self._mark_forwarded("child_command_results", "result_id", result_ids, maximum=200)

    def _mark_forwarded(self, table: str, id_column: str, values: Iterable[str], *, maximum: int) -> int:
        if table not in {"child_events", "child_command_results"}:
            raise ValueError("unsupported forwarding table")
        identifiers = tuple(dict.fromkeys(values))
        if len(identifiers) > maximum:
            raise ValueError(f"at most {maximum} records may be marked forwarded")
        if not identifiers:
            return 0
        for identifier in identifiers:
            validate_uuid_v4(identifier, field_name=id_column)
        placeholders = ",".join("?" for _ in identifiers)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"UPDATE {table} SET forwarded_at = ? WHERE {id_column} IN ({placeholders}) AND forwarded_at IS NULL",
                (format_timestamp(utc_now()), *identifiers),
            )
            return cursor.rowcount

    def list_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM child_events ORDER BY local_order DESC LIMIT ?",
                (_bounded_limit(limit, 1000),),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def set_upstream_active(self, active: bool) -> None:
        self.set_metadata("upstream_active", "1" if active else "0")

    def upstream_active(self) -> bool:
        return self.get_metadata("upstream_active") == "1"

    def set_metadata(self, key: str, value: str | None) -> None:
        if not isinstance(key, str) or not key or len(key) > 100:
            raise ValueError("metadata key must be a non-empty string up to 100 characters")
        if value is not None and (not isinstance(value, str) or len(value) > 4000):
            raise ValueError("metadata value must be null or a string up to 4000 characters")
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO hierarchy_metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_metadata(self, key: str) -> str | None:
        with self._lock:
            row = self._connection.execute("SELECT value FROM hierarchy_metadata WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None


def _credential_digest(salt: bytes, token: str) -> bytes:
    return hashlib.sha256(salt + token.encode("utf-8")).digest()


def _public_child(row: sqlite3.Row, *, descendant_node_ids: list[str]) -> dict[str, Any]:
    health = json.loads(row["last_health_json"]) if row["last_health_json"] else None
    return {
        "node_id": row["node_id"],
        "node_type": row["node_type"],
        "parent_node_id": row["parent_node_id"],
        "display_name": row["display_name"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_seen_at": row["last_seen_at"],
        "last_request_id": row["last_request_id"],
        "last_health": health,
        "descendant_node_ids": descendant_node_ids,
    }


def _normalize_desired_resource(resource: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(resource, dict):
        raise ValueError("desired resource must be an object")
    expected = {
        "resource_type",
        "resource_id",
        "target_node_id",
        "revision",
        "operation",
        "content_sha256",
        "updated_at",
        "payload",
    }
    if set(resource) != expected:
        raise ValueError("desired resource fields are invalid")
    resource_type = resource["resource_type"]
    if resource_type not in _RESOURCE_TYPES:
        raise ValueError("unsupported desired resource type")
    resource_id = resource["resource_id"]
    if not isinstance(resource_id, str) or not resource_id or len(resource_id) > 200:
        raise ValueError("resource_id must be a non-empty string up to 200 characters")
    target_node_id = parse_node_id(resource["target_node_id"]).value
    if resource_type.startswith("device."):
        validate_device_id(resource_id)
    elif parse_node_id(resource_id).value != target_node_id:
        raise ValueError("node.policy resource_id must equal target_node_id")
    revision = resource["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    operation = resource["operation"]
    payload = resource["payload"]
    if operation not in _RESOURCE_OPERATIONS:
        raise ValueError("operation must be upsert or delete")
    if operation == "upsert" and not isinstance(payload, dict):
        raise ValueError("upsert payload must be an object")
    if operation == "delete" and payload is not None:
        raise ValueError("delete payload must be null")
    canonical_json(payload)
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "target_node_id": target_node_id,
        "revision": revision,
        "operation": operation,
        "content_sha256": validate_sha256(resource["content_sha256"]),
        "updated_at": normalize_timestamp(resource["updated_at"], field_name="updated_at"),
        "payload": payload,
    }


def _normalize_command(command: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(command, dict):
        raise ValueError("command must be an object")
    required = {"command_id", "idempotency_key", "command_type", "target_node_id", "issued_at", "expires_at", "payload"}
    allowed = required | {"device_id"}
    if not required.issubset(command) or set(command) - allowed:
        raise ValueError("command fields are invalid")
    command_id = validate_uuid_v4(command["command_id"], field_name="command_id")
    idempotency_key = command["idempotency_key"]
    if not isinstance(idempotency_key, str) or not idempotency_key or len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    target_node_id = parse_node_id(command["target_node_id"]).value
    device_id = command.get("device_id")
    if device_id is not None:
        validate_device_id(device_id)
    issued_at = parse_timestamp(command["issued_at"], field_name="issued_at")
    expires_at = parse_timestamp(command["expires_at"], field_name="expires_at")
    if expires_at <= issued_at:
        raise ValueError("expires_at must be later than issued_at")
    payload = command["payload"]
    if not isinstance(payload, dict):
        raise ValueError("command payload must be an object")
    canonical_json(payload)
    normalized = {
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "command_type": validate_event_type(command["command_type"], field_name="command_type"),
        "target_node_id": target_node_id,
        "issued_at": format_timestamp(issued_at),
        "expires_at": format_timestamp(expires_at),
        "payload": payload,
    }
    if device_id is not None:
        normalized["device_id"] = device_id
    return normalized


def _desired_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "resource_type": row["resource_type"],
        "resource_id": row["resource_id"],
        "target_node_id": row["target_node_id"],
        "revision": int(row["revision"]),
        "operation": row["operation"],
        "content_sha256": row["content_sha256"],
        "updated_at": row["updated_at"],
        "payload": json.loads(row["payload_json"]),
    }


def _command_from_row(row: sqlite3.Row) -> dict[str, Any]:
    command = {
        "command_id": row["command_id"],
        "idempotency_key": row["idempotency_key"],
        "command_type": row["command_type"],
        "target_node_id": row["target_node_id"],
        "issued_at": row["issued_at"],
        "expires_at": row["expires_at"],
        "payload": json.loads(row["payload_json"]),
    }
    if row["device_id"] is not None:
        command["device_id"] = row["device_id"]
    return command


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    event = {
        "event_id": row["event_id"],
        "origin_node_id": row["origin_node_id"],
        "sequence": int(row["origin_sequence"]),
        "schema_version": int(row["schema_version"]),
        "event_type": row["event_type"],
        "occurred_at": row["occurred_at"],
        "payload": json.loads(row["payload_json"]),
    }
    if row["device_id"] is not None:
        event["device_id"] = row["device_id"]
    return event


def _command_result_from_row(row: sqlite3.Row) -> dict[str, Any]:
    result = {
        "result_id": row["result_id"],
        "command_id": row["command_id"],
        "origin_node_id": row["origin_node_id"],
        "status": row["status"],
        "occurred_at": row["occurred_at"],
    }
    for field in ("error_code", "message"):
        if row[field] is not None:
            result[field] = row[field]
    if row["payload_json"] is not None:
        result["payload"] = json.loads(row["payload_json"])
    return result


def _optional_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_DISPLAY_NAME_LENGTH:
        raise ValueError("display_name must be null or a non-empty string up to 200 characters")
    return value.strip()


def _bounded_limit(value: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    return value
