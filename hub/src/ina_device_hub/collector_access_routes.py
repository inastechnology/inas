"""Human administrator routes for AI collector access."""

from flask import Blueprint, jsonify, render_template, request

from ina_device_hub.cloudflare_token_connector import TokenProvisioningError
from ina_device_hub.collector_access_repository import CollectorStorageError
from ina_device_hub.collector_access_service import CollectorAccessService
from ina_device_hub.field_repository import field_repository
from ina_device_hub.user_context import authentication_mode, current_user_from_request

collector_access_routes = Blueprint("collector_access", __name__)


def collector_service():
    return CollectorAccessService(field_repository())


@collector_access_routes.before_request
def require_admin():
    user = current_user_from_request(request)
    if user.role != "admin":
        return jsonify({"error": "administrator role is required"}), 403
    if request.method != "GET" and (authentication_mode() != "cloudflare_access" or not user.authenticated):
        return jsonify({"error": "authenticated Cloudflare administrator is required"}), 403
    return None


@collector_access_routes.errorhandler(TokenProvisioningError)
@collector_access_routes.errorhandler(CollectorStorageError)
def collector_error(error):
    return jsonify({"error": str(error)}), 400


@collector_access_routes.get("/settings/ai-access")
def collector_page():
    service = collector_service()
    return render_template("collector_access.html", configured=service.connector.configured, fields=service.fields.list())


@collector_access_routes.get("/local/api/settings/ai-access")
def collector_list():
    return jsonify({"items": collector_service().list()})


@collector_access_routes.post("/local/api/settings/ai-access")
def collector_issue():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object is required"}), 400
    return jsonify(collector_service().issue(payload, current_user_from_request(request).email)), 201


@collector_access_routes.post("/local/api/settings/ai-access/<collector_id>/permissions")
def collector_permissions(collector_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object is required"}), 400
    return jsonify(collector_service().update(collector_id, payload, current_user_from_request(request).email))


@collector_access_routes.post("/local/api/settings/ai-access/<collector_id>/revoke")
def collector_revoke(collector_id):
    return jsonify(collector_service().revoke(collector_id, current_user_from_request(request).email))
