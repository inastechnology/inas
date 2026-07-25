import gzip
import io
import json
import re
from http import HTTPStatus
from typing import Any

from flask import Blueprint, jsonify, request

from ina_device_hub.hierarchy_repository import (
    HierarchyAuthenticationError,
    HierarchyCapacityError,
    HierarchyConflictError,
    HierarchyNotFoundError,
)
from ina_device_hub.hierarchy_service import hierarchy_service

hierarchy_api = Blueprint("hierarchy_api", __name__)
MAX_SYNC_BODY_BYTES = 1024 * 1024
NODE_BEARER_TOKEN = re.compile(r"^inas_sync_v1_[A-Za-z0-9_-]{43}$")


@hierarchy_api.post("/sync/v1/nodes/<node_id>/exchange")
def exchange_node(node_id: str):
    bearer_token = _bearer_token()
    if bearer_token is None:
        return _node_authentication_error()
    service = hierarchy_service()
    try:
        service.repository.authenticate_child(node_id, bearer_token)
    except (HierarchyAuthenticationError, TypeError, ValueError):
        return _node_authentication_error()

    try:
        document = _read_sync_document()
        response = service.exchange_child(node_id, bearer_token, document)
    except _SyncHTTPError as exc:
        return jsonify({"error": exc.code}), exc.status
    except HierarchyAuthenticationError:
        return _node_authentication_error()
    except HierarchyConflictError as exc:
        return jsonify({"error": "sync_conflict", "message": str(exc)}), HTTPStatus.CONFLICT
    except (HierarchyCapacityError, ValueError) as exc:
        return jsonify({"error": "invalid_sync_request", "message": str(exc)}), HTTPStatus.BAD_REQUEST
    flask_response = jsonify(response)
    flask_response.headers["Cache-Control"] = "no-store"
    return flask_response


@hierarchy_api.get("/local/api/hierarchy/nodes")
def list_hierarchy_nodes():
    service = hierarchy_service()
    return jsonify(
        {
            "parent": {
                "node_id": service.node_id,
                "node_type": "local_hub",
                "parent_node_id": None,
                "upstream_active": service.repository.upstream_active(),
            },
            "children": service.repository.list_children(),
        }
    )


@hierarchy_api.post("/local/api/hierarchy/children/enrollments")
def enroll_hierarchy_child():
    try:
        body = _json_object(
            allowed={"node_id", "display_name", "descendant_node_ids"},
            required={"node_id"},
        )
        descendants = body.get("descendant_node_ids", [])
        if not isinstance(descendants, list) or not all(isinstance(value, str) for value in descendants):
            raise ValueError("descendant_node_ids must be an array of node IDs")
        enrolled = hierarchy_service().enroll_child(
            body["node_id"],
            display_name=body.get("display_name"),
            descendant_node_ids=descendants,
        )
    except (HierarchyConflictError, ValueError) as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.CONFLICT
    response = jsonify(
        {
            **enrolled,
            "sync_path": f"/sync/v1/nodes/{enrolled['node_id']}/exchange",
            "credential_delivery": "one_time",
        }
    )
    response.status_code = HTTPStatus.CREATED
    response.headers["Cache-Control"] = "no-store"
    return response


@hierarchy_api.post("/local/api/hierarchy/children/<node_id>/revoke")
def revoke_hierarchy_child(node_id: str):
    try:
        child = hierarchy_service().repository.revoke_child(node_id)
    except (HierarchyNotFoundError, ValueError):
        return jsonify({"error": "child node not found"}), HTTPStatus.NOT_FOUND
    return jsonify(child)


@hierarchy_api.get("/local/api/hierarchy/events")
def list_hierarchy_events():
    try:
        limit = int(request.args.get("limit", "100"))
        events = hierarchy_service().repository.list_events(limit=limit)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
    return jsonify({"items": events, "count": len(events)})


@hierarchy_api.put("/local/api/hierarchy/desired-resources")
def set_hierarchy_desired_resource():
    try:
        body = _json_object(
            allowed={"resource_type", "resource_id", "target_node_id", "operation", "payload"},
            required={"resource_type", "resource_id", "target_node_id", "operation", "payload"},
        )
        resource = hierarchy_service().repository.set_downstream_desired(
            resource_type=body["resource_type"],
            resource_id=body["resource_id"],
            target_node_id=body["target_node_id"],
            operation=body["operation"],
            payload=body["payload"],
        )
    except HierarchyNotFoundError:
        return jsonify({"error": "target node is not in this Local Hub subtree"}), HTTPStatus.NOT_FOUND
    except (HierarchyCapacityError, HierarchyConflictError, ValueError) as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.CONFLICT
    return jsonify(resource)


@hierarchy_api.post("/local/api/hierarchy/commands")
def create_hierarchy_command():
    try:
        body = _json_object(
            allowed={
                "target_node_id",
                "command_type",
                "device_id",
                "payload",
                "expires_in_seconds",
                "idempotency_key",
            },
            required={"target_node_id", "command_type", "payload", "expires_in_seconds"},
        )
        command = hierarchy_service().create_downstream_command(
            target_node_id=body["target_node_id"],
            command_type=body["command_type"],
            device_id=body.get("device_id"),
            payload=body["payload"],
            expires_in_seconds=body["expires_in_seconds"],
            idempotency_key=body.get("idempotency_key"),
        )
    except HierarchyNotFoundError:
        return jsonify({"error": "target node is not in this Local Hub subtree"}), HTTPStatus.NOT_FOUND
    except (HierarchyCapacityError, HierarchyConflictError, ValueError) as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.CONFLICT
    return jsonify(command), HTTPStatus.CREATED


def _bearer_token() -> str | None:
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :]
    if NODE_BEARER_TOKEN.fullmatch(token) is None:
        return None
    return token


def _node_authentication_error():
    response = jsonify({"error": "invalid_node_credential"})
    response.status_code = HTTPStatus.UNAUTHORIZED
    response.headers["WWW-Authenticate"] = 'Bearer realm="inas-sync-v1"'
    response.headers["Cache-Control"] = "no-store"
    return response


def _read_sync_document() -> dict[str, Any]:
    media_type = request.headers.get("Content-Type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise _SyncHTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "content_type_must_be_application_json")
    if request.content_length is not None and request.content_length > MAX_SYNC_BODY_BYTES:
        raise _SyncHTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "sync_body_too_large")
    raw = request.stream.read(MAX_SYNC_BODY_BYTES + 1)
    if len(raw) > MAX_SYNC_BODY_BYTES:
        raise _SyncHTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "sync_body_too_large")
    content_encoding = request.headers.get("Content-Encoding", "").strip().lower()
    if content_encoding == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_SYNC_BODY_BYTES + 1)
        except (EOFError, OSError) as exc:
            raise _SyncHTTPError(HTTPStatus.BAD_REQUEST, "invalid_gzip_body") from exc
        if len(raw) > MAX_SYNC_BODY_BYTES:
            raise _SyncHTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "sync_body_too_large")
    elif content_encoding:
        raise _SyncHTTPError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_content_encoding")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _SyncHTTPError(HTTPStatus.BAD_REQUEST, "invalid_json_body") from exc
    if not isinstance(document, dict):
        raise _SyncHTTPError(HTTPStatus.BAD_REQUEST, "sync_body_must_be_object")
    return document


def _json_object(*, allowed: set[str], required: set[str]) -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    missing = required - set(body)
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
    unknown = set(body) - allowed
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(sorted(unknown))}")
    return body


class _SyncHTTPError(RuntimeError):
    def __init__(self, status: HTTPStatus, code: str):
        self.status = status
        self.code = code
        super().__init__(code)
