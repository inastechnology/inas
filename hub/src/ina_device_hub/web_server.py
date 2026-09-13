import csv
import io
import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import plotly
from flask import Flask, Response, g, has_request_context, jsonify, redirect, render_template, render_template_string, request, send_file, stream_template
from plotly import graph_objs as go
from plotly.io import to_html
from werkzeug.exceptions import RequestEntityTooLarge

from ina_device_hub.agri_action_service import METRIC_LABELS, build_action_candidates, build_calendar_operation_readiness
from ina_device_hub.ai_content_service import AIRequestError, ai_content_service
from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.camera_growth_monitoring_service import (
    CameraGrowthAIUnavailableError,
    CameraGrowthAnalysisError,
    CameraGrowthCaptureError,
    CameraGrowthMonitoringNotFoundError,
    CameraGrowthMonitoringValidationError,
    camera_growth_monitoring_service,
)
from ina_device_hub.camera_management_service import (
    CameraNotFoundError,
    CameraRemovalConflictError,
    CameraValidationError,
    camera_management_service,
)
from ina_device_hub.collection_search import matches_search, paginate, search_terms
from ina_device_hub.cultivation_research_repository import cultivation_research_repository
from ina_device_hub.cultivation_research_service import analyze_correlation, build_research_dataset
from ina_device_hub.device_config_repository import (
    DeviceConfigValidationError,
    DeviceRecordValidationError,
    DeviceStateConflictError,
)
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.device_definition_registry import (
    device_kind_label as definition_device_kind_label,
)
from ina_device_hub.device_definition_registry import (
    get_device_definition,
    project_runtime_config,
    value_at_path,
)
from ina_device_hub.device_event_log import list_device_events
from ina_device_hub.device_operational_alert import device_operational_error_details
from ina_device_hub.device_output_capabilities import (
    device_output_capabilities,
    equipment_type_from_notes,
    equipment_types_for_role,
    infer_equipment_type,
    supported_output_ids,
)
from ina_device_hub.device_removal_service import DeviceRemovalConflictError, device_removal_service
from ina_device_hub.discord_notification_service import (
    cloudflare_public_base_url,
    discord_notification_service,
    reload_discord_notification_settings,
)
from ina_device_hub.extension_installation_service import (
    MAX_PACKAGE_BYTES,
    ExtensionInstallError,
    ExtensionReviewError,
    extension_installation_service,
)
from ina_device_hub.extension_registry import build_device_detail_extensions
from ina_device_hub.field_calendar_view import build_calendar_todo_items as _build_calendar_todo_items
from ina_device_hub.field_layout_collaboration_service import (
    FieldLayoutCollaborationValidationError,
    field_layout_collaboration_service,
)
from ina_device_hub.field_layout_repository import (
    FieldLayoutConflictError,
    FieldLayoutValidationError,
    field_layout_repository,
)
from ina_device_hub.field_record_calendar import (
    build_field_record_calendar as _build_field_record_calendar,
)
from ina_device_hub.field_record_calendar import (
    record_month_start as _record_month_start,
)
from ina_device_hub.field_record_catalog import (
    FIELD_RECORD_CATALOG,
    FIELD_RECORD_CATALOG_BY_KEY,
    FIELD_RECORD_CATEGORIES,
    selected_record_catalog,
)
from ina_device_hub.field_record_media_service import (
    FieldRecordMediaStorageError,
    FieldRecordMediaValidationError,
    field_record_media_service,
)
from ina_device_hub.field_repository import FieldValidationError, field_repository
from ina_device_hub.field_status_dashboard import build_field_status_dashboard as _build_field_status_dashboard
from ina_device_hub.firmware_release_module import (
    FirmwareUploadTooLargeError,
    FirmwareUploadValidationError,
    normalize_firmware_upload,
)
from ina_device_hub.hierarchy_api import hierarchy_api
from ina_device_hub.instagram_client import InstagramClient
from ina_device_hub.instagram_post_task import reload_instagram_post_task_settings
from ina_device_hub.instagram_sensor_feed_task import reload_instagram_sensor_feed_task_settings
from ina_device_hub.location_repository import location_repository
from ina_device_hub.operations_api import operations_api
from ina_device_hub.ota_update_service import FirmwareArtifactValidationError, extract_firmware_manifest, ota_update_service
from ina_device_hub.plant_action_decision_service import PlantActionDecisionService
from ina_device_hub.plant_action_review_service import PlantActionAuthorizationError, PlantActionReviewService
from ina_device_hub.plant_calendar_generation_task import plant_calendar_generation_task
from ina_device_hub.plant_calendar_prompt import (
    DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE,
    PLANT_CALENDAR_PROMPT_MAX_LENGTH,
    validate_plant_calendar_prompt_template,
)
from ina_device_hub.plant_management_repository import (
    PlantManagementConflictError,
    PlantManagementNotFoundError,
    PlantManagementValidationError,
    plant_management_repository,
)
from ina_device_hub.plant_question_policy import validate_plant_question
from ina_device_hub.post_watering_moisture_service import (
    DEFAULT_MEASUREMENT_SOURCE,
    DEFAULT_MINIMUM_PERCENT,
    DEFAULT_WINDOW_DAYS,
    MAX_WINDOW_DAYS,
    MIN_WINDOW_DAYS,
    SOIL_MOISTURE_DEVICE_KINDS,
    PostWateringMoistureValidationError,
    post_watering_moisture_service,
    post_watering_rule_views,
    soil_moisture_measurements_from_status_history,
    soil_moisture_sensor_options,
    soil_moisture_source_label,
    soil_moisture_source_options,
    soil_moisture_source_value,
)
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.sensor_measurement_repository import extract_measurements_from_status, metric_supported_for_device_kind, sensor_measurement_repository
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.timelapse_media_service import timelapse_media_service
from ina_device_hub.user_context import (
    AccessAuthenticationError,
    authenticate_request,
    authentication_mode,
    current_user_from_request,
)
from ina_device_hub.user_preference_repository import (
    DEFAULT_CONTRAST_MODE,
    DEFAULT_CULTIVATION_EXPERIENCE_LEVEL,
    DEFAULT_FONT_SIZE,
    SUPPORTED_CONTRAST_MODES,
    SUPPORTED_CULTIVATION_EXPERIENCE_LEVELS,
    SUPPORTED_FONT_SIZES,
    UserPreferenceConflictError,
    UserPreferenceValidationError,
    effective_preferences,
    user_preference_repository,
)
from ina_device_hub.utils import Utils
from ina_device_hub.weather_record_repository import weather_record_repository

app = Flask(__name__)
app.register_blueprint(operations_api)
app.register_blueprint(hierarchy_api)
app.config["MAX_CONTENT_LENGTH"] = int((setting().get("http") or {}).get("max_request_bytes", 64 * 1024 * 1024))
MQTT_ADMIN_STATUS_HISTORY_LIMIT = 2000
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_HEALTH_PATHS = {"/healthz", "/readyz"}
PUBLIC_DEVICE_PATH_PREFIXES = ("/firmware/",)
NODE_SYNC_PATH_PREFIX = "/sync/v1/nodes/"
ADMIN_PATH_PREFIXES = (
    "/local/api/hierarchy/",
    "/local/api/settings/",
    "/local/api/extensions/",
    "/local/api/firmware-artifacts",
    "/local/api/cameras",
    "/cameras",
)
ADMIN_MUTATION_PATH_PREFIXES = ("/local/api/mqtt-devices/", "/local/api/device-configs/", "/devices/", "/locations/")
_web_initialized = False
_readiness_checks = {}
FIELD_AREA_TYPE_LABELS = {
    "section": "区画",
    "bed": "ベッド",
    "ridge": "畝",
    "zone": "ゾーン",
    "point": "測点",
    "other": "その他",
}
DEVICE_SCOPE_TYPE_LABELS = {
    "field": "圃場全体",
    "section": "区画",
    "bed": "ベッド",
    "ridge": "畝",
    "zone": "ゾーン",
    "point": "測点",
    "other": "その他",
}
FIELD_ENVIRONMENT_TYPE_OPTIONS = (
    ("outdoor", "屋外（露地）"),
    ("greenhouse", "ハウス・温室内"),
    ("indoor", "屋内"),
    ("semi_outdoor", "半屋外"),
    ("other", "その他"),
)
FIELD_ENVIRONMENT_TYPE_LABELS = dict(FIELD_ENVIRONMENT_TYPE_OPTIONS)
FIELD_CATALOG_PAGE_SIZE = 18
_RS485_SENSOR_METRIC_SPECS = (
    {
        "chart_kind": "soil_moisture",
        "device_value_key": "moisture_percent",
        "metric": "soil_moisture_percent",
        "label": "土壌水分",
        "unit": "%",
        "digits": 1,
    },
    {
        "chart_kind": "soil_temperature",
        "device_value_key": "temperature_c",
        "metric": "soil_temperature_c",
        "label": "地温",
        "unit": "℃",
        "digits": 1,
    },
    {
        "chart_kind": "soil_ec",
        "device_value_key": "ec_us_cm",
        "metric": "soil_ec_us_cm",
        "label": "土壌EC",
        "unit": "µS/cm",
        "digits": 0,
    },
    {
        "chart_kind": "soil_ph",
        "device_value_key": "ph",
        "metric": "soil_ph",
        "label": "土壌pH",
        "unit": "",
        "digits": 1,
    },
    {
        "chart_kind": "soil_n",
        "device_value_key": "n_mg_kg",
        "metric": "soil_n_mg_kg",
        "label": "土壌窒素",
        "unit": "mg/kg",
        "digits": 0,
    },
    {
        "chart_kind": "soil_p",
        "device_value_key": "p_mg_kg",
        "metric": "soil_p_mg_kg",
        "label": "土壌リン",
        "unit": "mg/kg",
        "digits": 0,
    },
    {
        "chart_kind": "soil_k",
        "device_value_key": "k_mg_kg",
        "metric": "soil_k_mg_kg",
        "label": "土壌カリウム",
        "unit": "mg/kg",
        "digits": 0,
    },
    {
        "chart_kind": "par",
        "device_value_key": "par_umol_m2_s",
        "metric": "par_umol_m2_s",
        "label": "光合成に使える光",
        "unit": "µmol/m²/s",
        "digits": 0,
    },
)
_RS485_TRACE_COLORS = ("#047857", "#2563eb", "#c2410c", "#7c3aed", "#0e7490", "#be123c", "#4d7c0f", "#a16207")


@app.before_request
def authenticate_hub_request():
    if request.path in PUBLIC_HEALTH_PATHS or request.path.startswith(PUBLIC_DEVICE_PATH_PREFIXES) or request.path.startswith(NODE_SYNC_PATH_PREFIX):
        return None
    try:
        user = authenticate_request(request)
    except AccessAuthenticationError as exc:
        if request.path.startswith("/operations/api/"):
            discord_notification_service().notify_operations_security_alert(
                str(exc),
                {
                    "method": request.method,
                    "path": request.path,
                    "client_ip": request.headers.get("CF-Connecting-IP") or request.remote_addr,
                    "cf_ray": request.headers.get("CF-Ray"),
                    "user_agent": request.headers.get("User-Agent"),
                },
            )
        return _access_error_response(str(exc), 401)

    if authentication_mode() == "cloudflare_access" and _admin_access_required(request.path, request.method) and user.role != "admin":
        return _access_error_response("administrator role is required", 403)
    if (
        authentication_mode() == "cloudflare_access"
        and request.method not in SAFE_HTTP_METHODS
        and not request.path.startswith("/operations/api/")
        and not _is_same_origin_request()
    ):
        app.logger.warning(
            "Rejected browser write by same-origin policy: method=%s path=%s origin_present=%s sec_fetch_site=%s forwarded_host_present=%s "
            "forwarded_proto_present=%s public_origin_configured=%s",
            request.method,
            request.path,
            bool(request.headers.get("Origin", "").strip()),
            request.headers.get("Sec-Fetch-Site", "").strip().lower() or "missing",
            bool(request.headers.get("X-Forwarded-Host", "").strip()),
            bool(request.headers.get("X-Forwarded-Proto", "").strip()),
            bool(cloudflare_public_base_url()),
        )
        return _access_error_response("same-origin request is required", 403)
    return None


@app.after_request
def apply_security_headers(response):
    if (
        request.path.startswith("/settings")
        or request.path.startswith(("/local/api/settings/", "/local/api/extensions/", "/local/api/cameras", "/local/api/hierarchy/", "/sync/v1/", "/cameras"))
        or request.path.startswith("/camera/")
        or "/growth-monitoring" in request.path
        or "/camera-growth-assessments" in request.path
    ):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    response.headers.setdefault("Permissions-Policy", "microphone=(), geolocation=()")
    if authentication_mode() == "cloudflare_access":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.errorhandler(RequestEntityTooLarge)
def request_entity_too_large(_error):
    if request.path.startswith(("/local/api/", "/operations/api/", "/sync/v1/")):
        return jsonify({"error": "request body is too large"}), 413
    return Response("request body is too large", status=413, mimetype="text/plain")


def _admin_access_required(path: str, method: str) -> bool:
    if any(path == prefix or path.startswith(prefix) for prefix in ADMIN_PATH_PREFIXES):
        return True
    return method not in SAFE_HTTP_METHODS and any(path.startswith(prefix) for prefix in ADMIN_MUTATION_PATH_PREFIXES)


def _access_error_response(message: str, status: int):
    if request.path.startswith(("/local/api/", "/operations/api/")):
        return jsonify({"error": message}), status
    return Response(message, status=status, mimetype="text/plain")


def _is_same_origin_request() -> bool:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
    if fetch_site == "same-origin":
        return True
    if fetch_site in {"cross-site", "same-site"}:
        return False

    origin = request.headers.get("Origin", "").strip()
    if not origin:
        return False
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/")
    ):
        return False
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip()
    scheme = forwarded_proto or request.scheme
    forwarded_host = request.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
    host = forwarded_host or request.host
    if parsed.scheme.lower() == scheme.lower() and parsed.netloc.lower() == host.lower():
        return True

    public_base_url = cloudflare_public_base_url()
    browser_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    return bool(public_base_url and browser_origin == public_base_url.lower())


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


@app.route("/readyz", methods=["GET"])
def readyz():
    checks = {"web": _web_initialized}
    for name, check in _readiness_checks.items():
        try:
            checks[name] = bool(check())
        except Exception:
            checks[name] = False
    ready = all(checks.values())
    return jsonify({"status": "ready" if ready else "not_ready", "checks": checks}), 200 if ready else 503


def register_readiness_check(name: str, check):
    _readiness_checks[name] = check


LAYOUT_PLACEMENT_LABELS = {
    "greenhouse": "ハウス",
    "open_field": "露地エリア",
    "shade_area": "日陰エリア",
    "ridge": "畝",
    "tree": "植木",
    "pot": "鉢",
    "hydroponic_bed": "水耕ベッド",
    "watering_device": "潅水設備",
    "sensor": "センサー",
    "camera": "カメラ",
    "irrigation_line": "配管（既存データ）",
    "tank": "タンク",
    "grow_light": "植物育成ライト",
    "mister": "噴霧器",
    "fan": "送風機",
    "hvac": "空調",
}
LAYOUT_CULTIVATION_PRESETS = {"ridge", "tree", "pot", "hydroponic_bed"}
FIELD_GROWTH_STAGE_OPTIONS = (
    "未作付け",
    "播種",
    "発芽",
    "育苗",
    "定植",
    "活着",
    "栄養成長",
    "開花",
    "結実",
    "果実肥大",
    "成熟",
    "収穫期",
    "休眠",
    "栽培終了",
)
FIELD_CULTIVATION_METHOD_OPTIONS = (
    "露地栽培",
    "ハウス栽培",
    "鉢・プランター栽培",
    "水耕栽培",
    "養液土耕",
    "培地栽培",
    "屋内栽培",
    "その他",
)
FIELD_CROP_CULTIVAR_SUGGESTIONS = {
    "イチゴ": ["章姫", "紅ほっぺ", "とちおとめ", "よつぼし"],
    "ブルーベリー": ["オニール", "ティフブルー", "ブライトウェル", "デューク"],
    "トマト": ["桃太郎", "アイコ", "千果", "麗夏"],
    "ミニトマト": ["アイコ", "千果", "オレンジ千果"],
    "ナス": ["千両二号", "庄屋大長", "筑陽"],
    "キュウリ": ["夏すずみ", "VR夏すずみ", "シャキット"],
    "ピーマン": ["京波", "ニューエース", "こどもピーマン"],
    "レタス": ["シスコ", "サウザー", "グリーンウェーブ"],
    "ホウレンソウ": ["おかめ", "次郎丸", "弁天丸"],
    "バジル": ["スイートバジル", "レモンバジル", "ホーリーバジル"],
}
JAPAN_PREFECTURES = (
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
)


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return Response(status=204)


DEVICE_ROLE_LABELS = {
    "environment": "環境センサー",
    "soil": "土壌センサー",
    "watering": "水やり機",
    "camera": "カメラ",
    "actuator": "制御デバイス",
    "sensor": "センサー",
    "other": "その他",
}


def _local_timezone():
    default_timezone_name = "Asia/Tokyo"
    if not has_request_context():
        return ZoneInfo(default_timezone_name)
    cached = getattr(g, "ina_display_timezone", None)
    if cached is not None:
        return cached
    timezone_name = default_timezone_name
    try:
        user = current_user_from_request(request)
        timezone_name = str(_current_user_preferences(user.email).get("timezone") or default_timezone_name)
    except Exception:  # noqa: BLE001
        app.logger.warning("Unable to load the current user's display timezone; using Asia/Tokyo")
    try:
        resolved = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        app.logger.warning(f"Unknown display timezone {timezone_name!r}; using Asia/Tokyo")
        resolved = ZoneInfo(default_timezone_name)
    g.ina_display_timezone = resolved
    return resolved


def _to_local_datetime(value):
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(_local_timezone())


def _to_local_plot_time(value):
    local_dt = _to_local_datetime(value)
    if local_dt is None:
        return None
    return local_dt.replace(tzinfo=None)


def _normalize_display_value(value):
    if value is None:
        return "null"
    return value


def _build_telemetry_monitoring(latest_sensor_data):
    if latest_sensor_data is None:
        return []

    monitoring = []
    age = datetime.now(UTC).astimezone() - latest_sensor_data["updated_at"]
    age_hours = age.total_seconds() / 3600

    if age >= timedelta(hours=6):
        monitoring.append(
            {
                "severity": "warning",
                "message": f"最終受信から {age_hours:.1f} 時間経過。低電圧または通信異常の可能性があります。",
            }
        )
    elif age >= timedelta(hours=3):
        monitoring.append(
            {
                "severity": "attention",
                "message": f"最終受信から {age_hours:.1f} 時間経過。未着注意です。",
            }
        )

    battery_v = latest_sensor_data.get("telemetry", {}).get("battery_v")
    if isinstance(battery_v, int | float):
        if battery_v < 3.2:
            monitoring.append(
                {
                    "severity": "warning",
                    "message": f"battery_v={battery_v}V。送信停止域として扱います。",
                }
            )
        elif battery_v < 3.4:
            monitoring.append(
                {
                    "severity": "attention",
                    "message": f"battery_v={battery_v}V。低電圧警告です。",
                }
            )

    return monitoring


@app.route("/", methods=["GET"])
def index():
    return _render_field_catalog(home_mode=True)


@app.route("/inas-app", methods=["GET"])
def inas_app_landing_page():
    return render_template("inas_app.html")


@app.route("/devices/<device_id>", methods=["GET"])
def get_device_info(device_id):
    device_info = sensor_device_repository().get(device_id)
    print(device_info)
    if device_info is None:
        return jsonify({"error": "device not found"}), 404

    latest_sensor_data = sensor_data_repository().get_latest(device_id)
    latest_aggregated_data = sensor_data_repository().get_latest_aggreated(device_id)
    latest_telemetry = latest_sensor_data.get("telemetry", {}) if latest_sensor_data else {}
    telemetry_monitoring = _build_telemetry_monitoring(latest_sensor_data)

    # plotly でグラフを描画
    # 画像を base64 エンコードして HTML に埋め込む
    agg_sensor_graph = Utils.create_latest_aggregated_graph_as_html(device_id, latest_aggregated_data)

    template = """
    <html>
      <head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/hub-ui.css"></head>
      <body class="hub-shell hub-legacy {{ accessibility_body_class }}">
        <p><a href="/fields">圃場一覧</a> / <a href="/mqtt-devices">機器保守</a></p>
        <h1>旧センサー詳細</h1>
        <h2>{{ device_id }}</h2>
          <li>Name: {{ info.name }}</li>
          <li>Location: {{ info.location }}</li>
          <li>Info: {{ info.info }}</li>
        <br>
        <h2>Last Sensor Data{% if latest_sensor_data %} ({{ latest_sensor_data.updated_at }}){% endif %}</h2>
        {% if latest_sensor_data %}
        <ul>
          <li>Temp: {{ latest_sensor_data.temp }}</li>
          <li>TDS: {{ latest_sensor_data.tds }}</li>
        </ul>
        {% else %}
        <p>No sensor data</p>
        {% endif %}
        <br>
        <h2>Farm Telemetry</h2>
        {% if latest_telemetry %}
        <ul>
          <li>Payload Device ID: {{ latest_telemetry.get("device_id") }}</li>
          <li>Payload Timestamp: {{ latest_telemetry.get("timestamp") }}</li>
          <li>Soil Moisture 1 Raw: {{ normalize_display_value(latest_telemetry.get("soil_moisture_1_raw")) }}</li>
          <li>Soil Moisture 1 %: {{ normalize_display_value(latest_telemetry.get("soil_moisture_1_pct")) }}</li>
          <li>Soil Moisture 2 Raw: {{ normalize_display_value(latest_telemetry.get("soil_moisture_2_raw")) }}</li>
          <li>Soil Moisture 2 %: {{ normalize_display_value(latest_telemetry.get("soil_moisture_2_pct")) }}</li>
          <li>Soil Temp C: {{ normalize_display_value(latest_telemetry.get("soil_temp_c")) }}</li>
          <li>Battery V: {{ normalize_display_value(latest_telemetry.get("battery_v")) }}</li>
          <li>RSSI: {{ normalize_display_value(latest_telemetry.get("rssi")) }}</li>
        </ul>
        {% else %}
        <p>No farm telemetry</p>
        {% endif %}
        <br>
        <h2>Monitoring</h2>
        {% if telemetry_monitoring %}
        <ul>
          {% for item in telemetry_monitoring %}
          <li>[{{ item.severity }}] {{ item.message }}</li>
          {% endfor %}
        </ul>
        {% else %}
        <p>No active alerts</p>
        {% endif %}
        <br>
        <h2>Graph</h2>
        <div>
          {{ agg_sensor_graph | safe }}
        </div>
        <br>
        <button type="button" onclick="location.href='/devices/{{ device_id }}/latest_image'">Latest Image</button>
        <button type="button" onclick="location.href='/devices/{{ device_id }}/edit'">Edit</button>
      </body>
    </html>
    """

    return render_template_string(
        template,
        device_id=device_id,
        info=device_info,
        agg_sensor_graph=agg_sensor_graph,
        latest_sensor_data=latest_sensor_data,
        latest_telemetry=latest_telemetry,
        telemetry_monitoring=telemetry_monitoring,
        normalize_display_value=_normalize_display_value,
    )


@app.route("/devices/<device_id>/edit", methods=["GET", "POST"])
def edit_device_info(device_id):
    device_info = sensor_device_repository().get(device_id)
    if not device_info:
        return jsonify({"error": "device not found"}), 404

    if request.method == "POST":
        sensor_device_repository().add(
            device_id,
            {
                "name": request.form.get("name", "").strip(),
                "location": request.form.get("location", "").strip(),
                "info": request.form.get("info", "").strip(),
            },
        )
        return redirect(f"/devices/{device_id}")

    device_name = device_info.get("name", "")
    device_location = device_info.get("location", "")
    device_info_text = device_info.get("info", "")
    template = """
    <html>
      <head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/hub-ui.css"></head>
      <body class="hub-shell hub-legacy {{ accessibility_body_class }}">
        <h1>旧センサー情報を編集</h1>
        <form method="post">
          <label for="name">Name</label>
          <input type="text" id="name" name="name" value="{{ device_name }}">
          <label for="location">Location</label>
          <input type="text" id="location" name="location" value="{{ device_location }}">
          <label for="info">Info</label>
          <textarea id="info" name="info">{{ device_info_text }}</textarea>
          <br>
          <br>
          <a href="/devices/{{ device_id }}">Back</a>
          <br>
          <br>
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """

    return render_template_string(
        template,
        device_name=device_name,
        device_location=device_location,
        device_info_text=device_info_text,
        device_id=device_id,
    )


@app.route("/devices/<device_id>/latest_image", methods=["GET"])
def get_latest_image(device_id):
    """
    デバイスIDに紐づく最新の画像を取得するエンドポイント

    Parameters
    ----------
    device_id : str
        デバイスID

    Returns
    -------
    response : http response
        デバイスIDに紐づく最新の画像を base64 エンコードしたもの
    """
    image_repo = sensor_image_repogitory()
    sensor_images = image_repo.fetch_latest(device_id, limit=24)
    if not sensor_images:
        return jsonify({"error": "no image"}), 404

    return render_template("image_page.html", sensor_images=sensor_images, device_id=device_id)


@app.route("/locations", methods=["GET"])
def get_location_list():
    locations = location_repository().get_all()
    template = """
    <html>
      <head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/hub-ui.css"></head>
      <body class="hub-shell hub-legacy {{ accessibility_body_class }}">
        <h1>旧ロケーション一覧</h1>
        <ul>
          {% for location_id, info in locations.items() %}
          <li>
            <a href="/locations/{{ location_id }}">{{ location_id }}</a>
          </li>
          {% endfor %}
        </ul>
        <button type="button" onclick="location.href='/locations/add'">Add</button>
      </body>
    </html>
    """

    return render_template_string(template, locations=locations)


@app.route("/locations/add", methods=["GET", "POST"])
def add_location():
    if request.method == "POST":
        location_id = uuid.uuid4().hex
        location_name = request.form.get("location_name")
        location_description = request.form.get("location_description")
        location_image = request.files.get("location_image")
        # save image to cloud
        image_key = f"locations/{location_id}/{os.path.basename(location_image.filename)}"
        image_path = storage_connector().save_to_cloud(image_key, location_image.read(), "image/jpeg")
        location_repository().add(
            location_id,
            {
                "name": location_name,
                "description": location_description,
                "image_path": image_path,
            },
        )
        return jsonify({"message": "added"})

    template = """
    <html>
      <head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/static/hub-ui.css"></head>
      <body class="hub-shell hub-legacy {{ accessibility_body_class }}">
        <h1>旧ロケーションを追加</h1>
        <form method="post" enctype="multipart/form-data">
          <label for="location_name">Location Name</label>
          <input type="text" id="location_name" name="location_name">
          <label for="location_description">Location Description</label>
          <input type="text" id="location_description" name="location_description">
          <h3>Location Image</h3>
          <input type="file" id="location_image" name="location_image">
          <br>
          <br>
          <a href="/locations">Back</a>
          <br>
          <br>
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """

    return render_template_string(template)


@app.route("/cameras/new", methods=["GET"])
def new_camera_page():
    return render_template("camera_form.html", camera=None, form_mode="create")


@app.route("/cameras/<device_id>/edit", methods=["GET"])
def edit_camera_page(device_id):
    camera = camera_management_service().get(device_id)
    if camera is None:
        return jsonify({"error": "camera not found"}), 404
    return redirect(f"/camera/{quote(str(device_id), safe='')}#settings")


@app.route("/local/api/cameras", methods=["GET", "POST"])
def cameras_api():
    service = camera_management_service()
    if request.method == "GET":
        cameras = service.list(query=request.args.get("q", ""))
        return jsonify({"items": cameras, "total": len(cameras)})
    request_body = request.get_json(silent=True)
    try:
        created = service.create(request_body)
    except CameraValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(created), 201


@app.route("/local/api/cameras/test-connection", methods=["POST"])
def test_camera_connection_api():
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    payload = dict(request_body)
    device_id = str(payload.pop("device_id", "") or "").strip() or None
    try:
        result = camera_management_service().test_connection(payload, device_id=device_id)
    except CameraNotFoundError:
        return jsonify({"error": "camera not found"}), 404
    except CameraValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/local/api/cameras/<device_id>", methods=["GET", "PATCH", "DELETE"])
def camera_api(device_id):
    service = camera_management_service()
    if request.method == "GET":
        camera = service.get(device_id)
        return jsonify(camera) if camera is not None else (jsonify({"error": "camera not found"}), 404)
    if request.method == "DELETE":
        user = current_user_from_request(request)
        try:
            deleted = service.delete(device_id, deleted_by=user.email or "local-operator")
        except CameraRemovalConflictError as exc:
            return jsonify({"error": str(exc), "references": exc.references}), 409
        if deleted is None:
            return jsonify({"error": "camera not found"}), 404
        return jsonify({"deleted": True, "device_id": device_id})
    request_body = request.get_json(silent=True)
    try:
        updated = service.update(device_id, request_body)
    except CameraNotFoundError:
        return jsonify({"error": "camera not found"}), 404
    except CameraValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(updated)


@app.route("/camera/<device_id>", methods=["GET"])
def camera_detail_page(device_id):
    service = camera_management_service()
    camera = service.get(device_id)
    if camera is None:
        return jsonify({"error": "camera not found"}), 404
    media_service = timelapse_media_service()
    images = media_service.list_frame_records(device_id, limit=24)
    list_videos = getattr(media_service, "list_video_records", None)
    videos = list_videos(device_id, limit=1) if callable(list_videos) else []
    return render_template(
        "camera_detail.html",
        camera=camera,
        references=service.references(device_id),
        initial_images=images,
        latest_video=videos[0] if videos else None,
        current_user=current_user_from_request(request),
    )


@app.route("/camera/<device_id>/preview", methods=["GET"])
def preview_camera(device_id):
    if camera_management_service().get(device_id) is None:
        return jsonify({"error": "camera not found"}), 404
    return redirect(f"/camera/{quote(str(device_id), safe='')}#live")


@app.route("/camera/<device_id>/images", methods=["GET"])
def camera_images(device_id):
    if camera_management_service().get(device_id) is None:
        return jsonify({"error": "camera not found"}), 404
    date_value = request.args.get("date", "").strip()
    query = f"?{urlencode({'start_date': date_value, 'end_date': date_value})}" if date_value else ""
    return redirect(f"/camera/{quote(str(device_id), safe='')}{query}#captures")


def _build_mqtt_admin_view(
    devices,
    selected_device_id,
    selected_device,
    selected_statuses,
    selected_ota_statuses,
    *,
    layout_context=None,
    connection_events=None,
):
    now = datetime.now(UTC)
    device_summaries = [
        _build_device_summary(device_id, record, now) for device_id, record in sorted(devices.items(), key=lambda item: _device_sort_key(item[0], item[1]))
    ]
    return {
        "devices": device_summaries,
        "operational_error_count": sum(1 for device in device_summaries if device.get("operational_error")),
        "field_zones": _build_field_zones(device_summaries, selected_device_id),
        "selected": _build_selected_device_view(
            selected_device_id,
            selected_device,
            selected_statuses,
            selected_ota_statuses,
            now,
            layout_context=layout_context,
            connection_events=connection_events,
        )
        if selected_device
        else None,
    }


def _build_field_zones(device_summaries, selected_device_id):
    groups = {}
    for device in device_summaries:
        location = device.get("location") or "場所未設定"
        groups.setdefault(location, []).append(device)

    zones = []
    for location, devices in groups.items():
        devices.sort(key=lambda item: str(item.get("name") or item.get("id") or ""))
        primary = next((device for device in devices if device.get("id") == selected_device_id), devices[0])
        rows = []
        for device in devices:
            rows.append(
                {
                    "id": device["id"],
                    "name": device["name"],
                    "kind_label": device["kind_label"],
                    "watering": "運転異常" if device.get("operational_error") else device["watering_label"],
                    "soil": device["soil_moisture"],
                    "last_seen_age": device["last_seen_age"],
                    "class": _field_device_class(device),
                    "selected": device["id"] == selected_device_id,
                }
            )
        zone_class = _highest_priority_class(row["class"] for row in rows)
        zones.append(
            {
                "name": location,
                "primary_device_id": primary["id"],
                "device_count": len(devices),
                "class": zone_class,
                "selected": any(row["selected"] for row in rows),
                "rows": rows,
                "empty_rows": list(range(max(0, 3 - len(rows)))),
            }
        )
    zones.sort(key=lambda item: (0 if item["selected"] else 1, item["name"]))
    return zones


def _field_device_class(device):
    if device.get("operational_error"):
        return "danger"
    if device.get("state_class") in {"danger", "warn"}:
        return device["state_class"]
    if device.get("watering_class") == "good":
        return "good"
    if device.get("watering_class") == "warn":
        return "warn"
    if device.get("soil_moisture") == "未取得" or device.get("last_seen_age") == "未取得":
        return "muted"
    return "ok"


def _highest_priority_class(classes):
    priority = {"danger": 0, "warn": 1, "good": 2, "ok": 3, "muted": 4}
    return min(classes, key=lambda value: priority.get(value, 9), default="muted")


def _format_firmware_artifacts_for_ui(firmware_artifacts):
    formatted = {}
    for key, artifact in (firmware_artifacts or {}).items():
        if not isinstance(artifact, dict):
            formatted[key] = artifact
            continue
        formatted_artifact = dict(artifact)
        formatted_artifact["created_at"] = _format_datetime(artifact.get("created_at"))
        formatted_artifact["updated_at"] = _format_datetime(artifact.get("updated_at"))
        metadata = artifact.get("firmware_metadata") if isinstance(artifact.get("firmware_metadata"), dict) else {}
        formatted_artifact["manifest_label"] = _firmware_manifest_label(metadata)
        formatted_artifact["option_label"] = _firmware_artifact_option_label(formatted_artifact)
        formatted[key] = formatted_artifact
    return formatted


def _firmware_manifest_label(metadata):
    if not metadata:
        return "未取得"
    details = []
    for key in ("project", "target", "framework"):
        value = metadata.get(key)
        if value:
            details.append(f"{key}={value}")
    return " / ".join(details) if details else "取得済み"


def _firmware_artifact_option_label(artifact):
    label = f"{artifact.get('version') or 'version未設定'}"
    build_id = artifact.get("build_id")
    if build_id:
        label += f" / build {build_id}"
    rollout_state = artifact.get("rollout_state")
    if rollout_state:
        label += f" / {rollout_state}"
    return label


def _build_firmware_target_options(firmware_artifacts, selected_device):
    selected_kind = selected_device.get("device_kind") if isinstance(selected_device, dict) else None
    options = []
    seen_versions = set()
    for artifact in (firmware_artifacts or {}).values():
        if not isinstance(artifact, dict):
            continue
        version = artifact.get("version")
        device_kind = artifact.get("device_kind")
        if not version:
            continue
        if selected_kind and device_kind != selected_kind:
            continue
        if version in seen_versions:
            continue
        seen_versions.add(version)
        options.append(
            {
                "version": version,
                "device_kind": device_kind,
                "label": _firmware_artifact_option_label(artifact),
            }
        )
    options.sort(key=lambda item: (str(item.get("version") or ""), str(item.get("device_kind") or "")), reverse=True)
    current_target = selected_device.get("target_firmware_version") if isinstance(selected_device, dict) else None
    if current_target and current_target not in seen_versions:
        options.insert(
            0,
            {
                "version": current_target,
                "device_kind": selected_kind,
                "label": f"{current_target} / 登録済みF/Wなし",
            },
        )
    return options


def _device_sort_key(device_id, record):
    state_order = {"active": 0, "pending": 1, "disabled": 2, "retired": 3}
    return (state_order.get(record.get("state"), 9), str(record.get("name") or device_id))


def _build_device_summary(device_id, record, now):
    payload = _latest_status_payload(record)
    watering = _watering_state(payload)
    config = record.get("config") or {}
    return {
        "id": device_id,
        "name": record.get("name") or device_id,
        "location": record.get("location") or "場所未設定",
        "kind_label": _device_kind_label(record.get("device_kind")),
        "state_label": _device_state_label(record.get("state")),
        "state_class": _device_state_class(record.get("state")),
        "watering_label": watering["label"],
        "watering_class": watering["class"],
        "soil_moisture": _format_percent(payload.get("last_soil_moisture")),
        "threshold": _format_percent(payload.get("threshold") if payload.get("threshold") is not None else config.get("moisture_threshold")),
        "last_seen": _format_datetime(record.get("last_seen_at") or record.get("last_status_at")),
        "last_seen_age": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
        "next_wake": _format_next_wake(record.get("last_status_at"), payload.get("next_sleep_sec")),
        "firmware": record.get("firmware_version") or "未取得",
        "target_firmware": record.get("target_firmware_version") or "設定なし",
        "operational_error": device_operational_error_details(payload),
        "operational_metrics": _build_device_operational_metrics(record, payload, config, now, watering)[:3],
    }


def _build_selected_device_view(device_id, record, statuses, ota_statuses, now, *, layout_context=None, connection_events=None):
    payload = _latest_status_payload(record)
    config = record.get("config") or {}
    device_kind = record.get("device_kind") or payload.get("device_kind") or ""
    definition = get_device_definition(device_kind)
    watering = _watering_state(payload)
    layout_context = layout_context or {"assigned": False, "assignments": [], "primary_path": "", "primary_href": ""}
    location = layout_context.get("primary_path") or record.get("location") or "未設置"
    soil_moisture = _first_numeric_value(payload, ("soil_moisture_percent", "last_soil_moisture"))
    threshold = payload.get("threshold") if payload.get("threshold") is not None else config.get("moisture_threshold")
    output_settings = _build_device_output_settings(device_kind, config, layout_context)
    scheduled_operation = _build_scheduled_operation_state(definition, config)
    enabled_outputs = [output for output in output_settings["outputs"] if output["enabled"]]
    readiness_checks = [
        {
            "label": "機器と通信",
            "value": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
            "class": "good" if record.get("last_seen_at") or record.get("last_status_at") else "warn",
            "hint": "直近の状態を受信済み" if record.get("last_seen_at") or record.get("last_status_at") else "まだ通信を確認できません",
        },
        {
            "label": "設定の受信",
            "value": "受信済み" if payload.get("config_received") is True else "確認待ち",
            "class": "good" if payload.get("config_received") is True else "warn",
            "hint": "機器がHub設定を読み込みました" if payload.get("config_received") is True else "設定送信後、次回起動を待ちます",
        },
        {
            "label": "時刻合わせ",
            "value": "同期済み" if payload.get("time_synced") is True else "確認待ち",
            "class": "good" if payload.get("time_synced") is True else "warn",
            "hint": "予約時刻の基準は正常です" if payload.get("time_synced") is True else "次回起動時に時刻同期を確認します",
        },
        {
            "label": "出力先",
            "value": f"{len(enabled_outputs)} 系統",
            "class": "good" if enabled_outputs else "muted",
            "hint": "有効なポンプ・バルブ・電源" if enabled_outputs else "出力先が未設定です",
        },
    ]
    return {
        "id": device_id,
        "title": record.get("name") or device_id,
        "location": location,
        "location_href": layout_context.get("primary_href") or "",
        "layout_context": layout_context,
        "memo": record.get("memo") or "",
        "device_kind": device_kind,
        "kind_label": _device_kind_label(device_kind),
        "supports_irrigation": device_kind in {"WTR", "WRS"},
        "supports_fertigation": device_kind == "FGT",
        "post_watering_setup_url": f"/settings/post-watering-moisture?{urlencode({'sensor_device_id': device_id})}",
        "supports_watering_pattern": "watering_pattern" in definition.get("runtime_config", {}).get("send_keys", []),
        "definition": definition,
        "ui_extensions": build_device_detail_extensions(device_kind, device=record, status=payload, config=config),
        "runtime_config_payload": project_runtime_config(device_kind, config),
        "state_label": _device_state_label(record.get("state")),
        "state_class": _device_state_class(record.get("state")),
        "watering": watering,
        "soil_moisture": _format_percent(soil_moisture),
        "threshold": _format_percent(threshold),
        "last_seen": _format_datetime(record.get("last_seen_at") or record.get("last_status_at")),
        "last_seen_age": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
        "next_wake": _format_next_wake(record.get("last_status_at"), payload.get("next_sleep_sec")),
        "next_wake_detail": _format_duration(payload.get("next_sleep_sec")),
        "firmware": record.get("firmware_version") or "未取得",
        "target_firmware": record.get("target_firmware_version") or "設定なし",
        "ota_state": _ota_state_label(record.get("ota_state")),
        "ota_class": _ota_state_class(record.get("ota_state")),
        "ota_error": record.get("ota_error") or "",
        "operational_error": device_operational_error_details(payload),
        "operational_heading": "現在の潅水判断" if device_kind in {"WTR", "WRS"} else "液肥づくりの現在地" if device_kind == "FGT" else "現在の計測・稼働状況",
        "operational_metrics": _build_device_operational_metrics(record, payload, config, now, watering),
        "rs485_sensor_groups": _build_rs485_sensor_groups(payload, device_kind),
        "monitoring_charts": _build_device_monitoring_charts(device_kind, statuses, config),
        "schedules": _format_schedules_for_ui(config.get("schedules") or [], config, scheduled_operation=scheduled_operation),
        "scheduled_operation": scheduled_operation,
        "config_summary": _format_config_summary(config),
        "watering_history": _build_watering_history(statuses, config=config),
        "wake_history": _build_wake_history(statuses),
        "ota_history": _build_ota_history(ota_statuses),
        "readiness_checks": readiness_checks,
        "connection_diagnostics": _build_device_connection_diagnostics(record, connection_events or [], now),
        "output_settings": output_settings,
        "soil_calibration_calibrated": bool((config.get("soil_calibration") or {}).get("calibrated")),
    }


def _build_device_connection_diagnostics(record, connection_events, now):
    last_seen_at = record.get("last_seen_at") or record.get("last_status_at")
    payload = _latest_status_payload(record)
    last_connected = next(
        (event for event in connection_events if event.get("event_type") in {"mqtt_client_connected", "connect"} or event.get("action") == "connect"),
        None,
    )
    if last_connected:
        connection_check = {
            "value": "接続を確認",
            "class": "good",
            "detail": _format_datetime(last_connected.get("occurred_at")),
            "reason": "この時点で、機器はWi-Fiを通ってHubの入口まで到達しています。",
        }
    elif last_seen_at:
        connection_check = {
            "value": "通信を確認",
            "class": "good",
            "detail": _format_datetime(last_seen_at),
            "reason": "Hubが機器の状態を受け取っているため、この時点の接続は成功しています。",
        }
    else:
        connection_check = {
            "value": "記録なし",
            "class": "warn",
            "detail": "まだHubへの接続を確認できません",
            "reason": "機器の電源と初期設定画面を確認し、もう一度接続を試してください。",
        }

    next_wake = _format_next_wake(record.get("last_status_at"), payload.get("next_sleep_sec"))
    return {
        "checks": [
            {
                "step": "1",
                "label": "Hubが最後に確認",
                "value": _format_age(last_seen_at, now),
                "class": "good" if last_seen_at else "warn",
                "detail": _format_datetime(last_seen_at) if last_seen_at else "受信記録はまだありません",
                "reason": (
                    "時刻が更新されていれば、電源・Wi-Fi・Hubへの接続はそこまで成功しています。"
                    if last_seen_at
                    else "ここが未取得なら、まず機器の電源と初期設定を確認します。"
                ),
            },
            {
                "step": "2",
                "label": "Hubへの接続",
                **connection_check,
            },
            {
                "step": "3",
                "label": "次回の通信予定",
                "value": next_wake,
                "class": "ok" if next_wake != "未取得" else "muted",
                "detail": _format_duration(payload.get("next_sleep_sec")) if next_wake != "未取得" else "予定を受信していません",
                "reason": (
                    "省電力機器は予定時刻まで通信を休みます。切断表示だけで故障とは限りません。"
                    if next_wake != "未取得"
                    else "常時接続機器、またはまだ状態を受信していない機器では表示されません。"
                ),
            },
        ],
        "events": [_format_device_connection_event(event, now) for event in connection_events[:8]],
    }


def _format_device_connection_event(event, now):
    event_type = str(event.get("event_type") or "")
    action = str(event.get("action") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    reason = str(payload.get("reason") or "")
    if event_type in {"mqtt_client_connected", "connect"} or action == "connect":
        label = "Hubへの接続に成功"
        description = "機器からHubの入口まで通信できました。"
        event_class = "good"
    elif action == "disconnect_replaced" or reason == "replaced":
        label = "同じ機器番号の接続が重複"
        description = "同じ機器番号を使う機器がほかにないか確認してください。"
        event_class = "warn"
    elif action == "disconnect_timeout" or reason == "timeout":
        label = "通信が途切れて接続を終了"
        description = "電源やWi-Fiの電波が不安定でないか確認してください。"
        event_class = "warn"
    elif event_type in {"mqtt_client_disconnected", "disconnect"} or action.startswith("disconnect"):
        label = "Hubとの接続を終了"
        description = "省電力のため休止する機器では、予定どおりの切断です。"
        event_class = "muted"
    elif event_type == "mqtt_client_connection_attempt":
        label = "Hubへ接続を試行"
        description = "機器からHubの入口へ通信が届きました。接続完了の記録が続くか確認します。"
        event_class = "ok"
    else:
        label = "接続に関する記録"
        description = "詳しい内容は、下部の管理者向けデータで確認できます。"
        event_class = "muted"
    return {
        "label": label,
        "description": description,
        "class": event_class,
        "occurred_at": str(event.get("occurred_at") or ""),
        "time": _format_datetime(event.get("occurred_at")),
        "age": _format_age(event.get("occurred_at"), now),
    }


def _build_device_output_settings(device_kind, config, layout_context):
    definition = get_device_definition(device_kind)
    effective_config = project_runtime_config(device_kind, config)
    scheduled_operation_spec = definition.get("ui", {}).get("scheduled_operation") or {}
    program_enabled_path = scheduled_operation_spec.get("program_required_when_path")
    program_outputs_path = scheduled_operation_spec.get("program_outputs_path")
    program_enabled = value_at_path(effective_config, program_enabled_path) is True if program_enabled_path else False
    output_programs = value_at_path(effective_config, program_outputs_path) if program_outputs_path else None
    output_programs = output_programs if isinstance(output_programs, dict) else {}
    capabilities = device_output_capabilities(device_kind)
    saved_outputs = [item for item in config.get("mosfet_switches") or [] if isinstance(item, dict)] if isinstance(config, dict) else []
    saved_by_id = {str(item.get("switch_id") or ""): item for item in saved_outputs if item.get("switch_id")}
    layout_targets = []
    for assignment in layout_context.get("assignments") or []:
        for target in assignment.get("targets") or []:
            name = str(target.get("name") or "").strip()
            if name and not any(item["value"] == name for item in layout_targets):
                layout_targets.append(
                    {
                        "value": name,
                        "label": name,
                        "equipment_type": infer_equipment_type(name, preset=target.get("preset")),
                        "source": "圃場に配置済み",
                    }
                )

    outputs = []
    for capability in capabilities:
        saved = saved_by_id.get(capability["switch_id"], {})
        output_program = output_programs.get(capability["switch_id"])
        output_program = output_program if isinstance(output_program, dict) else None
        on_sec = output_program.get("on_sec") if output_program else None
        repeat_count = output_program.get("repeat_count") if output_program else None
        programmed = (
            program_enabled
            and isinstance(on_sec, int)
            and not isinstance(on_sec, bool)
            and on_sec > 0
            and isinstance(repeat_count, int)
            and not isinstance(repeat_count, bool)
            and repeat_count > 0
        )
        current_load = str(saved.get("controlled_load") or "").strip()
        equipment_options = []
        for target in layout_targets:
            target_type = target["equipment_type"]
            if target_type == "other":
                target_type = infer_equipment_type(target["value"], role=capability["role"])
            equipment_options.append({**target, "equipment_type": target_type})
        for candidate in capability.get("equipment_presets", ()):
            option_value = str(candidate or "").strip()
            if option_value and not any(item["value"] == option_value for item in equipment_options):
                equipment_options.append(
                    {
                        "value": option_value,
                        "label": option_value,
                        "equipment_type": infer_equipment_type(option_value, role=capability["role"]),
                        "source": "設備の種類",
                    }
                )
        if current_load and not any(item["value"] == current_load for item in equipment_options):
            equipment_options.append(
                {
                    "value": current_load,
                    "label": current_load,
                    "equipment_type": infer_equipment_type(current_load, role=capability["role"]),
                    "source": "現在の設定",
                }
            )
        available_types = equipment_types_for_role(capability["role"])
        saved_type = equipment_type_from_notes(saved.get("notes"))
        allowed_type_values = {item["value"] for item in available_types}
        equipment_type = saved_type if saved_type in allowed_type_values else infer_equipment_type(current_load, role=capability["role"])
        outputs.append(
            {
                **capability,
                "name": str(saved.get("name") or capability["default_name"]).strip(),
                "enabled": programmed if output_program is not None else saved.get("enabled") is not False,
                "programmed": programmed if output_program is not None else None,
                "program_summary": f"{on_sec}秒 × {repeat_count}回" if programmed else "動作しません" if output_program is not None else "",
                "controlled_load": current_load,
                "equipment_type": equipment_type,
                "equipment_types": available_types,
                "equipment_options": equipment_options,
                "notes": str(saved.get("notes") or "").strip(),
            }
        )

    supported_ids = supported_output_ids(device_kind)
    unsupported = [item for item in saved_outputs if str(item.get("switch_id") or "") not in supported_ids]
    ignored_legacy_ids = {"sensor_power"} if str(device_kind or "").upper() == "WTR" else set()
    unsupported_count = sum(1 for item in unsupported if str(item.get("switch_id") or "") not in ignored_legacy_ids)
    return {
        "outputs": outputs,
        "unsupported": unsupported,
        "unsupported_count": unsupported_count,
        "layout_href": (layout_context.get("assignments") or [{}])[0].get("layout_href", "") if layout_context.get("assignments") else "",
    }


def _build_device_layout_context(device_id, record=None):
    assignments = []
    layout_repository = field_layout_repository()
    for field in field_repository().list():
        field_id = field.get("id") or ""
        if not field_id:
            continue
        layout = layout_repository.get(field_id, field_name=field.get("name") or "")
        spaces = {space.get("id"): space for space in layout.get("spaces") or [] if space.get("id")}
        placement_index = {
            placement.get("id"): (space, placement) for space in spaces.values() for placement in space.get("placements") or [] if placement.get("id")
        }
        field_assignments = []
        for space in spaces.values():
            for placement in space.get("placements") or []:
                binding = placement.get("binding") if isinstance(placement.get("binding"), dict) else {}
                if binding.get("device_id") != device_id:
                    continue
                target_items = []
                for target_id in binding.get("target_placement_ids") or []:
                    target_location = placement_index.get(target_id)
                    if target_location is None:
                        continue
                    target_space, target = target_location
                    target_items.append(
                        {
                            "id": target_id,
                            "name": target.get("name") or target_id,
                            "preset": target.get("preset") or "",
                            "kind_label": LAYOUT_PLACEMENT_LABELS.get(target.get("preset"), target.get("preset") or "配置物"),
                            "path": _layout_placement_path(field, layout, target_space.get("id"), target),
                            "href": _layout_placement_url(field_id, target_space.get("id"), target_id),
                        }
                    )
                preset = placement.get("preset") or ""
                relation_label = (
                    "潅水対象" if preset == "watering_device" else "計測対象" if preset == "sensor" else "監視対象" if preset == "camera" else "関連対象"
                )
                resource_type = binding.get("resource_type") or "device"
                placement_path = _without_trailing_internal_id(
                    _layout_placement_path(field, layout, space.get("id"), placement),
                    device_id,
                )
                field_assignments.append(
                    {
                        "field_id": field_id,
                        "field_name": field.get("name") or field_id,
                        "field_href": f"/fields/{quote(str(field_id), safe='')}",
                        "layout_href": f"/fields/{quote(str(field_id), safe='')}/layout",
                        "space_id": space.get("id") or "",
                        "space_name": space.get("name") or "圃場全体",
                        "placement_id": placement.get("id") or "",
                        "placement_name": _without_trailing_internal_id(
                            placement.get("name") or placement.get("id") or "配置物",
                            device_id,
                        ),
                        "placement_kind": LAYOUT_PLACEMENT_LABELS.get(preset, preset or "配置物"),
                        "path": placement_path,
                        "href": _layout_placement_url(field_id, space.get("id"), placement.get("id")),
                        "resource_name": _layout_resource_name(record, resource_type, binding.get("resource_id") or ""),
                        "relation_label": relation_label,
                        "targets": target_items,
                        "field_level": False,
                    }
                )

        if field_assignments:
            assignments.extend(field_assignments)
            continue
        if device_id in set(field.get("device_ids") or []) | set(field.get("camera_device_ids") or []):
            field_name = field.get("name") or field_id
            field_href = f"/fields/{quote(str(field_id), safe='')}"
            assignments.append(
                {
                    "field_id": field_id,
                    "field_name": field_name,
                    "field_href": field_href,
                    "layout_href": f"{field_href}/layout",
                    "space_id": layout.get("root_space_id") or "",
                    "space_name": "圃場全体",
                    "placement_id": "",
                    "placement_name": "圃場全体",
                    "placement_kind": "圃場",
                    "path": f"{field_name} / 圃場全体",
                    "href": field_href,
                    "resource_name": "デバイス",
                    "relation_label": "関連対象",
                    "targets": [],
                    "field_level": True,
                }
            )

    assignments.sort(key=lambda item: (item["field_name"], item["path"], item["placement_id"]))
    primary = assignments[0] if assignments else {}
    return {
        "assigned": bool(assignments),
        "assignments": assignments,
        "primary_path": primary.get("path") or "",
        "primary_href": primary.get("href") or "",
    }


def _layout_placement_path(field, layout, space_id, placement):
    spaces = {space.get("id"): space for space in layout.get("spaces") or [] if space.get("id")}
    parent_by_child = {
        child_space_id: (space.get("id"), parent)
        for space in spaces.values()
        for parent in space.get("placements") or []
        if (child_space_id := parent.get("child_space_id"))
    }
    ancestor_names = []
    current_space_id = space_id
    visited = set()
    while current_space_id and current_space_id != layout.get("root_space_id") and current_space_id not in visited:
        visited.add(current_space_id)
        parent_location = parent_by_child.get(current_space_id)
        if parent_location is None:
            break
        current_space_id, parent = parent_location
        ancestor_names.append(parent.get("name") or parent.get("id") or "空間")
    path_parts = [field.get("name") or field.get("id") or "圃場", *reversed(ancestor_names)]
    placement_name = placement.get("name") or placement.get("id") or "配置物"
    if not path_parts or path_parts[-1] != placement_name:
        path_parts.append(placement_name)
    return " / ".join(path_parts)


def _without_trailing_internal_id(value, identifier):
    text = str(value or "")
    suffix = f" / {identifier}"
    return text[: -len(suffix)] if identifier and text.endswith(suffix) else text


def _layout_placement_url(field_id, space_id, placement_id):
    query = urlencode({"space": space_id or "", "placement": placement_id or ""})
    return f"/fields/{quote(str(field_id), safe='')}/layout?{query}"


def _build_device_operational_metrics(record, payload, config, now, watering):
    device_kind = record.get("device_kind") or payload.get("device_kind") or ""
    definition = get_device_definition(device_kind)
    definition_metrics = definition.get("status", {}).get("metrics") or definition.get("sensor_slots") or []
    if device_kind in {"WTR", "WRS"}:
        soil_moisture = _first_numeric_value(payload, ("soil_moisture_percent", "last_soil_moisture"))
        threshold = payload.get("threshold") if payload.get("threshold") is not None else config.get("moisture_threshold")
        next_watering = _next_watering_schedule(config, now)
        moisture_class, moisture_hint = _moisture_threshold_guidance(soil_moisture, threshold)
        metrics = [
            {
                "label": "次の潅水",
                "value": next_watering["label"],
                "class": "priority",
                "hint": next_watering["hint"],
                "settings_anchor": "watering-schedules",
            },
            {
                "label": "土壌水分しきい値",
                "value": _format_percent(threshold),
                "class": "",
                "hint": "この値以下で潅水を判断",
                "settings_anchor": "watering-rules",
            },
            {
                "label": "現在の土壌水分",
                "value": _format_percent(soil_moisture),
                "class": moisture_class,
                "hint": moisture_hint,
                "history_anchor": "soil-moisture-chart",
            },
            {
                "label": "現在の潅水状態",
                "value": watering["label"],
                "class": watering["class"],
                "hint": "最後に受信した状態から判断",
                "history_anchor": "watering-trend-chart",
            },
        ]
        if device_kind == "WRS":
            metrics.extend(_definition_operational_metrics(definition_metrics, payload, config, skip_ids={"soil_moisture"}))
        return metrics

    metrics = _definition_operational_metrics(definition_metrics, payload, config)
    scheduled_operation = _build_scheduled_operation_state(definition, config)
    if scheduled_operation:
        metrics.insert(
            0,
            {
                "label": scheduled_operation["label"],
                "value": scheduled_operation["value"],
                "class": scheduled_operation["class"],
                "hint": scheduled_operation["hint"],
                "settings_anchor": scheduled_operation["settings_anchor"],
            },
        )
    if not metrics:
        detected_metric_specs = (
            ("気温", ("air_temperature_c",), "℃", 1, "air-temperature-chart"),
            ("湿度", ("air_humidity_percent",), "%", 1, "air-humidity-chart"),
            ("土壌水分", ("soil_moisture_percent", "last_soil_moisture"), "%", 1, "soil-moisture-chart"),
            ("地温", ("soil_temperature_c",), "℃", 1, "soil-temperature-chart"),
            ("土壌EC", ("soil_ec_us_cm",), "uS/cm", 0, "soil-ec-chart"),
            ("土壌pH", ("soil_ph",), "", 1, "soil-ph-chart"),
            ("光合成に使える光", ("par_umol_m2_s",), "umol/m2/s", 0, "par-chart"),
        )
        for label, aliases, unit, digits, history_anchor in detected_metric_specs:
            value = _first_numeric_value(payload, aliases)
            if value is not None:
                metrics.append(
                    {
                        "label": label,
                        "value": _format_measurement_value(value, unit, digits),
                        "class": "",
                        "hint": "直近の計測値",
                        "history_anchor": history_anchor,
                    }
                )

    if metrics:
        return metrics
    return [
        {
            "label": "Hub登録",
            "value": _device_state_label(record.get("state")),
            "class": _device_state_class(record.get("state")),
            "hint": "機器の登録状態",
        },
        {
            "label": "最終通信",
            "value": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
            "class": "",
            "hint": _format_datetime(record.get("last_seen_at") or record.get("last_status_at")),
        },
    ]


def _definition_operational_metrics(metric_specs, payload, config, *, skip_ids=None):
    metrics = []
    skip_ids = skip_ids or set()
    for spec in metric_specs:
        if not isinstance(spec, dict) or spec.get("id") in skip_ids:
            continue
        value = _first_numeric_value(payload, spec.get("status_keys") or [])
        enabled_path = spec.get("enabled_path")
        enabled = value_at_path(config, enabled_path) if enabled_path else True
        if value is None and enabled is False:
            display_value, hint, css_class = "未接続", "設定で使用していません", "muted"
        elif value is None:
            display_value, hint, css_class = "未取得", "機器は対応しています。次回の計測を待っています", "muted"
        else:
            display_value = _format_measurement_value(value, spec.get("unit") or "", int(spec.get("digits") or 0))
            hint, css_class = "直近の計測値", ""
        chart = spec.get("chart") or {}
        metrics.append(
            {
                "label": spec.get("label") or spec.get("id") or "計測値",
                "value": display_value,
                "class": css_class,
                "hint": hint,
                "history_anchor": f"{str(chart.get('kind') or spec.get('id')).replace('_', '-')}-chart",
                "availability": "connected" if value is not None else "disconnected" if enabled is False else "waiting",
            }
        )
    return metrics


def _next_watering_schedule(config, now):
    config = config if isinstance(config, dict) else {}
    offset_seconds = config.get("timezone_offset_sec")
    if not isinstance(offset_seconds, int) or not -43200 <= offset_seconds <= 50400:
        offset_seconds = 0
    device_timezone = timezone(timedelta(seconds=offset_seconds))
    local_now = now.astimezone(device_timezone)
    candidates = []
    for schedule in config.get("schedules") or []:
        if not isinstance(schedule, dict):
            continue
        hour = schedule.get("hour")
        minute = schedule.get("minute")
        if not isinstance(hour, int) or not isinstance(minute, int) or not 0 <= hour <= 23 or not 0 <= minute <= 59:
            continue
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        candidates.append((candidate, schedule))
    if not candidates:
        return {"label": "予約なし", "hint": "動作設定で潅水予約を追加できます"}

    candidate, schedule = min(candidates, key=lambda item: item[0])
    days_ahead = (candidate.date() - local_now.date()).days
    date_label = "今日" if days_ahead == 0 else "明日" if days_ahead == 1 else f"{candidate.month}月{candidate.day}日"
    hint_parts = [
        _format_channel_mask_for_config(schedule.get("channel_mask"), config),
        _format_duration(schedule.get("duration_sec")),
    ]
    return {
        "label": f"{date_label} {candidate:%H:%M}",
        "hint": " / ".join(part for part in hint_parts if part),
    }


def _moisture_threshold_guidance(soil_moisture, threshold):
    if not isinstance(soil_moisture, int | float) or isinstance(soil_moisture, bool):
        return "muted", "現在値を取得できていません"
    if not isinstance(threshold, int | float) or isinstance(threshold, bool):
        return "muted", "しきい値が設定されていません"
    difference = float(soil_moisture) - float(threshold)
    if difference < 0:
        return "warn", f"しきい値を {abs(difference):g} ポイント下回っています"
    if difference == 0:
        return "warn", "しきい値に達しています"
    return "good", f"しきい値まで {difference:g} ポイント"


def _first_numeric_value(payload, aliases):
    for alias in aliases:
        value = payload.get(alias)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return value
    return None


def _format_measurement_value(value, unit, digits):
    if value is None:
        return "未取得"
    formatted = f"{float(value):.{digits}f}"
    if digits == 0:
        formatted = str(int(round(float(value))))
    return f"{formatted} {unit}".strip()


def _build_rs485_sensor_groups(payload, device_kind):
    devices = payload.get("rs485_devices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        return []

    groups = []
    for position, device in enumerate(devices):
        if not isinstance(device, dict):
            continue
        state_label, state_class = _rs485_sensor_state(device)
        measurements = []
        if device.get("enabled") is not False and device.get("ok") is not False:
            for spec in _RS485_SENSOR_METRIC_SPECS:
                if not metric_supported_for_device_kind(spec["metric"], device_kind):
                    continue
                value = device.get(spec["device_value_key"])
                if not isinstance(value, int | float) or isinstance(value, bool):
                    continue
                measurements.append(
                    {
                        "label": spec["label"],
                        "value": _format_measurement_value(value, spec["unit"], spec["digits"]),
                        "history_anchor": f"{spec['chart_kind'].replace('_', '-')}-chart",
                    }
                )
        groups.append(
            {
                "name": _rs485_sensor_name(device, position),
                "location": str(device.get("location") or "").strip() or "設置場所未設定",
                "state_label": state_label,
                "state_class": state_class,
                "measurements": measurements,
            }
        )
    return groups


def _rs485_sensor_state(device):
    if device.get("enabled") is False:
        return "停止中", "muted"
    if device.get("attempted") is False:
        return "次回計測待ち", "muted"
    if device.get("bus_ready") is False or device.get("ok") is False:
        return "読取エラー", "danger"
    if device.get("ok") is True:
        return "正常", "good"
    return "状態未取得", "muted"


def _rs485_sensor_name(device, position):
    name = str(device.get("name") or "").strip()
    if name:
        return name
    sensor_type = str(device.get("type") or "").strip().lower()
    type_label = "土壌センサー" if sensor_type == "soil" else "光センサー" if sensor_type == "par" else "RS485センサー"
    return f"{type_label}{position + 1}"


def _rs485_sensor_series_label(device, position):
    name = _rs485_sensor_name(device, position)
    location = str(device.get("location") or "").strip()
    return f"{name}（{location}）" if location else name


def _rs485_sensor_identity(device, position):
    index = device.get("index")
    if isinstance(index, int | str) and not isinstance(index, bool):
        return "index", str(index)
    slave_id = device.get("modbus_slave_id")
    if isinstance(slave_id, int | str) and not isinstance(slave_id, bool):
        return "bus", str(device.get("type") or ""), str(device.get("baud") or ""), str(slave_id)
    return "position", str(position)


def _rs485_metric_series(statuses, device_value_key):
    series_by_sensor = {}
    for entry in statuses or []:
        payload = entry.get("payload") if isinstance(entry, dict) else None
        received_at = _to_local_plot_time(entry.get("received_at")) if isinstance(entry, dict) else None
        devices = payload.get("rs485_devices") if isinstance(payload, dict) else None
        if received_at is None or not isinstance(devices, list):
            continue
        for position, device in enumerate(devices):
            if not isinstance(device, dict) or device.get("enabled") is False or device.get("ok") is False:
                continue
            value = device.get(device_value_key)
            if not isinstance(value, int | float) or isinstance(value, bool):
                continue
            identity = _rs485_sensor_identity(device, position)
            series = series_by_sensor.setdefault(identity, {"name": "", "points": []})
            series["name"] = _rs485_sensor_series_label(device, position)
            series["points"].append({"time": received_at, "value": value})
    return list(series_by_sensor.values())


def _build_device_monitoring_charts(device_kind, statuses, config=None):
    definition = get_device_definition(device_kind)
    definition_metrics = definition.get("status", {}).get("metrics") or []
    if definition_metrics:
        specs = []
        device_category = str((definition.get("device") or {}).get("category") or "")
        if device_category in {"watering", "fertigation"}:
            specs.append(("watering", "潅水推移", "潅水に関する時系列データはまだありません。"))
        payloads = [entry.get("payload") for entry in statuses or [] if isinstance(entry, dict) and isinstance(entry.get("payload"), dict)]
        for metric in definition_metrics:
            if not any(_first_numeric_value(payload, metric.get("status_keys") or []) is not None for payload in payloads):
                continue
            chart = metric.get("chart") or {}
            kind = chart.get("kind") or metric.get("id")
            specs.append((kind, chart.get("title") or f"{metric.get('label')}推移", chart.get("empty_message") or "時系列データはまだありません。"))
        seen = set()
        specs = tuple(item for item in specs if not (item[0] in seen or seen.add(item[0])))
    else:
        specs = None
    chart_specs = {
        "WTR": (
            ("watering", "潅水推移", "潅水に関する時系列データはまだありません。"),
            ("soil_moisture", "土壌水分推移", "土壌水分の時系列データはまだありません。"),
        ),
        "WRS": (
            ("watering", "潅水推移", "潅水に関する時系列データはまだありません。"),
            ("soil_moisture", "土壌水分推移", "土壌水分の時系列データはまだありません。"),
            ("soil_ec", "土壌EC推移", "土壌ECの時系列データはまだありません。"),
            ("soil_ph", "土壌pH推移", "土壌pHの時系列データはまだありません。"),
            ("par", "PAR推移", "PARの時系列データはまだありません。"),
        ),
        "ENV": (
            ("air_temperature", "気温推移", "気温の時系列データはまだありません。"),
            ("air_humidity", "湿度推移", "湿度の時系列データはまだありません。"),
            ("par", "PAR推移", "PARの時系列データはまだありません。"),
        ),
        "SOI": (
            ("soil_moisture", "土壌水分推移", "土壌水分の時系列データはまだありません。"),
            ("soil_temperature", "地温推移", "地温の時系列データはまだありません。"),
            ("soil_ec", "土壌EC推移", "土壌ECの時系列データはまだありません。"),
            ("soil_ph", "土壌pH推移", "土壌pHの時系列データはまだありません。"),
        ),
        "PAR": (("par", "PAR推移", "PARの時系列データはまだありません。"),),
    }
    specs = specs or chart_specs.get(device_kind)
    if specs is None:
        specs = tuple(_detected_device_chart_specs(statuses))
    dom_ids = {
        "watering": "watering-trend-chart",
        "soil_moisture": "soil-moisture-chart",
        "air_temperature": "air-temperature-chart",
        "air_humidity": "air-humidity-chart",
        "soil_temperature": "soil-temperature-chart",
        "soil_ec": "soil-ec-chart",
        "soil_ph": "soil-ph-chart",
        "par": "par-chart",
    }
    return [
        {
            "kind": kind,
            "title": title,
            "empty_message": empty_message,
            "dom_id": dom_ids.get(kind, f"{str(kind).replace('_', '-')}-chart"),
        }
        for kind, title, empty_message in specs
    ]


def _detected_device_chart_specs(statuses):
    payloads = [entry.get("payload") for entry in statuses or [] if isinstance(entry, dict) and isinstance(entry.get("payload"), dict)]
    candidates = (
        ("air_temperature", "気温推移", "気温の時系列データはまだありません。", ("air_temperature_c",)),
        ("air_humidity", "湿度推移", "湿度の時系列データはまだありません。", ("air_humidity_percent",)),
        ("soil_moisture", "土壌水分推移", "土壌水分の時系列データはまだありません。", ("soil_moisture_percent", "last_soil_moisture")),
        ("soil_temperature", "地温推移", "地温の時系列データはまだありません。", ("soil_temperature_c",)),
        ("soil_ec", "土壌EC推移", "土壌ECの時系列データはまだありません。", ("soil_ec_us_cm",)),
        ("soil_ph", "土壌pH推移", "土壌pHの時系列データはまだありません。", ("soil_ph",)),
        ("par", "PAR推移", "PARの時系列データはまだありません。", ("par_umol_m2_s",)),
    )
    for kind, title, empty_message, aliases in candidates:
        if any(_first_numeric_value(payload, aliases) is not None for payload in payloads):
            yield kind, title, empty_message


def _latest_status_payload(record):
    payload = record.get("last_status")
    if isinstance(payload, dict):
        return payload
    history = record.get("status_history") or []
    for entry in reversed(history):
        entry_payload = entry.get("payload") if isinstance(entry, dict) else None
        if isinstance(entry_payload, dict):
            return entry_payload
    return {}


def _build_watering_history(statuses, limit=24, *, config=None):
    history = []
    for entry in reversed(statuses or []):
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict) or not _has_watering_information(payload):
            continue
        watering = _watering_state(payload)
        duration_sec = _watering_duration_sec(payload)
        history.append(
            {
                "time": _format_datetime(entry.get("received_at")),
                "label": watering["label"],
                "class": watering["class"],
                "duration": _format_duration(duration_sec),
                "channel": _watering_channel(payload, config),
                "soil": _format_percent(
                    payload.get("soil_moisture_percent") if payload.get("soil_moisture_percent") is not None else payload.get("last_soil_moisture")
                ),
                "threshold": _format_percent(payload.get("threshold")),
                "reason": payload.get("batch_skip_reason") or payload.get("watering_stop_reason") or "",
                "catch_up": payload.get("batch_catch_up") is True,
            }
        )
        if len(history) >= limit:
            break
    return history


def _build_watering_trend_chart(statuses, include_plotlyjs=False, *, deferred=False):
    points = _watering_trend_points(statuses)
    if not points:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[point["time"] for point in points],
            y=[point["duration_minutes"] for point in points],
            name="灌水時間",
            marker_color="#2563eb",
            customdata=[[point["state"], point["duration_label"], point["channel"], point["soil"], point["threshold"]] for point in points],
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M}<br>"
                "状態: %{customdata[0]}<br>"
                "実行時間: %{customdata[1]}<br>"
                "対象: %{customdata[2]}<br>"
                "土壌水分: %{customdata[3]}<br>"
                "しきい値: %{customdata[4]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="灌水推移",
        height=360,
        margin={"l": 56, "r": 24, "t": 48, "b": 48},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        yaxis_title="灌水時間（分）",
        bargap=0.28,
        showlegend=False,
    )
    _configure_time_axis(fig, points)
    fig.update_yaxes(rangemode="tozero")
    return _plotly_div(fig, "watering-trend-chart", include_plotlyjs=include_plotlyjs, deferred=deferred)


def _build_soil_moisture_chart(statuses, include_plotlyjs=False):
    sensor_series = _rs485_metric_series(statuses, "moisture_percent")
    points = [point for series in sensor_series for point in series["points"]] if sensor_series else _soil_moisture_points(statuses)
    if not points:
        return None

    fig = go.Figure()
    if sensor_series:
        for index, series in enumerate(sensor_series):
            series_points = series["points"]
            fig.add_trace(
                go.Scatter(
                    x=[point["time"] for point in series_points],
                    y=[point["value"] for point in series_points],
                    mode="lines+markers",
                    name=series["name"],
                    line={"color": _RS485_TRACE_COLORS[index % len(_RS485_TRACE_COLORS)], "width": 3},
                    marker={"size": 7},
                    hovertemplate="%{fullData.name}<br>%{x|%Y-%m-%d %H:%M}<br>土壌水分: %{y}%<extra></extra>",
                )
            )
    else:
        fig.add_trace(
            go.Scatter(
                x=[point["time"] for point in points],
                y=[point["soil_moisture"] for point in points],
                mode="lines+markers",
                name="土壌水分",
                line={"color": "#047857", "width": 3},
                marker={"size": 7},
                customdata=[[point["state"], point["threshold_label"]] for point in points],
                hovertemplate=("%{x|%Y-%m-%d %H:%M}<br>土壌水分: %{y}%<br>状態: %{customdata[0]}<br>しきい値: %{customdata[1]}<extra></extra>"),
            )
        )
    threshold_points = [point for point in _soil_moisture_points(statuses) if point["threshold"] is not None]
    if threshold_points:
        fig.add_trace(
            go.Scatter(
                x=[point["time"] for point in threshold_points],
                y=[point["threshold"] for point in threshold_points],
                mode="lines",
                name="灌水しきい値",
                line={"color": "#f59e0b", "width": 2, "dash": "dash"},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>しきい値: %{y}%<extra></extra>",
            )
        )
    fig.update_layout(
        title="土壌水分推移",
        height=360,
        margin={"l": 56, "r": 24, "t": 48, "b": 48},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        yaxis_title="土壌水分（%）",
        legend={"orientation": "h", "y": -0.24},
    )
    _configure_time_axis(fig, points)
    fig.update_yaxes(range=[0, 100])
    return _plotly_div(fig, "soil-moisture-chart", include_plotlyjs=include_plotlyjs)


def _build_metric_trend_chart(
    statuses,
    *,
    aliases,
    title,
    unit,
    color,
    div_id,
    include_plotlyjs=False,
    y_range=None,
    rs485_value_key=None,
):
    sensor_series = _rs485_metric_series(statuses, rs485_value_key) if rs485_value_key else []
    points = [point for series in sensor_series for point in series["points"]] if sensor_series else _metric_trend_points(statuses, aliases)
    if not points:
        return None

    unit_suffix = f" {unit}" if unit else ""
    fig = go.Figure()
    if sensor_series:
        for index, series in enumerate(sensor_series):
            series_points = series["points"]
            fig.add_trace(
                go.Scatter(
                    x=[point["time"] for point in series_points],
                    y=[point["value"] for point in series_points],
                    mode="lines+markers",
                    name=series["name"],
                    line={"color": _RS485_TRACE_COLORS[index % len(_RS485_TRACE_COLORS)], "width": 3},
                    marker={"size": 7},
                    hovertemplate=f"%{{fullData.name}}<br>%{{x|%Y-%m-%d %H:%M}}<br>{title}: %{{y}}{unit_suffix}<extra></extra>",
                )
            )
    else:
        fig.add_trace(
            go.Scatter(
                x=[point["time"] for point in points],
                y=[point["value"] for point in points],
                mode="lines+markers",
                name=title,
                line={"color": color, "width": 3},
                marker={"size": 7},
                hovertemplate=f"%{{x|%Y-%m-%d %H:%M}}<br>{title}: %{{y}}{unit_suffix}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        height=360,
        margin={"l": 64, "r": 24, "t": 48, "b": 48},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        yaxis_title=f"{title}（{unit}）" if unit else title,
        showlegend=bool(sensor_series),
        legend={"orientation": "h", "y": -0.24} if sensor_series else None,
    )
    _configure_time_axis(fig, points)
    if y_range:
        fig.update_yaxes(range=list(y_range))
    return _plotly_div(fig, div_id, include_plotlyjs=include_plotlyjs)


def _metric_trend_points(statuses, aliases):
    points = []
    for entry in statuses or []:
        payload = entry.get("payload") if isinstance(entry, dict) else None
        received_at = _to_local_plot_time(entry.get("received_at")) if isinstance(entry, dict) else None
        if received_at is None or not isinstance(payload, dict):
            continue
        value = _first_numeric_value(payload, aliases)
        if value is None:
            continue
        points.append({"time": received_at, "value": value})
    return points


def _watering_trend_points(statuses):
    points = []
    for entry in statuses or []:
        payload = entry.get("payload") if isinstance(entry, dict) else None
        received_at = _to_local_plot_time(entry.get("received_at")) if isinstance(entry, dict) else None
        if received_at is None or not isinstance(payload, dict) or not _has_watering_information(payload):
            continue
        duration_sec = _watering_duration_sec(payload)
        duration_minutes = round(float(duration_sec) / 60, 2) if isinstance(duration_sec, int | float) else 0
        watering = _watering_state(payload)
        points.append(
            {
                "time": received_at,
                "duration_minutes": duration_minutes,
                "duration_label": _format_duration(duration_sec),
                "state": watering["label"],
                "channel": _watering_channel(payload),
                "soil": _format_percent(
                    payload.get("soil_moisture_percent") if payload.get("soil_moisture_percent") is not None else payload.get("last_soil_moisture")
                ),
                "threshold": _format_percent(payload.get("threshold")),
            }
        )
    return points


def _soil_moisture_points(statuses):
    points = []
    for entry in statuses or []:
        payload = entry.get("payload") if isinstance(entry, dict) else None
        received_at = _to_local_plot_time(entry.get("received_at")) if isinstance(entry, dict) else None
        if received_at is None or not isinstance(payload, dict):
            continue
        soil_moisture = _first_numeric_value(payload, ("soil_moisture_percent", "last_soil_moisture"))
        if not isinstance(soil_moisture, int | float):
            continue
        threshold = payload.get("threshold")
        points.append(
            {
                "time": received_at,
                "soil_moisture": soil_moisture,
                "threshold": threshold if isinstance(threshold, int | float) else None,
                "threshold_label": _format_percent(threshold),
                "state": _watering_state(payload)["label"],
            }
        )
    return points


def _configure_time_axis(fig, points):
    max_time = max((point["time"] for point in points), default=None)
    if max_time is None:
        return
    fig.update_xaxes(
        range=[max_time - timedelta(days=3), max_time],
        rangeslider={"visible": True, "thickness": 0.08},
        showgrid=True,
    )


def _plotly_div(fig, div_id, include_plotlyjs=False, *, deferred=False):
    config = {"displaylogo": False, "responsive": True}
    if deferred:
        figure = fig.to_plotly_json()
        payload = json.dumps(
            {"data": figure["data"], "layout": figure["layout"], "config": config},
            cls=plotly.utils.PlotlyJSONEncoder,
            ensure_ascii=True,
            separators=(",", ":"),
        ).replace("</", "<\\/")
        safe_id = escape(div_id, quote=True)
        return (
            f'<div id="{safe_id}" class="plotly-deferred" data-plotly-deferred="true">'
            '<p class="plotly-deferred-status">グラフを読み込んでいます</p></div>'
            f'<script type="application/json" data-plotly-chart="{safe_id}">{payload}</script>'
        )
    return to_html(
        fig,
        full_html=False,
        include_plotlyjs=include_plotlyjs,
        div_id=div_id,
        config=config,
    )


def _build_wake_history(statuses, limit=8):
    history = []
    for entry in reversed(statuses or []):
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        history.append(
            {
                "time": _format_datetime(entry.get("received_at")),
                "seq": payload.get("seq", "-"),
                "next_wake": _format_next_wake(entry.get("received_at"), payload.get("next_sleep_sec")),
                "config_received": _format_bool(payload.get("config_received")),
                "time_synced": _format_bool(payload.get("time_synced")),
                "rssi": payload.get("rssi", "-"),
            }
        )
        if len(history) >= limit:
            break
    return history


def _build_ota_history(ota_statuses, limit=8):
    history = []
    for entry in reversed(ota_statuses or []):
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        history.append(
            {
                "time": _format_datetime(entry.get("received_at")),
                "state": _ota_state_label(payload.get("state")),
                "from_version": payload.get("from_version") or "-",
                "to_version": payload.get("to_version") or "-",
                "error": payload.get("error") or "",
            }
        )
        if len(history) >= limit:
            break
    return history


def _has_watering_information(payload):
    if any(
        key in payload
        for key in (
            "watering_due",
            "watering_started",
            "watering_duration_sec",
            "channel_mask",
            "last_soil_moisture",
            "threshold",
        )
    ):
        return True
    if any(payload.get(key) is True for key in ("batch_due", "batch_started", "batch_completed", "batch_skipped")):
        return True
    elapsed_ms = payload.get("fgt_batch_elapsed_ms")
    return isinstance(elapsed_ms, int | float) and not isinstance(elapsed_ms, bool) and elapsed_ms > 0


def _watering_state(payload):
    if not payload:
        return {"label": "未取得", "class": "muted"}
    if payload.get("batch_completed") is True:
        return {"label": "潅水完了", "class": "good"}
    if payload.get("batch_skipped") is True:
        return {"label": "実行せず", "class": "warn"}
    if payload.get("batch_started") is True:
        return {"label": "潅水開始", "class": "good"}
    if payload.get("batch_due") is True:
        return {"label": "潅水予定", "class": "warn"}
    if payload.get("watering_started") is True:
        return {"label": "灌水中", "class": "good"}
    if payload.get("watering_due") is True:
        return {"label": "灌水予定", "class": "warn"}
    if "watering_started" in payload or "watering_due" in payload or "last_soil_moisture" in payload or "batch_started" in payload or "batch_due" in payload:
        return {"label": "待機中", "class": "ok"}
    return {"label": "未取得", "class": "muted"}


def _watering_duration_sec(payload):
    duration_sec = payload.get("watering_duration_sec")
    if isinstance(duration_sec, int | float) and not isinstance(duration_sec, bool):
        return duration_sec
    elapsed_ms = payload.get("fgt_batch_elapsed_ms")
    if isinstance(elapsed_ms, int | float) and not isinstance(elapsed_ms, bool):
        return float(elapsed_ms) / 1000
    return None


def _watering_channel(payload, config=None):
    timed_output = str(payload.get("fgt_timed_output") or "").strip()
    if timed_output and timed_output != "none":
        return _fgt_output_label(timed_output)
    timed_outputs = ((config or {}).get("fgt") or {}).get("timed_outputs") or {}
    enabled_outputs = [
        output_id
        for output_id in ("water_inlet", "nutrient_a", "nutrient_b", "mixer", "irrigation")
        if isinstance(timed_outputs.get(output_id), dict)
        and timed_outputs[output_id].get("on_sec", 0) > 0
        and timed_outputs[output_id].get("repeat_count", 0) > 0
    ]
    if payload.get("fgt_operation_mode") == "timed_outputs" and len(enabled_outputs) == 1:
        return _fgt_output_label(enabled_outputs[0])
    return _format_channel_mask(payload.get("channel_mask"))


def _fgt_output_label(output_id):
    return {
        "water_inlet": "給水ポンプ",
        "nutrient_a": "A液ポンプ",
        "nutrient_b": "B液ポンプ",
        "mixer": "攪拌ポンプ",
        "irrigation": "潅水ポンプ",
    }.get(output_id, output_id)


def _device_kind_label(device_kind):
    legacy_labels = {"PAR": "日射・PARセンサー", "CAM": "カメラ"}
    return legacy_labels.get(device_kind) or definition_device_kind_label(device_kind)


def _device_state_label(state):
    return {
        "active": "利用中",
        "pending": "承認待ち",
        "disabled": "停止中",
        "retired": "廃止済み",
    }.get(state, "状態未取得")


def _device_state_class(state):
    return {
        "active": "good",
        "pending": "warn",
        "disabled": "muted",
        "retired": "danger",
    }.get(state, "muted")


def _ota_state_label(state):
    return {
        "started": "更新中",
        "downloaded": "取得完了",
        "applying": "適用中",
        "confirmed": "更新完了",
        "failed": "更新失敗",
    }.get(state, "更新なし")


def _ota_state_class(state):
    return {
        "started": "warn",
        "downloaded": "warn",
        "applying": "warn",
        "confirmed": "good",
        "failed": "danger",
    }.get(state, "muted")


def _build_scheduled_operation_state(definition, config):
    spec = definition.get("ui", {}).get("scheduled_operation") if isinstance(definition, dict) else None
    if not isinstance(spec, dict) or not spec.get("enabled_path"):
        return None
    device_kind = definition.get("device", {}).get("kind")
    config = project_runtime_config(device_kind, config)
    fixed_values = definition.get("runtime_config", {}).get("fixed_values") or {}

    schedules = value_at_path(config, spec.get("schedules_path") or "schedules")
    schedules = schedules if isinstance(schedules, list) else []
    enabled_schedules = [schedule for schedule in schedules if isinstance(schedule, dict) and schedule.get("enabled") is not False]
    operation_enabled = value_at_path(config, spec["enabled_path"]) is True
    program_required_when_path = spec.get("program_required_when_path")
    program_requirements_apply = value_at_path(config, program_required_when_path) is True if program_required_when_path else True
    output_programs = value_at_path(config, spec.get("program_outputs_path"))
    output_programs = output_programs if isinstance(output_programs, dict) else {}
    missing_output_ids = []
    for output_id in (spec.get("required_output_ids") or []) if program_requirements_apply else []:
        output = output_programs.get(output_id)
        if (
            not isinstance(output, dict)
            or not isinstance(output.get("on_sec"), int)
            or output.get("on_sec", 0) <= 0
            or not isinstance(output.get("repeat_count"), int)
            or output.get("repeat_count", 0) <= 0
        ):
            missing_output_ids.append(output_id)

    warnings = []
    if enabled_schedules and not operation_enabled:
        warnings.append(spec.get("disabled_warning") or "予約運転が停止中のため、予約は実行されません。")
    if enabled_schedules and missing_output_ids:
        warnings.append(spec.get("missing_output_warning") or "必要な出力時間が設定されていないため、予約は実行されません。")

    if not enabled_schedules:
        value = spec.get("no_schedule_label") or "予約なし"
        css_class = "muted"
        hint = spec.get("no_schedule_hint") or "有効な予約がありません"
    elif not operation_enabled:
        value = spec.get("disabled_label") or "停止中"
        css_class = "warn"
        hint = " ".join(warnings)
    elif missing_output_ids:
        value = spec.get("incomplete_label") or "設定不足"
        css_class = "warn"
        hint = " ".join(warnings)
    else:
        value = spec.get("enabled_label") or "運転中"
        css_class = "good"
        hint = spec.get("ready_hint") or "有効な予約を設定時刻に実行します"

    return {
        "label": spec.get("label") or "予約運転",
        "value": value,
        "class": css_class,
        "hint": hint,
        "warning": " ".join(warnings),
        "warnings": warnings,
        "enabled": operation_enabled,
        "ready": bool(enabled_schedules) and operation_enabled and not missing_output_ids,
        "active_schedule_count": len(enabled_schedules),
        "missing_output_ids": missing_output_ids,
        "enable_control_available": spec["enabled_path"] not in fixed_values,
        "settings_anchor": spec.get("settings_anchor") or "watering-schedules",
        "spec": spec,
    }


def _format_config_summary(config):
    if not isinstance(config, dict) or not config:
        return {"threshold": "未設定", "force": "未設定", "debug_log": "未設定", "ota_interval": "未設定", "schedule_count": "0件"}
    return {
        "threshold": _format_percent(config.get("moisture_threshold")),
        "force": _format_bool(config.get("force_watering")),
        "debug_log": _format_bool(config.get("debug_log_on_wake")),
        "ota_interval": _format_duration(config.get("ota_check_interval_sec")),
        "schedule_count": f"{len(config.get('schedules') or [])}件",
    }


def _format_schedules_for_ui(schedules, config=None, *, scheduled_operation=None):
    formatted = []
    for schedule in schedules:
        if not isinstance(schedule, dict):
            continue
        hour = schedule.get("hour")
        minute = schedule.get("minute")
        duration_sec = schedule.get("duration_sec")
        if not isinstance(hour, int) or not isinstance(minute, int):
            continue
        formatted.append(
            {
                "time": f"{hour:02d}:{minute:02d}",
                "duration": _format_duration(duration_sec),
                "channel": _format_channel_mask_for_config(schedule.get("channel_mask"), config),
                "state_label": (
                    "利用しない"
                    if schedule.get("enabled") is False
                    else "実行予定"
                    if scheduled_operation and scheduled_operation["ready"]
                    else "実行されません"
                    if scheduled_operation
                    else ""
                ),
                "state_class": (
                    "muted"
                    if schedule.get("enabled") is False
                    else "good"
                    if scheduled_operation and scheduled_operation["ready"]
                    else "warn"
                    if scheduled_operation
                    else ""
                ),
            }
        )
    return formatted


def _format_channel_mask_for_config(channel_mask, config):
    labels_by_mask = _mosfet_switch_labels_by_mask(config)
    if labels_by_mask:
        labels = [name for bit, name in labels_by_mask.items() if isinstance(channel_mask, int) and channel_mask & bit]
        if labels:
            return "・".join(labels)
    return _format_channel_mask(channel_mask)


def _mosfet_switch_labels_by_mask(config):
    labels_by_mask = {}
    if not isinstance(config, dict):
        return labels_by_mask
    for switch in config.get("mosfet_switches") or []:
        if not isinstance(switch, dict) or switch.get("enabled") is False:
            continue
        channel_mask = switch.get("channel_mask")
        name = switch.get("name")
        if isinstance(channel_mask, int) and channel_mask > 0 and isinstance(name, str) and name.strip():
            labels_by_mask[channel_mask] = name.strip()
    return labels_by_mask


def _format_channel_mask(channel_mask):
    if not isinstance(channel_mask, int) or channel_mask <= 0:
        return "系統未取得"
    channels = [f"系統{i}" for i in range(1, 9) if channel_mask & (1 << (i - 1))]
    return "・".join(channels) if channels else "対応外の系統"


def _format_percent(value):
    if isinstance(value, int | float):
        return f"{value:g}%"
    return "未取得"


def _format_bool(value):
    if value is True:
        return "はい"
    if value is False:
        return "いいえ"
    return "未取得"


def _format_duration(seconds):
    if not isinstance(seconds, int | float):
        return "未取得"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}分{rest}秒" if rest else f"{minutes}分"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}時間{minutes}分" if minutes else f"{hours}時間"


def _format_next_wake(received_at, next_sleep_sec):
    if not isinstance(next_sleep_sec, int | float):
        return "未取得"
    received_at_dt = _parse_datetime(received_at)
    if received_at_dt is None:
        return f"{int(next_sleep_sec)}秒後"
    return _format_datetime((received_at_dt + timedelta(seconds=next_sleep_sec)).isoformat())


def _format_age(value, now=None):
    parsed = _parse_datetime(value)
    if parsed is None:
        return "未取得"
    now = now or datetime.now(UTC)
    seconds = max(0, int((now - parsed).total_seconds()))
    if seconds < 60:
        return f"{seconds}秒前"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分前"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}時間前"
    return f"{hours // 24}日前"


def _format_datetime(value):
    local_dt = _to_local_datetime(value)
    if local_dt is None:
        return "未取得"
    timezone_name = local_dt.tzname() or "local"
    return local_dt.strftime(f"%Y-%m-%d %H:%M {timezone_name}")


def _parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_truthy_request_arg(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _demo_mqtt_admin_page_data(selected_device_id=None):
    requested_device_id = selected_device_id
    now = datetime.now(UTC)

    def ago(minutes):
        return (now - timedelta(minutes=minutes)).isoformat()

    def status(minutes, seq, **payload):
        payload.setdefault("device_kind", "WTR")
        payload.setdefault("firmware_version", "1.0.0")
        payload.setdefault("config_received", True)
        payload.setdefault("time_synced", True)
        payload.setdefault("rssi", -62)
        payload["seq"] = seq
        return {"received_at": ago(minutes), "payload": payload}

    statuses_by_device = {
        "INADS-DEMO-WTR-001": [
            status(60 * 24 * 35, 112, watering_due=False, watering_started=False, last_soil_moisture=52, threshold=40, next_sleep_sec=21600, rssi=-63),
            status(
                60 * 24 * 21,
                113,
                watering_due=True,
                watering_started=True,
                watering_duration_sec=80,
                channel_mask=1,
                last_soil_moisture=32,
                threshold=40,
                next_sleep_sec=21600,
                rssi=-62,
            ),
            status(60 * 24 * 13, 114, watering_due=False, watering_started=False, last_soil_moisture=45, threshold=40, next_sleep_sec=21600, rssi=-61),
            status(
                60 * 24 * 6,
                115,
                watering_due=True,
                watering_started=True,
                watering_duration_sec=70,
                channel_mask=3,
                last_soil_moisture=36,
                threshold=40,
                next_sleep_sec=21600,
                rssi=-60,
            ),
            status(60 * 24 * 2, 116, watering_due=False, watering_started=False, last_soil_moisture=43, threshold=40, next_sleep_sec=21600, rssi=-59),
            status(180, 118, watering_due=False, watering_started=False, last_soil_moisture=47, threshold=40, next_sleep_sec=1800, rssi=-59),
            status(
                96,
                119,
                watering_due=True,
                watering_started=True,
                watering_duration_sec=90,
                channel_mask=1,
                last_soil_moisture=34,
                threshold=40,
                next_sleep_sec=900,
                rssi=-61,
            ),
            status(
                48,
                120,
                watering_due=False,
                watering_started=False,
                watering_duration_sec=0,
                channel_mask=1,
                last_soil_moisture=44,
                threshold=40,
                next_sleep_sec=1800,
                rssi=-60,
            ),
            status(
                12,
                121,
                watering_due=True,
                watering_started=True,
                watering_duration_sec=60,
                channel_mask=3,
                last_soil_moisture=38,
                threshold=40,
                next_sleep_sec=600,
                rssi=-58,
            ),
        ],
        "INADS-DEMO-WTR-002": [
            status(240, 71, watering_due=False, watering_started=False, last_soil_moisture=63, threshold=35, next_sleep_sec=3600, rssi=-67),
            status(
                78,
                72,
                watering_due=False,
                watering_started=False,
                watering_duration_sec=0,
                channel_mask=2,
                last_soil_moisture=58,
                threshold=35,
                next_sleep_sec=2400,
                rssi=-66,
            ),
        ],
        "INADS-DEMO-WTR-003": [
            status(
                780, 4, watering_due=False, watering_started=False, last_soil_moisture=29, threshold=38, next_sleep_sec=3600, rssi=-82, config_received=False
            ),
        ],
    }
    devices = {
        "INADS-DEMO-WTR-001": {
            "id": "INADS-DEMO-WTR-001",
            "name": "北ハウス 1号",
            "location": "北ハウス",
            "memo": "葉物エリア。朝夕の水やりを自動化しています。",
            "device_kind": "WTR",
            "state": "active",
            "config": {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 40,
                "force_watering": False,
                "mosfet_switches": [
                    {
                        "switch_id": "irr1",
                        "name": "高設ベッドA",
                        "enabled": True,
                        "role": "irrigation",
                        "terminal": "IRR1",
                        "channel_mask": 1,
                        "controlled_load": "点滴チューブ A",
                    },
                    {
                        "switch_id": "irr2",
                        "name": "高設ベッドB",
                        "enabled": True,
                        "role": "irrigation",
                        "terminal": "IRR2",
                        "channel_mask": 2,
                        "controlled_load": "点滴チューブ B",
                    },
                ],
                "schedules": [
                    {"hour": 6, "minute": 30, "duration_sec": 90, "channel_mask": 1},
                    {"hour": 17, "minute": 45, "duration_sec": 60, "channel_mask": 3},
                ],
            },
            "firmware_version": "1.0.0",
            "target_firmware_version": "1.1.0",
            "ota_state": "started",
            "ota_error": "",
        },
        "INADS-DEMO-WTR-002": {
            "id": "INADS-DEMO-WTR-002",
            "name": "南ハウス 2号",
            "location": "南ハウス",
            "memo": "土壌水分は十分。次の水やりまで待機しています。",
            "device_kind": "WTR",
            "state": "active",
            "config": {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 35,
                "force_watering": False,
                "mosfet_switches": [
                    {
                        "switch_id": "irr1",
                        "name": "南ハウス点滴A",
                        "enabled": True,
                        "role": "irrigation",
                        "terminal": "IRR1",
                        "channel_mask": 1,
                        "controlled_load": "点滴チューブ A",
                    },
                    {
                        "switch_id": "irr2",
                        "name": "南ハウス点滴B",
                        "enabled": True,
                        "role": "irrigation",
                        "terminal": "IRR2",
                        "channel_mask": 2,
                        "controlled_load": "点滴チューブ B",
                    },
                ],
                "schedules": [{"hour": 7, "minute": 0, "duration_sec": 75, "channel_mask": 2}],
            },
            "firmware_version": "1.0.0",
            "target_firmware_version": "",
            "ota_state": "",
            "ota_error": "",
        },
        "INADS-DEMO-WTR-003": {
            "id": "INADS-DEMO-WTR-003",
            "name": "西ハウス 予備機",
            "location": "西ハウス",
            "memo": "設置直後で承認待ちです。",
            "device_kind": "WTR",
            "state": "pending",
            "config": {
                "ntp_server": "pool.ntp.org",
                "timezone_offset_sec": 32400,
                "moisture_threshold": 38,
                "force_watering": False,
                "schedules": [],
            },
            "firmware_version": "0.9.8",
            "target_firmware_version": "1.1.0",
            "ota_state": "failed",
            "ota_error": "download timeout",
        },
    }
    for device_id, record in devices.items():
        statuses = statuses_by_device.get(device_id, [])
        if statuses:
            latest = statuses[-1]
            record["last_status_at"] = latest["received_at"]
            record["last_seen_at"] = latest["received_at"]
            record["last_status"] = latest["payload"]
            record["status_history"] = statuses

    ota_statuses_by_device = {
        "INADS-DEMO-WTR-001": [
            {
                "received_at": ago(22),
                "payload": {
                    "schema_version": 1,
                    "device_kind": "WTR",
                    "update_id": "demo-wtr-1.1.0-001",
                    "state": "started",
                    "from_version": "1.0.0",
                    "to_version": "1.1.0",
                },
            },
            {
                "received_at": ago(15),
                "payload": {
                    "schema_version": 1,
                    "device_kind": "WTR",
                    "update_id": "demo-wtr-1.1.0-001",
                    "state": "downloaded",
                    "from_version": "1.0.0",
                    "to_version": "1.1.0",
                },
            },
        ],
        "INADS-DEMO-WTR-003": [
            {
                "received_at": ago(760),
                "payload": {
                    "schema_version": 1,
                    "device_kind": "WTR",
                    "update_id": "demo-wtr-1.1.0-003",
                    "state": "failed",
                    "from_version": "0.9.8",
                    "to_version": "1.1.0",
                    "error": "download timeout",
                },
            }
        ],
    }
    if selected_device_id not in devices and requested_device_id is None:
        selected_device_id = next(iter(devices), None)
    selected_statuses = statuses_by_device.get(selected_device_id, [])
    selected_ota_statuses = ota_statuses_by_device.get(selected_device_id, [])
    selected_events = [
        {
            "occurred_at": status_entry["received_at"],
            "event_type": "status",
            "direction": "in",
            "topic": f"ina/devices/{selected_device_id}/status",
            "payload": status_entry["payload"],
        }
        for status_entry in selected_statuses[-5:]
    ]
    connection_events = [
        {
            "occurred_at": ago(10),
            "event_type": "mqtt_client_disconnected",
            "direction": "broker",
            "topic": "$SYS/broker/log/N",
            "action": "disconnect",
            "payload": {"client_id": selected_device_id, "reason": "disconnect"},
        },
        {
            "occurred_at": ago(12),
            "event_type": "mqtt_client_connected",
            "direction": "broker",
            "topic": "$SYS/broker/log/N",
            "action": "connect",
            "payload": {"client_id": selected_device_id, "remote_address": "192.0.2.24:51411"},
        },
    ]
    firmware_artifacts = {
        "WTR:1.1.0": {
            "version": "1.1.0",
            "device_kind": "WTR",
            "rollout_state": "active",
            "size": 1179648,
            "sha256": "d" * 64,
            "build_id": "demo-build-20260702",
            "url": "http://demo-hub.local:39151/firmware/WTR/1.1.0/firmware.bin",
            "updated_at": ago(360),
        }
    }
    return {
        "devices": devices,
        "selected_device_id": selected_device_id,
        "selected_statuses": selected_statuses,
        "selected_ota_statuses": selected_ota_statuses,
        "firmware_artifacts": firmware_artifacts,
        "recent_events": selected_events,
        "connection_events": connection_events,
    }


@app.route("/mqtt-devices", methods=["GET"])
def mqtt_devices_page():
    device_id = request.args.get("device_id")
    demo_mode = _is_truthy_request_arg(request.args.get("demo"))
    if device_id:
        prefix = "/demo/mqtt-devices" if demo_mode else "/mqtt-devices"
        return redirect(f"{prefix}/{device_id}")
    return _mqtt_devices_page_response(
        demo_mode=demo_mode,
        page_mode="list",
    )


@app.route("/mqtt-devices/<device_id>", methods=["GET"])
def mqtt_device_detail_page(device_id):
    return _mqtt_devices_page_response(demo_mode=False, device_id=device_id, page_mode="detail")


@app.route("/demo/mqtt-devices", methods=["GET"])
def mqtt_devices_demo_page():
    device_id = request.args.get("device_id")
    if device_id:
        return redirect(f"/demo/mqtt-devices/{device_id}")
    return _mqtt_devices_page_response(demo_mode=True, page_mode="list")


@app.route("/demo/mqtt-devices/<device_id>", methods=["GET"])
def mqtt_device_demo_detail_page(device_id):
    return _mqtt_devices_page_response(demo_mode=True, device_id=device_id, page_mode="detail")


def _mqtt_device_catalog_url(path, query, page):
    parameters = {key: value for key, value in {"q": query, "page": page if page > 1 else ""}.items() if value not in ("", None)}
    return f"{path}?{urlencode(parameters)}" if parameters else path


def _mqtt_devices_page_response(demo_mode=False, device_id=None, page_mode="list"):
    is_detail_page = page_mode == "detail"
    device_query = request.args.get("q", "").strip()[:200] if not is_detail_page else ""
    device_page = request.args.get("page", 1) if not is_detail_page else 1
    device_page_size = 24
    device_catalog = {"total": 0, "page": 1, "page_size": device_page_size, "page_count": 1, "has_previous": False, "has_next": False}
    camera_devices = []
    if demo_mode:
        demo_data = _demo_mqtt_admin_page_data(device_id)
        devices = demo_data["devices"]
        selected_device_id = demo_data["selected_device_id"] if is_detail_page else None
        selected_statuses = demo_data["selected_statuses"] if is_detail_page else []
        selected_ota_statuses = demo_data["selected_ota_statuses"] if is_detail_page else []
        firmware_artifacts = demo_data["firmware_artifacts"]
        connection_events = demo_data["connection_events"] if is_detail_page else []
        if not is_detail_page:
            terms = search_terms(device_query)
            matches = [
                (candidate_id, record)
                for candidate_id, record in devices.items()
                if matches_search(
                    terms,
                    [candidate_id, record.get("name"), record.get("location"), record.get("device_kind"), record.get("state")],
                )
            ]
            matches.sort(key=lambda item: ((item[1].get("name") or item[0]).casefold(), item[0]))
            try:
                page_result = paginate(matches, page=device_page, page_size=device_page_size)
            except ValueError:
                page_result = paginate(matches, page=1, page_size=device_page_size)
            devices = dict(page_result.pop("items"))
            device_catalog = page_result
    else:
        if is_detail_page:
            selected_record = device_config_service().find_record(device_id)
            if selected_record is None:
                return jsonify({"error": "device not found"}), 404
            devices = {device_id: selected_record}
        else:
            try:
                page_result = device_config_service().search_records(
                    query=device_query,
                    page=device_page,
                    page_size=device_page_size,
                )
            except ValueError:
                page_result = device_config_service().search_records(page=1, page_size=device_page_size)
            devices = page_result.pop("items")
            device_catalog = page_result
        selected_device_id = device_id if is_detail_page else None
        # find_record already returns an isolated snapshot, including histories.
        # Reuse it instead of repeatedly copying the entire device record.
        selected_statuses = (selected_record.get("status_history") or [])[-MQTT_ADMIN_STATUS_HISTORY_LIMIT:] if is_detail_page else []
        selected_ota_statuses = (selected_record.get("ota_status_history") or [])[-20:] if is_detail_page else []
        firmware_artifacts = ota_update_service().get_artifacts()
        connection_events = list_device_events(limit=50, device_id=selected_device_id, connection_events_only=True) if selected_device_id else []
        if not is_detail_page:
            camera_devices = camera_management_service().list(query=device_query)
    selected_device = devices.get(selected_device_id) if selected_device_id else None
    if is_detail_page and selected_device is None:
        return jsonify({"error": "device not found"}), 404
    layout_context = _build_device_layout_context(selected_device_id, selected_device) if selected_device and not demo_mode else None
    admin_view = _build_mqtt_admin_view(
        devices,
        selected_device_id,
        selected_device,
        selected_statuses,
        selected_ota_statuses,
        layout_context=layout_context,
        connection_events=connection_events,
    )
    device_link_prefix = "/demo/mqtt-devices/" if demo_mode else "/mqtt-devices/"
    list_path = "/demo/mqtt-devices" if demo_mode else "/mqtt-devices"
    device_catalog["previous_url"] = (
        _mqtt_device_catalog_url(list_path, device_query, int(device_catalog["page"]) - 1) if device_catalog["has_previous"] else ""
    )
    device_catalog["next_url"] = _mqtt_device_catalog_url(list_path, device_query, int(device_catalog["page"]) + 1) if device_catalog["has_next"] else ""

    return render_template(
        "mqtt_devices.html",
        devices=devices,
        selected_device_id=selected_device_id,
        selected_device=selected_device,
        firmware_artifacts=_format_firmware_artifacts_for_ui(firmware_artifacts),
        firmware_target_options=_build_firmware_target_options(firmware_artifacts, selected_device),
        admin_view=admin_view,
        format_json=_format_json,
        format_datetime=_format_datetime,
        demo_mode=demo_mode,
        device_link_prefix=device_link_prefix,
        is_detail_page=is_detail_page,
        list_path=list_path,
        device_query=device_query,
        device_catalog=device_catalog,
        camera_devices=camera_devices,
    )


# ==========================================
# Field pages
# ==========================================
@app.route("/preferences", methods=["GET"])
def user_preferences_page():
    user = current_user_from_request(request)
    preferences = _current_user_preferences(user.email)
    return render_template("user_preferences.html", user=user, preferences=preferences)


@app.route("/local/api/me/preferences", methods=["GET", "PATCH"])
def current_user_preferences_api():
    user = current_user_from_request(request)
    repository = user_preference_repository()
    if request.method == "GET":
        return jsonify({"user": {"email": user.email, "role": user.role}, "preferences": _current_user_preferences(user.email)})

    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        expected_version = int(request_body.get("version", -1))
    except (TypeError, ValueError):
        return jsonify({"error": "version must be an integer"}), 400
    try:
        preferences = repository.update(user.email, request_body, expected_version)
    except UserPreferenceConflictError as exc:
        return jsonify({"error": str(exc), "code": "revision_conflict", "current": exc.current}), 409
    except UserPreferenceValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"user": {"email": user.email, "role": user.role}, "preferences": preferences})


def _current_user_preferences(user_email):
    return effective_preferences(user_preference_repository(), user_email)


def _accessibility_body_class(preferences):
    values = preferences.get("preferences") if isinstance(preferences, dict) else {}
    font_size = str((values or {}).get("font_size") or DEFAULT_FONT_SIZE)
    if font_size not in SUPPORTED_FONT_SIZES:
        font_size = DEFAULT_FONT_SIZE
    contrast = str((values or {}).get("contrast") or DEFAULT_CONTRAST_MODE)
    if contrast not in SUPPORTED_CONTRAST_MODES:
        contrast = DEFAULT_CONTRAST_MODE
    return f"a11y-font-{font_size.replace('_', '-')} a11y-contrast-{contrast}"


def _request_ui_locale():
    """Return the explicitly requested UI language without changing saved preferences."""
    return "en" if request.args.get("lang", "").strip().lower() == "en" else "ja"


@app.context_processor
def inject_accessibility_preferences():
    try:
        user = current_user_from_request(request)
        preferences = _current_user_preferences(user.email)
    except AccessAuthenticationError:
        preferences = {"preferences": {"font_size": DEFAULT_FONT_SIZE, "contrast": DEFAULT_CONTRAST_MODE}}
    return {
        "accessibility_body_class": _accessibility_body_class(preferences),
        "ui_locale": _request_ui_locale(),
    }


def _current_plant_advice_profile():
    user = current_user_from_request(request)
    preferences = _current_user_preferences(user.email).get("preferences", {})
    experience_level = str(preferences.get("cultivation_experience") or DEFAULT_CULTIVATION_EXPERIENCE_LEVEL)
    if experience_level not in SUPPORTED_CULTIVATION_EXPERIENCE_LEVELS:
        experience_level = DEFAULT_CULTIVATION_EXPERIENCE_LEVEL
    return {"experience_level": experience_level}


AI_TEMPERATURE_MODES = {"auto", "default", "custom"}
AI_REASONING_EFFORTS = {"", "none", "minimal", "low", "medium", "high", "xhigh", "max"}


def _parse_ai_model_parameters(source, prefix, current=None):
    current = current if isinstance(current, dict) else {}
    mode = str(source.get(f"{prefix}_temperature_mode", current.get(f"{prefix}_temperature_mode", "auto")) or "auto")
    if mode not in AI_TEMPERATURE_MODES:
        raise ValueError(f"{prefix}_temperature_mode is invalid")
    raw_temperature = source.get(f"{prefix}_temperature", current.get(f"{prefix}_temperature", 1.0))
    try:
        temperature = float(raw_temperature)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{prefix}_temperature must be a number") from exc
    if not 0 <= temperature <= 2:
        raise ValueError(f"{prefix}_temperature must be between 0 and 2")
    reasoning_effort = str(source.get(f"{prefix}_reasoning_effort", current.get(f"{prefix}_reasoning_effort", "")) or "")
    if reasoning_effort not in AI_REASONING_EFFORTS:
        raise ValueError(f"{prefix}_reasoning_effort is invalid")
    return {
        f"{prefix}_temperature_mode": mode,
        f"{prefix}_temperature": temperature,
        f"{prefix}_reasoning_effort": reasoning_effort,
    }


def _redact_ai_error(value):
    redacted = str(value or "")
    ai_settings = setting().get("ai") or {}
    for secret_key in ("text_analyze_api_key", "image_analyze_api_key"):
        secret_value = str(ai_settings.get(secret_key) or "")
        if secret_value:
            redacted = redacted.replace(secret_value, "[redacted]")
    return redacted


def _ai_error_diagnostic(exc: AIRequestError | RuntimeError):
    message = _redact_ai_error(exc)
    detail = _redact_ai_error(getattr(exc, "technical_detail", ""))
    code = str(getattr(exc, "code", "") or "")
    parameter = str(getattr(exc, "parameter", "") or "")
    status = getattr(exc, "upstream_status", None)
    haystack = f"{message} {detail} {code} {parameter}".lower()
    if "temperature" in haystack:
        title = "出力の揺らぎ設定がモデルに対応していません"
        summary = "選択したモデルは、指定した温度を受け付けませんでした。"
        suggestions = [
            "「モデル特性を調整」を開き、出力の揺らぎを「自動調整（おすすめ）」に変更します。",
            "設定を保存してから、もう一度「接続を確認」を押します。",
        ]
        category = "unsupported_parameter"
    elif "reasoning" in haystack or parameter == "reasoning_effort":
        title = "考える深さがモデルに対応していません"
        summary = "選択したモデルは、指定した推論レベルを受け付けませんでした。"
        suggestions = [
            "「考える深さ」を「モデルに任せる」に戻します。",
            "設定を保存してから、もう一度接続を確認します。",
        ]
        category = "unsupported_parameter"
    elif status in {401, 403} or any(marker in haystack for marker in ("api key", "authentication", "unauthorized")):
        title = "APIキーを確認してください"
        summary = "AIサービスが認証情報を受け付けませんでした。"
        suggestions = ["APIキーが失効していないか確認します。", "正しいAPIキーを再登録して接続を確認します。"]
        category = "authentication"
    elif status == 404 or "model_not_found" in haystack or "does not exist" in haystack:
        title = "モデル名または接続先を確認してください"
        summary = "指定したモデルを接続先で見つけられませんでした。"
        suggestions = ["モデルIDの綴りを確認します。", "そのモデルを利用できるBase URLとAPIキーか確認します。"]
        category = "model_not_found"
    elif status == 429 or "rate limit" in haystack or "quota" in haystack:
        title = "AIサービスの利用上限に達しています"
        summary = "短時間の利用上限または契約上の残量を超えました。"
        suggestions = ["少し時間を置いて再試行します。", "AIサービス側の利用上限・残高を確認します。"]
        category = "rate_limit"
    elif code in {"connection_error", "timeout"} or status is None:
        title = "AIサービスへ接続できませんでした"
        summary = message or "ネットワークまたは接続先から応答を受け取れませんでした。"
        suggestions = ["Base URLとHubのインターネット接続を確認します。", "少し時間を置いて再試行します。"]
        category = "connection"
    else:
        title = "AI設定を確認してください"
        summary = message or "AIサービスがリクエストを処理できませんでした。"
        suggestions = ["モデルID、Base URL、上級者設定を確認します。", "設定を保存してから再試行します。"]
        category = "provider_error"
    return {
        "title": title,
        "summary": summary,
        "suggestions": suggestions,
        "category": category,
        "code": code,
        "parameter": parameter,
        "upstream_status": status,
        "technical_detail": detail or message,
    }


@app.route("/settings", methods=["GET", "POST"])
def hub_settings_page():
    user = current_user_from_request(request)
    if user.role != "admin":
        return render_template("settings_forbidden.html", user=user), 403
    current_ai = dict(setting().get("ai") or {})
    current_discord = dict(setting().get("discord") or {})
    current_instagram = dict(setting().get("instagram") or {})
    if request.method == "POST":
        section = request.form.get("settings_section", "ai")
        if section == "ai":
            try:
                plant_calendar_prompt_template = validate_plant_calendar_prompt_template(request.form.get("plant_calendar_prompt_template", ""))
                plant_calendar_web_knowledge_cache_days = max(
                    1,
                    min(365, int(request.form.get("plant_calendar_web_knowledge_cache_days", "30"))),
                )
                model_parameters = {
                    **_parse_ai_model_parameters(request.form, "text_analyze", current_ai),
                    **_parse_ai_model_parameters(request.form, "image_analyze", current_ai),
                }
            except ValueError as exc:
                return str(exc), 400
            setting().set(
                "ai",
                {
                    "enabled": request.form.get("enabled") == "on",
                    "text_analyze_base_url": request.form.get("text_analyze_base_url", "").strip(),
                    "text_analyze_model": request.form.get("text_analyze_model", "").strip(),
                    "image_analyze_base_url": request.form.get("image_analyze_base_url", "").strip(),
                    "image_analyze_model": request.form.get("image_analyze_model", "").strip(),
                    "plant_calendar_web_knowledge_enabled": request.form.get("plant_calendar_web_knowledge_enabled") == "on",
                    "plant_calendar_web_knowledge_cache_days": plant_calendar_web_knowledge_cache_days,
                    "plant_calendar_prompt_template": plant_calendar_prompt_template,
                    **model_parameters,
                },
            )
            for channel in ("text", "image"):
                secret_key = f"{channel}_analyze_api_key"
                if request.form.get(f"clear_{secret_key}") == "on":
                    setting().set_secret("ai", secret_key, "")
                    continue
                submitted_secret = request.form.get(secret_key, "")
                if submitted_secret:
                    setting().set_secret("ai", secret_key, submitted_secret.strip())
            ai_content_service().reload_settings()
            reload_instagram_post_task_settings()
        elif section == "notifications":
            if request.form.get("disable_all") == "1":
                updated_discord = {**current_discord, "enabled": False}
            else:
                try:
                    reminder_days = max(
                        0,
                        min(30, int(request.form.get("plant_task_reminder_days_before", "7"))),
                    )
                except ValueError:
                    return "plant_task_reminder_days_before must be between 0 and 30", 400
                updated_discord = {
                    "enabled": request.form.get("enabled") == "on",
                    "notify_plant_tasks": request.form.get("notify_plant_tasks") == "on",
                    "plant_task_notify_new": request.form.get("plant_task_notify_new") == "on",
                    "plant_task_reminder_days_before": reminder_days,
                    "plant_task_notify_on_start_day": request.form.get("plant_task_notify_on_start_day") == "on",
                    "plant_task_notify_during_window": request.form.get("plant_task_notify_during_window") == "on",
                    "notify_new_device": request.form.get("notify_new_device") == "on",
                    "notify_device_offline": request.form.get("notify_device_offline") == "on",
                    "notify_watering_missing": request.form.get("notify_watering_missing") == "on",
                    "notify_soil_calibration_suggested": request.form.get("notify_soil_calibration_suggested") == "on",
                    "notify_mqtt_activity": request.form.get("notify_mqtt_activity") == "on",
                    "notify_operations_security_alerts": request.form.get("notify_operations_security_alerts") == "on",
                    "security_alert_cooldown_sec": current_discord.get("security_alert_cooldown_sec", 300),
                }
            setting().set("discord", updated_discord)
            reload_discord_notification_settings()
        elif section == "instagram":
            post_schedule_start = request.form.get("post_schedule_start", "09:01").strip()
            sensor_feed_schedule_start = request.form.get("sensor_feed_schedule_start", "20:00").strip()
            try:
                datetime.strptime(post_schedule_start, "%H:%M")
                datetime.strptime(sensor_feed_schedule_start, "%H:%M")
            except ValueError:
                return "Instagram schedules must use HH:MM", 400
            camera_id = request.form.get("camera_id", "").strip()
            camera_ids = {item["id"] for item in _instagram_camera_options(current_instagram.get("camera_id", ""))}
            if camera_id and camera_id not in camera_ids:
                return "camera_id must identify a registered camera", 400
            sensor_id = request.form.get("sensor_id", "").strip()
            sensor_ids = {item["id"] for item in _instagram_sensor_options(current_instagram.get("sensor_id", ""))}
            if sensor_id and sensor_id not in sensor_ids:
                return "sensor_id must identify a registered sensor device", 400
            setting().set(
                "instagram",
                {
                    "posting_paused": request.form.get("posting_paused") == "on",
                    "post_schedule_start": post_schedule_start,
                    "sensor_feed_enabled": request.form.get("sensor_feed_enabled") == "on",
                    "sensor_feed_schedule_start": sensor_feed_schedule_start,
                    "sensor_id": sensor_id,
                    "camera_id": camera_id,
                    "plant_position_prompt": request.form.get("plant_position_prompt", "").strip(),
                },
            )
            reload_instagram_post_task_settings()
            reload_instagram_sensor_feed_task_settings()
        else:
            return "unsupported settings section", 400
        return redirect(f"/settings?{urlencode({'section': section, 'saved': '1'})}")

    visible_ai = {
        "enabled": bool(current_ai.get("enabled")),
        "text_analyze_base_url": current_ai.get("text_analyze_base_url", ""),
        "text_analyze_model": current_ai.get("text_analyze_model", ""),
        "text_analyze_temperature_mode": current_ai.get("text_analyze_temperature_mode", "auto"),
        "text_analyze_temperature": float(current_ai.get("text_analyze_temperature", 1.0)),
        "text_analyze_reasoning_effort": current_ai.get("text_analyze_reasoning_effort", ""),
        "image_analyze_base_url": current_ai.get("image_analyze_base_url", ""),
        "image_analyze_model": current_ai.get("image_analyze_model", ""),
        "image_analyze_temperature_mode": current_ai.get("image_analyze_temperature_mode", "auto"),
        "image_analyze_temperature": float(current_ai.get("image_analyze_temperature", 1.0)),
        "image_analyze_reasoning_effort": current_ai.get("image_analyze_reasoning_effort", ""),
        "plant_calendar_web_knowledge_enabled": bool(current_ai.get("plant_calendar_web_knowledge_enabled", True)),
        "plant_calendar_web_knowledge_cache_days": int(current_ai.get("plant_calendar_web_knowledge_cache_days", 30)),
        "plant_calendar_prompt_template": current_ai.get("plant_calendar_prompt_template", DEFAULT_PLANT_CALENDAR_PROMPT_TEMPLATE),
        "text_key_configured": setting().secret_configured("ai", "text_analyze_api_key"),
        "image_key_configured": setting().secret_configured("ai", "image_analyze_api_key"),
    }
    visible_instagram = {
        "posting_paused": bool(current_instagram.get("posting_paused", False)),
        "post_schedule_start": current_instagram.get("post_schedule_start", "09:01"),
        "sensor_feed_enabled": bool(current_instagram.get("sensor_feed_enabled", False)),
        "sensor_feed_schedule_start": current_instagram.get("sensor_feed_schedule_start", "20:00"),
        "sensor_id": current_instagram.get("sensor_id", ""),
        "camera_id": current_instagram.get("camera_id", ""),
        "plant_position_prompt": current_instagram.get("plant_position_prompt", ""),
        "account_id": current_instagram.get("account_id", ""),
        "account_username": current_instagram.get("account_username", ""),
        "account_profile_updated_at": current_instagram.get("account_profile_updated_at", ""),
        "credentials_configured": bool(current_instagram.get("user_id") and current_instagram.get("access_token")),
    }
    public_notification_url = cloudflare_public_base_url()
    try:
        current_reminder_days = int(current_discord.get("plant_task_reminder_days_before", 7))
    except (TypeError, ValueError):
        current_reminder_days = 7
    visible_discord = {
        "enabled": bool(current_discord.get("enabled", True)),
        "notify_plant_tasks": bool(current_discord.get("notify_plant_tasks", True)),
        "plant_task_notify_new": bool(current_discord.get("plant_task_notify_new", True)),
        "plant_task_reminder_days_before": max(0, min(30, current_reminder_days)),
        "plant_task_notify_on_start_day": bool(current_discord.get("plant_task_notify_on_start_day", True)),
        "plant_task_notify_during_window": bool(current_discord.get("plant_task_notify_during_window", True)),
        "notify_new_device": bool(current_discord.get("notify_new_device", True)),
        "notify_device_offline": bool(current_discord.get("notify_device_offline", True)),
        "notify_watering_missing": bool(current_discord.get("notify_watering_missing", True)),
        "notify_soil_calibration_suggested": bool(current_discord.get("notify_soil_calibration_suggested", True)),
        "notify_mqtt_activity": bool(current_discord.get("notify_mqtt_activity", False)),
        "notify_operations_security_alerts": bool(current_discord.get("notify_operations_security_alerts", True)),
        "webhook_configured": bool(current_discord.get("webhook_url")),
        "public_base_url": public_notification_url,
        "public_url_configured": bool(public_notification_url),
    }
    device_records = device_config_service().get_all_records()
    post_watering_rules = post_watering_rule_views(post_watering_moisture_service().list_rules(), device_records)
    post_watering_moisture = {
        "rules": post_watering_rules,
        "enabled_count": sum(1 for rule in post_watering_rules if rule.get("enabled") is True),
    }
    database_settings = setting().get("turso") or {}
    database_url = str(database_settings.get("database_url") or "local")
    database_label = "Turso replica" if database_url.startswith(("libsql://", "http://", "https://")) else "端末内DB"
    infrastructure = (
        {"label": database_label, "configured": bool(database_url)},
        {
            "label": "R2 / S3",
            "configured": bool((setting().get("storage_bucket") or {}).get("endpoint_url") and (setting().get("storage_bucket") or {}).get("bucket_name")),
        },
        {"label": "MQTT", "configured": bool((setting().get("mqtt") or {}).get("mqtt_broker"))},
        {"label": "AIテキストAPIキー", "configured": visible_ai["text_key_configured"]},
        {"label": "AI画像APIキー", "configured": visible_ai["image_key_configured"]},
    )
    response = app.make_response(
        render_template(
            "hub_settings.html",
            ai=visible_ai,
            discord=visible_discord,
            post_watering_moisture=post_watering_moisture,
            plant_calendar_prompt_max_length=PLANT_CALENDAR_PROMPT_MAX_LENGTH,
            instagram=visible_instagram,
            instagram_camera_options=_instagram_camera_options(current_instagram.get("camera_id", "")),
            infrastructure=infrastructure,
            active_section=request.args.get("section") if request.args.get("section") in {"ai", "notifications", "instagram", "system"} else "ai",
            saved=request.args.get("saved") == "1",
            user=user,
            instagram_sensor_options=_instagram_sensor_options(current_instagram.get("sensor_id", "")),
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _post_watering_sensor_trend(
    sensor_device_id: str,
    *,
    measurement_source: str = DEFAULT_MEASUREMENT_SOURCE,
    sensor_record: dict | None = None,
    days: int = DEFAULT_WINDOW_DAYS,
    now: datetime | None = None,
):
    range_end = now or datetime.now(UTC)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=UTC)
    range_end = range_end.astimezone(UTC)
    days = min(MAX_WINDOW_DAYS, max(MIN_WINDOW_DAYS, int(days)))
    range_start = range_end - timedelta(days=days)
    try:
        if measurement_source == DEFAULT_MEASUREMENT_SOURCE:
            measurements = sensor_measurement_repository().between_for_devices(
                [sensor_device_id],
                range_start.isoformat(),
                range_end.isoformat(),
                limit=5000,
                metric="soil_moisture_percent",
            )
        else:
            measurements = soil_moisture_measurements_from_status_history((sensor_record or {}).get("status_history"), measurement_source)
    except Exception:  # noqa: BLE001
        app.logger.exception("Unable to load post-watering moisture trend for sensor_device_id=%s", sensor_device_id)
        return {
            "sensor_device_id": sensor_device_id,
            "measurement_source": measurement_source,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "points": [],
            "latest": None,
            "minimum": None,
            "maximum": None,
            "days": days,
            "error": f"直近{days}日分の測定値を読み込めませんでした。時間をおいて再読み込みしてください。",
        }

    points = []
    for measurement in measurements:
        if measurement.get("metric") != "soil_moisture_percent":
            continue
        measured_at = _parse_datetime(measurement.get("measured_at"))
        value = measurement.get("value")
        if measured_at is None or isinstance(value, bool) or not isinstance(value, int | float):
            continue
        if measured_at < range_start or measured_at > range_end:
            continue
        numeric_value = float(value)
        if not 0 <= numeric_value <= 100:
            continue
        points.append(
            {
                "measured_at": measured_at.astimezone(UTC).isoformat(),
                "label": measured_at.astimezone(_local_timezone()).strftime("%m/%d %H:%M"),
                "value": round(numeric_value, 1),
            }
        )
    points.sort(key=lambda item: item["measured_at"])
    maximum_points = 480
    if len(points) > maximum_points:
        step = (len(points) + maximum_points - 1) // maximum_points
        sampled = points[::step]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        points = sampled
    values = [point["value"] for point in points]
    return {
        "sensor_device_id": sensor_device_id,
        "measurement_source": measurement_source,
        "days": days,
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "points": points,
        "latest": values[-1] if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "error": "",
    }


@app.route("/local/api/settings/post-watering-moisture/trend", methods=["GET"])
def post_watering_moisture_trend_api():
    user = current_user_from_request(request)
    if user.role != "admin":
        return jsonify({"error": "admin access required"}), 403
    sensor_device_id = request.args.get("sensor_device_id", "").strip()
    records = device_config_service().get_all_records()
    valid_sensor_ids = {item["id"] for item in soil_moisture_sensor_options(records)}
    if sensor_device_id not in valid_sensor_ids:
        return jsonify({"error": "土壌水分を測定できる利用中のセンサーを選んでください。"}), 400
    sensor_record = records.get(sensor_device_id) or {}
    measurement_source = request.args.get("measurement_source", DEFAULT_MEASUREMENT_SOURCE).strip()
    if measurement_source not in {item["id"] for item in soil_moisture_source_options(sensor_record)}:
        return jsonify({"error": "判定に使う土壌水分の値を選んでください。"}), 400
    try:
        days = int(request.args.get("days", DEFAULT_WINDOW_DAYS))
    except (TypeError, ValueError):
        return jsonify({"error": "表示期間は1〜14日で入力してください。"}), 400
    if not MIN_WINDOW_DAYS <= days <= MAX_WINDOW_DAYS:
        return jsonify({"error": "表示期間は1〜14日で入力してください。"}), 400
    response = jsonify(
        _post_watering_sensor_trend(
            sensor_device_id,
            measurement_source=measurement_source,
            sensor_record=sensor_record,
            days=days,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/settings/post-watering-moisture", methods=["GET", "POST"])
def post_watering_moisture_settings_page():
    user = current_user_from_request(request)
    if user.role != "admin":
        return render_template("settings_forbidden.html", user=user), 403

    records = device_config_service().get_all_records()
    soil_sensors = soil_moisture_sensor_options(records)
    service = post_watering_moisture_service()
    requested_field_id = str((request.form.get("field_id") if request.method == "POST" else request.args.get("field_id")) or "").strip()
    return_field = field_repository().get(requested_field_id) if requested_field_id else None
    field_id = return_field["id"] if return_field else ""
    return_url = f"/fields/{field_id}#monitoring" if field_id else "/settings?section=notifications#notifications"
    return_label = "環境・設備へ戻る" if field_id else "通知設定へ戻る"
    submitted = None
    error_message = ""
    status_code = 200
    if request.method == "POST":
        if request.form.get("action") == "delete":
            requested_sensor_device_id = request.form.get("sensor_device_id", "").strip()
            try:
                service.delete_rule(requested_sensor_device_id)
            except PostWateringMoistureValidationError as exc:
                error_message = str(exc)
                status_code = 400
            else:
                if field_id:
                    return redirect(return_url)
                return redirect("/settings/post-watering-moisture?deleted=1")
        else:
            submitted = {
                "sensor_device_id": request.form.get("sensor_device_id", "").strip(),
                "measurement_source": request.form.get("measurement_source", "").strip(),
                "minimum_percent": request.form.get("minimum_percent", ""),
                "window_days": request.form.get("window_days", ""),
                "enabled": request.form.get("enabled") == "on",
            }
            original_sensor_device_id = request.form.get("original_sensor_device_id", "").strip()
            try:
                saved_rule = service.save_rule(submitted, records)
                if (
                    original_sensor_device_id
                    and original_sensor_device_id != saved_rule["sensor_device_id"]
                    and any(rule.get("sensor_device_id") == original_sensor_device_id for rule in service.list_rules())
                ):
                    service.delete_rule(original_sensor_device_id)
            except PostWateringMoistureValidationError as exc:
                error_message = str(exc)
                status_code = 400
            else:
                query = urlencode(
                    {
                        "sensor_device_id": saved_rule["sensor_device_id"],
                        "saved": "1",
                        **({"field_id": field_id} if field_id else {}),
                    }
                )
                return redirect(f"/settings/post-watering-moisture?{query}")

    rules = service.list_rules()
    requested_sensor_device_id = str(
        (submitted or {}).get("sensor_device_id")
        or request.form.get("sensor_device_id")
        or request.args.get("sensor_device_id")
        or request.args.get("watering_device_id")
        or (soil_sensors[0]["id"] if soil_sensors else "")
    )
    existing_rule = next((rule for rule in rules if rule.get("sensor_device_id") == requested_sensor_device_id), None)
    selected_rule = submitted or existing_rule or {}
    sensor_ids = {item["id"] for item in soil_sensors}
    selected_sensor_id = str(selected_rule.get("sensor_device_id") or requested_sensor_device_id)
    if selected_sensor_id not in sensor_ids:
        selected_sensor_id = soil_sensors[0]["id"] if soil_sensors else ""
    selected_sensor_record = records.get(selected_sensor_id) or {}
    selected_source_options = soil_moisture_source_options(selected_sensor_record) if selected_sensor_id else []
    selected_source_ids = {item["id"] for item in selected_source_options}
    selected_measurement_source = str(selected_rule.get("measurement_source") or DEFAULT_MEASUREMENT_SOURCE)
    if selected_measurement_source not in selected_source_ids:
        selected_measurement_source = DEFAULT_MEASUREMENT_SOURCE
    try:
        minimum_percent = float(selected_rule.get("minimum_percent", DEFAULT_MINIMUM_PERCENT))
    except (TypeError, ValueError):
        minimum_percent = DEFAULT_MINIMUM_PERCENT
    try:
        window_days = int(selected_rule.get("window_days", DEFAULT_WINDOW_DAYS))
    except (TypeError, ValueError):
        window_days = DEFAULT_WINDOW_DAYS
    selected_values = {
        "sensor_device_id": selected_sensor_id,
        "measurement_source": selected_measurement_source,
        "minimum_percent": minimum_percent,
        "window_days": min(MAX_WINDOW_DAYS, max(MIN_WINDOW_DAYS, window_days)),
        "enabled": selected_rule.get("enabled") is not False,
    }
    response = app.make_response(
        (
            render_template(
                "post_watering_moisture_wizard.html",
                soil_sensors=soil_sensors,
                selected_source_options=selected_source_options,
                selected=selected_values,
                rules=post_watering_rule_views(rules, records),
                editing_rule=post_watering_rule_views([existing_rule], records)[0] if existing_rule else None,
                error_message=error_message,
                saved=request.args.get("saved") == "1",
                deleted=request.args.get("deleted") == "1",
                discord={
                    "enabled": bool((setting().get("discord") or {}).get("enabled", True)),
                    "webhook_configured": bool((setting().get("discord") or {}).get("webhook_url")),
                },
                field_id=field_id,
                return_url=return_url,
                return_label=return_label,
                user=user,
            ),
            status_code,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/settings/ai", methods=["GET", "POST"])
def legacy_hub_ai_settings_page():
    return redirect("/settings?section=ai")


@app.get("/settings/extensions")
def hub_extensions_page():
    user = current_user_from_request(request)
    if user.role != "admin":
        return render_template("settings_forbidden.html", user=user), 403
    current_ai = dict(setting().get("ai") or {})
    base_url = str(current_ai.get("text_analyze_base_url") or "").strip()
    ai_review = {
        "configured": bool(current_ai.get("enabled") and current_ai.get("text_analyze_model") and setting().secret_configured("ai", "text_analyze_api_key")),
        "model": str(current_ai.get("text_analyze_model") or "未設定"),
        "destination": urlsplit(base_url).netloc or "未設定",
    }
    service = extension_installation_service()
    response = app.make_response(
        render_template(
            "hub_extensions.html",
            bundled_extensions=service.bundled_extensions(),
            installed_extensions=service.installed_extensions(),
            ai_review=ai_review,
            user=user,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/local/api/extensions/reviews")
def review_extension_upload_api():
    user = current_user_from_request(request)
    if user.role != "admin":
        return jsonify({"error": "admin role is required"}), 403
    uploaded = request.files.get("extension")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "追加機能ファイルを選択してください。"}), 400
    payload = uploaded.stream.read(MAX_PACKAGE_BYTES + 1)
    try:
        review = extension_installation_service().review_upload(uploaded.filename, payload, reviewed_by=user.email)
    except ExtensionReviewError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"review": review})


@app.post("/local/api/extensions/reviews/<review_id>/ai-audit")
def audit_extension_review_api(review_id):
    user = current_user_from_request(request)
    if user.role != "admin":
        return jsonify({"error": "admin role is required"}), 403
    request_body = request.get_json(silent=True)
    confirmed = isinstance(request_body, dict) and request_body.get("confirmed") is True
    try:
        review = extension_installation_service().audit_review(
            review_id,
            consent_confirmed=confirmed,
            approved_by=user.email,
        )
    except ExtensionReviewError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"review": review})


@app.post("/local/api/extensions/reviews/<review_id>/install")
def install_extension_review_api(review_id):
    user = current_user_from_request(request)
    if user.role != "admin":
        return jsonify({"error": "admin role is required"}), 403
    try:
        result = extension_installation_service().install_review(review_id, installed_by=user.email)
    except (ExtensionReviewError, ExtensionInstallError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/local/api/settings/ai/test", methods=["POST"])
def test_hub_ai_settings_api():
    if current_user_from_request(request).role != "admin":
        return jsonify({"error": "admin role is required"}), 403
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    channel = str(request_body.get("channel") or "text")
    if channel not in {"text", "image"}:
        return jsonify({"error": "channel must be text or image"}), 400
    try:
        prefix = "image_analyze" if channel == "image" else "text_analyze"
        parameter_values = _parse_ai_model_parameters(
            {
                f"{prefix}_temperature_mode": request_body.get("temperature_mode", "auto"),
                f"{prefix}_temperature": request_body.get("temperature", 1.0),
                f"{prefix}_reasoning_effort": request_body.get("reasoning_effort", ""),
            },
            prefix,
        )
        result = ai_content_service().test_connection(
            channel,
            {
                "base_url": str(request_body.get("base_url") or "").strip(),
                "model": str(request_body.get("model") or "").strip(),
                "temperature_mode": parameter_values[f"{prefix}_temperature_mode"],
                "temperature": parameter_values[f"{prefix}_temperature"],
                "reasoning_effort": parameter_values[f"{prefix}_reasoning_effort"],
            },
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        diagnostic = _ai_error_diagnostic(exc)
        return jsonify({"error": diagnostic["summary"], "diagnostic": diagnostic}), 422
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/local/api/settings/instagram/profile", methods=["POST"])
def refresh_instagram_account_profile_api():
    if current_user_from_request(request).role != "admin":
        return jsonify({"error": "admin role is required"}), 403
    instagram = dict(setting().get("instagram") or {})
    if not instagram.get("user_id") or not instagram.get("access_token"):
        return jsonify({"error": "InstagramのユーザーIDとアクセストークンを初期設定してください"}), 400
    try:
        profile = InstagramClient(instagram["user_id"], instagram["access_token"]).get_account_profile()
    except RuntimeError:
        return jsonify({"error": "Instagram APIからアカウント情報を取得できませんでした"}), 502
    updated_at = datetime.now(UTC).isoformat(timespec="seconds")
    setting().set(
        "instagram",
        {
            "account_id": profile["id"],
            "account_username": profile["username"],
            "account_profile_updated_at": updated_at,
        },
    )
    reload_instagram_post_task_settings()
    reload_instagram_sensor_feed_task_settings()
    response = jsonify(
        {
            "id": profile["id"],
            "username": profile["username"],
            "updated_at": updated_at,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _instagram_camera_options(selected_camera_id=""):
    cameras = {}
    for device_id, camera_record in (camera_connector().camera_device_repository.get_all() or {}).items():
        normalized_camera = camera_record if isinstance(camera_record, dict) else {}
        cameras[str(device_id)] = normalized_camera.get("name") or str(device_id)
    for device_id, record in (device_config_service().get_all_records() or {}).items():
        if (record or {}).get("device_kind") == "CAM":
            cameras.setdefault(str(device_id), (record or {}).get("name") or str(device_id))
    if selected_camera_id and selected_camera_id not in cameras:
        cameras[selected_camera_id] = f"{selected_camera_id}（現在の設定・未登録）"
    return [{"id": device_id, "name": name} for device_id, name in sorted(cameras.items(), key=lambda item: (item[1].lower(), item[0].lower()))]


def _instagram_sensor_options(selected_sensor_id=""):
    eligible_kinds = {"ENV", "SOI", "WTR", "WRS", "FGT"}
    sensors = {}
    for device_id, record in (device_config_service().get_all_records() or {}).items():
        normalized = record if isinstance(record, dict) else {}
        device_kind = str(normalized.get("device_kind") or "").upper()
        if device_kind not in eligible_kinds or normalized.get("state") == "retired":
            continue
        sensors[str(device_id)] = {
            "name": normalized.get("name") or str(device_id),
            "kind": device_kind,
        }
    if selected_sensor_id and selected_sensor_id not in sensors:
        sensors[selected_sensor_id] = {"name": f"{selected_sensor_id}（現在の設定・未登録）", "kind": ""}
    return [
        {"id": device_id, "name": details["name"], "kind": details["kind"]}
        for device_id, details in sorted(sensors.items(), key=lambda item: (item[1]["name"].lower(), item[0].lower()))
    ]


@app.route("/fields", methods=["GET", "POST"])
def fields_page():
    repo = field_repository()
    if request.method == "POST":
        try:
            data = _field_create_form_data(request.form)
            field = repo.upsert(None, data)
        except FieldValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        return redirect(f"/fields/{field['id']}")

    return _render_field_catalog(home_mode=False)


def _render_field_catalog(*, home_mode: bool):
    query = request.args.get("q", "").strip()[:120]
    prefecture = request.args.get("prefecture", "").strip()
    environment_type = request.args.get("environment_type", "").strip()
    if prefecture not in JAPAN_PREFECTURES:
        prefecture = ""
    if environment_type not in FIELD_ENVIRONMENT_TYPE_LABELS:
        environment_type = ""
    try:
        requested_page = max(1, int(request.args.get("page", "1")))
    except (TypeError, ValueError):
        requested_page = 1

    result = field_repository().search(
        query=query,
        prefecture=prefecture,
        environment_type=environment_type,
        page=requested_page,
        page_size=FIELD_CATALOG_PAGE_SIZE,
    )
    fields = [_build_field_list_item(field) for field in result["items"]]
    catalog_path = "/" if home_mode else "/fields"
    page = result["page"]
    page_count = result["page_count"]
    first_page_link = max(1, min(page - 2, page_count - 4))
    last_page_link = min(page_count, first_page_link + 4)
    page_links = [
        {
            "page": page_number,
            "current": page_number == page,
            "url": _field_catalog_url(
                catalog_path,
                query=query,
                prefecture=prefecture,
                environment_type=environment_type,
                page=page_number,
            ),
        }
        for page_number in range(first_page_link, last_page_link + 1)
    ]
    result.update(
        {
            "range_start": (page - 1) * result["page_size"] + 1 if result["total"] else 0,
            "range_end": min(page * result["page_size"], result["total"]),
            "page_links": page_links,
            "previous_url": (
                _field_catalog_url(
                    catalog_path,
                    query=query,
                    prefecture=prefecture,
                    environment_type=environment_type,
                    page=page - 1,
                )
                if page > 1
                else ""
            ),
            "next_url": (
                _field_catalog_url(
                    catalog_path,
                    query=query,
                    prefecture=prefecture,
                    environment_type=environment_type,
                    page=page + 1,
                )
                if page < page_count
                else ""
            ),
        }
    )
    return render_template(
        "field_catalog.html",
        page_title="圃場を選択" if home_mode else "圃場一覧",
        home_mode=home_mode,
        catalog_path=catalog_path,
        catalog=result,
        fields=fields,
        filters={
            "query": query,
            "prefecture": prefecture,
            "environment_type": environment_type,
            "active": bool(query or prefecture or environment_type),
        },
        prefectures=JAPAN_PREFECTURES,
        environment_options=FIELD_ENVIRONMENT_TYPE_OPTIONS,
        environment_labels=FIELD_ENVIRONMENT_TYPE_LABELS,
        current_user=current_user_from_request(request),
    )


def _field_catalog_url(path: str, *, query: str, prefecture: str, environment_type: str, page: int):
    parameters = {
        key: value
        for key, value in {
            "q": query,
            "prefecture": prefecture,
            "environment_type": environment_type,
            "page": page if page > 1 else "",
        }.items()
        if value not in ("", None)
    }
    return f"{path}?{urlencode(parameters)}" if parameters else path


@app.route("/fields/<field_id>", methods=["GET", "POST"])
def field_detail_page(field_id):
    repo = field_repository()
    field = repo.get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404

    if request.method == "POST":
        try:
            data = _field_create_form_data(request.form)
            repo.upsert(field_id, data)
        except FieldValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        return redirect(f"/fields/{field_id}#settings")

    compare_date = request.args.get("compare_date", "").strip()
    record_month = request.args.get("record_month", "").strip()
    response = Response(
        stream_template(
            "field_detail.html",
            field=field,
            build_context=lambda: _build_field_context(
                field,
                compare_date=compare_date,
                record_month=record_month,
                include_automatic_measurements=False,
            ),
            build_deferred_context=lambda context: _build_field_deferred_context(field, context, record_month),
            metric_labels=METRIC_LABELS,
            prefectures=JAPAN_PREFECTURES,
            environment_options=FIELD_ENVIRONMENT_TYPE_OPTIONS,
            environment_labels=FIELD_ENVIRONMENT_TYPE_LABELS,
            current_user=current_user_from_request(request),
        ),
        mimetype="text/html",
    )
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/fields/<field_id>/layout", methods=["GET"])
def field_layout_page(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    legacy_calendar_id = request.args.get("calendar", "").strip()
    if legacy_calendar_id:
        return redirect(f"/fields/{field_id}/calendar?{urlencode({'planting': legacy_calendar_id})}")
    return render_template("field_layout.html", field=field)


@app.route("/fields/<field_id>/calendar", methods=["GET"])
def field_calendar_page(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    return render_template(
        "field_calendar.html",
        field=field,
        planting_id=request.args.get("planting", "").strip(),
        action_id=request.args.get("action", "").strip(),
    )


@app.route("/fields/<field_id>/growth-monitoring", methods=["GET"])
def field_growth_monitoring_page(field_id):
    try:
        dashboard = camera_growth_monitoring_service().dashboard(field_id)
    except CameraGrowthMonitoringNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    return render_template(
        "field_growth_monitoring.html",
        dashboard=dashboard,
        current_user=current_user_from_request(request),
    )


@app.route("/local/api/fields/<field_id>/camera-growth-assessments", methods=["GET"])
def list_camera_growth_assessments_api(field_id):
    try:
        items = camera_growth_monitoring_service().list_assessments(
            field_id,
            camera_id=request.args.get("camera_id", "").strip(),
            limit=_request_limit(default=50, maximum=200),
        )
    except CameraGrowthMonitoringNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"items": items})


@app.route("/local/api/fields/<field_id>/camera-growth-assessments", methods=["POST"])
def create_camera_growth_assessment_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    camera_id = str(request_body.get("camera_id") or "").strip()
    if not camera_id:
        return jsonify({"error": "camera_id is required"}), 400
    user = current_user_from_request(request)
    preferences = effective_preferences(user_preference_repository(), user.email)
    try:
        assessment = camera_growth_monitoring_service().create_assessment(
            field_id,
            camera_id,
            created_by=user.email,
            audience={"experience_level": (preferences.get("preferences") or {}).get("cultivation_experience", "standard")},
        )
    except CameraGrowthMonitoringNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except CameraGrowthMonitoringValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except CameraGrowthAIUnavailableError as exc:
        return jsonify({"error": str(exc), "code": "image_ai_not_configured"}), 503
    except CameraGrowthCaptureError as exc:
        return jsonify({"error": str(exc), "code": "camera_capture_failed"}), 502
    except CameraGrowthAnalysisError as exc:
        return jsonify({"error": str(exc), "code": "image_analysis_failed"}), 502
    return jsonify(assessment), 201


@app.route("/local/api/fields/<field_id>/layout", methods=["GET"])
def get_field_layout_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    try:
        layout = field_layout_repository().get(field_id, field_name=field.get("name", ""))
    except FieldLayoutValidationError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify(layout)


@app.route("/local/api/fields/<field_id>/layout", methods=["PUT"])
def update_field_layout_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        user = current_user_from_request(request)
        layout = field_layout_repository().upsert(
            field_id,
            request_body,
            field_name=field.get("name", ""),
            updated_by=user.email,
        )
    except FieldLayoutConflictError as exc:
        return jsonify(
            {
                "error": str(exc),
                "code": "revision_conflict",
                "submitted_revision": request_body.get("revision"),
                "current": exc.current,
            }
        ), 409
    except FieldLayoutValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    field_layout_collaboration_service().publish_layout(field_id, layout)
    return jsonify(layout)


@app.route("/local/api/fields/<field_id>/layout/collaboration", methods=["POST"])
def update_field_layout_collaboration_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    if request.content_length is not None and request.content_length > 8 * 1024:
        return jsonify({"error": "collaboration request body is too large"}), 413
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    try:
        layout = field_layout_repository().get(field_id, field_name=field.get("name", ""))
        service = field_layout_collaboration_service()
        user = current_user_from_request(request)
        if request_body.get("leave") is True:
            snapshot = service.leave(
                field_id,
                request_body.get("client_id"),
                actor_email=user.email,
                layout=layout,
            )
        else:
            snapshot = service.touch(
                field_id,
                client_id=request_body.get("client_id"),
                actor_email=user.email,
                active_space_id=request_body.get("active_space_id", ""),
                selected_placement_id=request_body.get("selected_placement_id", ""),
                state=request_body.get("state", "viewing"),
                layout=layout,
            )
    except FieldLayoutCollaborationValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldLayoutValidationError as exc:
        return jsonify({"error": str(exc)}), 500

    response = jsonify(snapshot)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/local/api/fields/<field_id>/layout/devices", methods=["GET"])
def list_field_layout_devices_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    return jsonify(_field_layout_devices(field_id, field))


@app.route("/local/api/fields/<field_id>/layout/device-options", methods=["GET"])
def search_field_layout_devices_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    groups = set(_query_list("group"))
    include_ids = set(_query_list("include"))
    terms = search_terms(request.args.get("q", ""))
    available_devices = [device for device in _field_layout_devices(field_id, field) if not groups or device.get("group_label") in groups]
    devices = [
        device
        for device in available_devices
        if matches_search(
            terms,
            [
                device.get("id"),
                device.get("name"),
                device.get("device_kind"),
                device.get("kind_label"),
                device.get("group_label"),
                device.get("location"),
                device.get("state"),
                device.get("resources"),
            ],
        )
    ]
    devices.sort(key=lambda device: ((device.get("name") or device.get("id") or "").casefold(), device.get("id") or ""))
    try:
        result = paginate(
            devices,
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
            maximum_page_size=100,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    pinned = [device for device in available_devices if device.get("id") in include_ids]
    result["items"] = list({device["id"]: device for device in [*pinned, *result["items"]]}.values())
    return jsonify(result)


def _field_layout_devices(field_id, field):
    records = device_config_service().get_all_records()
    camera_records = {record["id"]: record for record in camera_management_service().list() if record.get("id")}
    assignments = _layout_device_assignments()
    field_device_ids = set(field.get("device_ids") or []) | set(field.get("camera_device_ids") or [])
    device_ids = sorted(set(records) | set(camera_records) | field_device_ids)
    devices = []
    for device_id in device_ids:
        assigned_field_id = assignments.get(device_id, "")
        if assigned_field_id and assigned_field_id != field_id:
            continue
        camera_record = camera_records.get(device_id)
        if camera_record is not None:
            devices.append(
                {
                    "id": device_id,
                    "name": camera_record.get("name") or device_id,
                    "device_kind": "CAM",
                    "kind_label": _device_kind_label("CAM"),
                    "group_label": "カメラ",
                    "assigned_field_id": assigned_field_id,
                    "state": "active" if camera_record.get("credentials_configured") else "pending",
                    "location": camera_record.get("ip_address") or "",
                    "resources": [],
                    "preview_url": camera_record.get("preview_url") or f"/camera/{quote(str(device_id), safe='')}#live",
                    "manage_url": camera_record.get("detail_url") or f"/camera/{quote(str(device_id), safe='')}",
                }
            )
            continue
        record = records.get(device_id) or {}
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        last_status = record.get("last_status") if isinstance(record.get("last_status"), dict) else {}
        resources = [
            {
                "resource_type": "mosfet_switch",
                "resource_id": switch.get("switch_id", ""),
                "name": switch.get("name") or switch.get("switch_id") or "機器出力",
            }
            for switch in config.get("mosfet_switches", [])
            if isinstance(switch, dict) and switch.get("enabled", True)
        ]
        device_kind = record.get("device_kind") or last_status.get("device_kind") or ""
        devices.append(
            {
                "id": device_id,
                "name": record.get("name") or device_id,
                "device_kind": device_kind,
                "kind_label": _device_kind_label(device_kind),
                "group_label": _layout_device_group_label(device_kind),
                "assigned_field_id": assigned_field_id,
                "state": record.get("state") or "unknown",
                "location": record.get("location") or "",
                "resources": resources,
                "preview_url": "",
                "manage_url": f"/mqtt-devices/{quote(str(device_id), safe='')}",
            }
        )
    return devices


def _layout_device_assignments():
    repository = field_layout_repository()
    assignments = {}
    for assigned_field_id in repository.layouts:
        try:
            layout = repository.get(assigned_field_id)
        except FieldLayoutValidationError:
            continue
        for space in layout.get("spaces", []):
            for placement in space.get("placements", []):
                device_id = (placement.get("binding") or {}).get("device_id")
                if device_id:
                    assignments[device_id] = assigned_field_id
    return assignments


def _layout_device_group_label(device_kind):
    if device_kind in {"WTR", "WRS", "FGT"}:
        return "潅水デバイス"
    if device_kind == "ENV":
        return "環境センサー"
    if device_kind == "SOI":
        return "土壌センサー"
    if device_kind == "PAR":
        return "日射・PARセンサー"
    if device_kind == "CAM":
        return "カメラ"
    return "その他デバイス"


def _query_list(name):
    values = []
    for raw_value in request.args.getlist(name):
        for item in str(raw_value or "").split(","):
            normalized = item.strip()
            if normalized and normalized not in values:
                values.append(normalized)
    return values


@app.route("/local/api/fields/<field_id>/plantings", methods=["GET"])
def list_field_plantings_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    today = request.args.get("today", "").strip() or None
    compact = _is_truthy_request_arg(request.args.get("compact"))
    calendar_planting_ids = _query_list("calendar_planting_id")
    try:
        bundle = plant_management_repository().field_bundle(
            field_id,
            today=today,
            statuses=["active"] if compact else None,
            calendar_planting_ids=calendar_planting_ids if compact else None,
            include_work_logs=not compact or bool(calendar_planting_ids),
        )
        layout = field_layout_repository().get(field_id, field_name=field.get("name", ""))
        bundle["operation_readiness"] = build_calendar_operation_readiness(bundle, field, layout, _field_device_records(field, layout))
        user = current_user_from_request(request)
        bundle["viewer"] = {"email": user.email, "role": user.role}
        return jsonify(bundle)
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/local/api/fields/<field_id>/plantings", methods=["POST"])
def create_field_planting_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    layout = field_layout_repository().get(field_id, field_name=field.get("name", ""))
    space = next((item for item in layout["spaces"] if item["id"] == request_body.get("space_id")), None)
    placement = next((item for item in (space or {}).get("placements", []) if item["id"] == request_body.get("placement_id")), None)
    if space is None or placement is None:
        return jsonify({"error": "planting placement was not found in the field layout"}), 400

    repository = plant_management_repository()
    planting_data = {
        **request_body,
        "placement_name": placement["name"],
        "cultivation_method": request_body.get("cultivation_method") or "",
    }
    planting_data["conditions"] = {
        **(request_body.get("conditions") if isinstance(request_body.get("conditions"), dict) else {}),
        "region": "",
    }
    try:
        _validate_planting_generation_input(planting_data)
        planting = repository.create_planting(field_id, planting_data)
        generation_task = plant_calendar_generation_task().enqueue(
            planting["id"],
            kind="initial",
            start_date=max(date.fromisoformat(planting["planted_on"]), date.today()).isoformat(),
            planning_notes=str(request_body.get("planning_notes") or "")[:2000],
            audience=_current_plant_advice_profile(),
            mode=str(request_body.get("mode") or "automatic"),
        )
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"planting": repository.get_planting(planting["id"]), "generation_task": generation_task}), 202


@app.route("/local/api/plantings/<planting_id>/calendar/actions", methods=["GET"])
def search_plant_calendar_actions_api(planting_id):
    repository = plant_management_repository()
    if repository.get_planting(planting_id) is None:
        return jsonify({"error": "planting not found"}), 404
    try:
        result = repository.search_actions(
            planting_id,
            query=request.args.get("q", ""),
            statuses=_query_list("status"),
            action_types=_query_list("action_type"),
            date_from=request.args.get("date_from", ""),
            date_to=request.args.get("date_to", ""),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
        )
    except (PlantManagementNotFoundError, PlantManagementValidationError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


def _validate_planting_generation_input(value):
    conditions = value.get("conditions") if isinstance(value.get("conditions"), dict) else {}
    required_values = (
        ("作物名", value.get("crop_name")),
        ("作物区分", value.get("crop_category")),
        ("定植日", value.get("planted_on")),
        ("栽培方式", value.get("cultivation_method")),
        ("用土・培地", conditions.get("soil_or_substrate")),
        ("日当たり", conditions.get("sunlight")),
    )
    missing = [label for label, item in required_values if not str(item or "").strip()]
    try:
        plant_count = int(value.get("plant_count"))
    except (TypeError, ValueError):
        plant_count = 0
    if plant_count < 1:
        missing.append("株数")
    if value.get("crop_category") == "fruit_tree" and value.get("tree_age_years") in (None, ""):
        missing.append("樹齢")
    if missing:
        raise PlantManagementValidationError(f"AI計画生成に必要な項目が不足しています: {', '.join(missing)}")


@app.route("/local/api/plantings/<planting_id>", methods=["PATCH"])
def update_planting_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        planting = plant_management_repository().update_planting(planting_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(planting)


@app.route("/local/api/plantings/<planting_id>/fertilizer-applications", methods=["GET"])
def list_fertilizer_applications_api(planting_id):
    repository = plant_management_repository()
    try:
        return jsonify(repository.fertilizer_effect_context(planting_id, as_of=request.args.get("as_of") or None))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except (PlantManagementValidationError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/local/api/fertilizer-materials", methods=["GET"])
def list_fertilizer_materials_api():
    return jsonify({"materials": plant_management_repository().list_fertilizer_materials()})


@app.route("/local/api/fertilizer-materials", methods=["POST"])
def create_fertilizer_material_api():
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        material = plant_management_repository().create_fertilizer_material(request_body)
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(material), 201


@app.route("/local/api/fertilizer-materials/<material_id>", methods=["PATCH"])
def update_fertilizer_material_api(material_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        material = plant_management_repository().update_fertilizer_material(material_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(material)


@app.route("/local/api/fertilizer-materials/<material_id>", methods=["DELETE"])
def delete_fertilizer_material_api(material_id):
    try:
        plant_management_repository().delete_fertilizer_material(material_id)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return "", 204


@app.route("/local/api/plantings/<planting_id>/fertilizer-applications", methods=["POST"])
def create_fertilizer_application_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repository = plant_management_repository()
    try:
        application = repository.create_fertilizer_application(planting_id, request_body)
        effect_context = repository.fertilizer_effect_context(planting_id)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"application": application, **effect_context}), 201


@app.route("/local/api/plantings/<planting_id>/fertilizer-applications/<application_id>", methods=["DELETE"])
def delete_fertilizer_application_api(planting_id, application_id):
    try:
        plant_management_repository().delete_fertilizer_application(planting_id, application_id)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    return "", 204


@app.route("/local/api/plantings/<planting_id>/calendar/regenerate", methods=["POST"])
def regenerate_plant_calendar_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    if planting is None:
        return jsonify({"error": "planting not found"}), 404
    field = field_repository().get(planting["field_id"])
    if field is None:
        return jsonify({"error": "field not found"}), 404
    layout = field_layout_repository().get(field["id"], field_name=field.get("name", ""))
    space = next((item for item in layout["spaces"] if item["id"] == planting["space_id"]), None)
    placement = next((item for item in (space or {}).get("placements", []) if item["id"] == planting["placement_id"]), None)
    if space is None or placement is None:
        return jsonify({"error": "planting placement was not found in the field layout"}), 400
    try:
        generation_task = plant_calendar_generation_task().enqueue(
            planting_id,
            kind="regenerate" if repository.get_calendar(planting_id) is not None else "initial",
            start_date=str(request_body.get("start_date") or date.today().isoformat()),
            planning_notes=str(request_body.get("planning_notes") or "")[:2000],
            audience=_current_plant_advice_profile(),
            mode=str(request_body.get("mode") or "automatic"),
        )
    except (PlantManagementNotFoundError, PlantManagementValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"planting": repository.get_planting(planting_id), "generation_task": generation_task}), 202


@app.route("/local/api/plantings/<planting_id>/calendar/regeneration-proposals/<task_id>/<proposal_id>", methods=["POST"])
def decide_plant_calendar_regeneration_proposal_api(planting_id, task_id, proposal_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    task = (
        next((item for item in repository.field_bundle(planting["field_id"]).get("generation_tasks", []) if item.get("id") == task_id), None)
        if planting
        else None
    )
    if task is None or task.get("planting_id") != planting_id:
        return jsonify({"error": "calendar generation task not found"}), 404
    try:
        result = repository.decide_calendar_generation_proposal(task_id, proposal_id, str(request_body.get("decision") or ""))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result)


@app.route("/local/api/plantings/<planting_id>/calendar/regeneration-proposals/<task_id>/decisions", methods=["POST"])
def decide_plant_calendar_regeneration_proposals_api(planting_id, task_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    task = (
        next((item for item in repository.field_bundle(planting["field_id"]).get("generation_tasks", []) if item.get("id") == task_id), None)
        if planting
        else None
    )
    if task is None or task.get("planting_id") != planting_id:
        return jsonify({"error": "calendar generation task not found"}), 404
    try:
        result = repository.decide_calendar_generation_proposals(task_id, request_body.get("decisions"))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    result["bundle"] = repository.field_bundle(planting["field_id"])
    user = current_user_from_request(request)
    result["bundle"]["viewer"] = {"email": user.email, "role": user.role}
    return jsonify(result)


@app.route("/local/api/plantings/<planting_id>/calendar/actions", methods=["POST"])
def add_plant_calendar_action_api(planting_id):
    request_body = _plant_action_request_body()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object or multipart payload"}), 400
    repository = plant_management_repository()
    user = current_user_from_request(request)
    if "assigned_to" in request_body and user.role != "admin":
        return jsonify({"error": "administrator role is required to assign work"}), 403
    try:
        planting = repository.get_planting(planting_id)
        if planting is None:
            raise PlantManagementNotFoundError("planting not found")
        repository.assert_calendar_mutation_unlocked(planting_id)
        request_body = _attach_plant_action_images(planting, request_body, request.files.getlist("images"))
        action = repository.add_action(planting_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except (PlantManagementValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(action), 201


@app.route("/local/api/plantings/<planting_id>/work-routes", methods=["GET", "POST"])
def plant_work_routes_api(planting_id):
    repository = plant_management_repository()
    if repository.get_planting(planting_id) is None:
        return jsonify({"error": "planting not found"}), 404
    if request.method == "GET":
        return jsonify({"items": repository.list_work_routes(planting_id)})
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        route = repository.create_work_route(planting_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(route), 201


@app.route("/local/api/plantings/<planting_id>/work-routes/<route_id>", methods=["PATCH", "DELETE"])
def plant_work_route_api(planting_id, route_id):
    repository = plant_management_repository()
    try:
        if request.method == "DELETE":
            repository.delete_work_route(planting_id, route_id)
            return "", 204
        request_body = request.get_json(silent=True)
        if not isinstance(request_body, dict):
            return jsonify({"error": "request body must be a JSON object"}), 400
        return jsonify(repository.update_work_route(planting_id, route_id, request_body))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/plantings/<planting_id>/work-routes/<route_id>/start", methods=["POST"])
def start_plant_work_route_api(planting_id, route_id):
    repository = plant_management_repository()
    try:
        return jsonify(repository.start_work_route(planting_id, route_id)), 201
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/plantings/<planting_id>/work-route-runs/<run_id>/steps/<step_id>/answer", methods=["POST"])
def answer_plant_work_route_step_api(planting_id, run_id, step_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repository = plant_management_repository()
    try:
        return jsonify(repository.answer_work_route_step(planting_id, run_id, step_id, request_body))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/plantings/<planting_id>/work-route-runs/<run_id>/rewind", methods=["POST"])
def rewind_plant_work_route_step_api(planting_id, run_id):
    repository = plant_management_repository()
    try:
        return jsonify(repository.rewind_work_route_step(planting_id, run_id))
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>", methods=["DELETE"])
def delete_plant_calendar_action_api(planting_id, action_id):
    repository = plant_management_repository()
    try:
        _assert_user_can_work_on_action(repository, planting_id, action_id, current_user_from_request(request))
        repository.delete_action(planting_id, action_id)
    except PlantActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return "", 204


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>", methods=["PATCH"])
def update_plant_calendar_action_api(planting_id, action_id):
    request_body = _plant_action_request_body()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object or multipart payload"}), 400
    use_as_guidance = bool(request_body.pop("use_as_guidance", False))
    repository = plant_management_repository()
    user = current_user_from_request(request)
    if "assigned_to" in request_body and user.role != "admin":
        return jsonify({"error": "administrator role is required to assign work"}), 403
    try:
        planting = repository.get_planting(planting_id)
        if planting is None:
            raise PlantManagementNotFoundError("planting not found")
        repository.assert_calendar_mutation_unlocked(planting_id)
        current_calendar = repository.get_calendar(planting_id) or {}
        current_action = next((item for item in current_calendar.get("actions") or [] if item.get("id") == action_id), {})
        if not current_action:
            raise PlantManagementNotFoundError("calendar action not found")
        PlantActionReviewService.assert_actor_can_work(current_action, actor_email=user.email, actor_role=user.role)
        request_body = _attach_plant_action_images(
            planting,
            request_body,
            request.files.getlist("images"),
            existing=current_action.get("attachments") or [],
        )
        action = repository.update_action(
            planting_id,
            action_id,
            request_body,
            use_as_guidance=use_as_guidance,
        )
    except PlantActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except (PlantManagementValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(action)


def _plant_action_request_body():
    if request.is_json:
        return request.get_json(silent=True)
    raw_payload = request.form.get("payload", "")
    try:
        value = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _plant_action_review_service():
    return PlantActionReviewService(
        plant_repository=plant_management_repository(),
        field_repository=field_repository(),
        media_service=field_record_media_service(),
        ai_content_service=ai_content_service(),
    )


def _assert_user_can_work_on_action(repository, planting_id: str, action_id: str, user):
    planting = repository.get_planting(planting_id)
    if planting is None:
        raise PlantManagementNotFoundError("planting not found")
    calendar = repository.get_calendar(planting_id) or {}
    action = next((item for item in calendar.get("actions", []) if item.get("id") == action_id), None)
    if action is None:
        raise PlantManagementNotFoundError("calendar action not found")
    PlantActionReviewService.assert_actor_can_work(action, actor_email=user.email, actor_role=user.role)
    return action


def _attach_plant_action_images(planting, value, files, *, existing=None):
    uploads = field_record_media_service().upload_images(
        planting["field_id"],
        str(value.get("window_start") or date.today().isoformat()),
        files,
    )
    if not uploads:
        return value
    html = str(value.get("instructions_html") or "")[:12000]
    for index, attachment in enumerate(uploads):
        marker = f"{{{{image:{index}}}}}"
        image_html = (
            f'<figure><img src="{escape(attachment["url"], quote=True)}" '
            f'alt="{escape(attachment.get("original_filename") or "作業画像", quote=True)}" loading="lazy"></figure>'
        )
        html = html.replace(marker, image_html)
        if marker not in str(value.get("instructions_html") or ""):
            html += image_html
    return {**value, "instructions_html": html, "attachments": [*(existing or []), *uploads][-5:]}


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>/skip", methods=["POST"])
def skip_plant_calendar_action_api(planting_id, action_id):
    request_body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be an object"}), 400
    repository = plant_management_repository()
    service = PlantActionDecisionService(
        plant_repository=repository,
        field_repository=field_repository(),
        media_service=field_record_media_service(),
    )
    try:
        repository.assert_calendar_mutation_unlocked(planting_id)
        user = current_user_from_request(request)
        _assert_user_can_work_on_action(repository, planting_id, action_id, user)
        result = service.skip_action(
            planting_id,
            action_id,
            request_body,
            request.files.getlist("images"),
            decided_by=user.email,
        )
    except PlantActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except (PlantManagementValidationError, FieldValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result), 201


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>/complete", methods=["POST"])
def complete_plant_calendar_action_api(planting_id, action_id):
    request_body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be an object"}), 400
    user = current_user_from_request(request)
    try:
        result = _plant_action_review_service().submit_completion(
            planting_id,
            action_id,
            request_body,
            request.files.getlist("images"),
            actor_email=user.email,
            actor_role=user.role,
        )
    except PlantActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except (PlantManagementValidationError, FieldValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({**result["work_log"], "action": result["action"]}), 201


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>/review", methods=["POST"])
def review_plant_calendar_action_api(planting_id, action_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    user = current_user_from_request(request)
    try:
        result = _plant_action_review_service().review_completion(
            planting_id,
            action_id,
            request_body,
            reviewer_email=user.email,
            reviewer_role=user.role,
            audience=_current_plant_advice_profile(),
        )
    except PlantActionAuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except (PlantManagementValidationError, FieldValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result), 200


@app.route("/local/api/plantings/<planting_id>/questions", methods=["GET", "POST"])
def ask_plant_question_api(planting_id):
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    if planting is None:
        return jsonify({"error": "planting not found"}), 404
    if request.method == "GET":
        try:
            return jsonify(
                repository.list_questions(
                    planting_id,
                    query=request.args.get("q", ""),
                    page=request.args.get("page", 1),
                    page_size=request.args.get("page_size", 50),
                )
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    question = str(request_body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    allowed, code, message = validate_plant_question(question, planting)
    if not allowed:
        return jsonify({"error": message, "code": code, "saved": False}), 422
    calendar = repository.get_calendar(planting_id)
    field = field_repository().get(planting["field_id"])
    context = {
        "field": field or {},
        "planting": planting,
        "calendar": calendar or {},
        "suggestions": repository.list_suggestions(planting["field_id"]),
        "fertilizer_history": repository.fertilizer_effect_context(planting_id),
        "recent_questions": repository.list_questions(planting_id, page_size=12)["items"],
    }
    answer = ai_content_service().answer_plant_question(context, question)
    try:
        record = repository.record_question(planting_id, question, answer)
    except (PlantManagementNotFoundError, PlantManagementValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(record), 201


@app.route("/fields/<field_id>/notes", methods=["POST"])
def add_field_note(field_id):
    try:
        field_repository().add_note(
            field_id,
            {
                "category": request.form.get("category", "observation"),
                "text": request.form.get("text", ""),
                "human_evaluation": request.form.get("human_evaluation", ""),
                "rating": _record_rating(request.form.get("rating")),
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}#records")


@app.route("/fields/<field_id>/events", methods=["POST"])
def add_field_event(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    try:
        occurred_at = request.form.get("occurred_at", "")
        rating = _record_rating(request.form.get("rating"))
        attachments = field_record_media_service().upload_images(field_id, occurred_at, request.files.getlist("images"))
        record_values = _field_record_values_from_form(request.form)
        target_placement_id = request.form.get("target_placement_id", "").strip()
        target_name = _field_record_target_name(field_id, target_placement_id)
        tags = [tag.strip() for value in request.form.getlist("tags") for tag in _split_lines_or_commas(value) if tag.strip()]
        if request.form.get("event_type") == "daily_record" and not any(
            (record_values, tags, request.form.get("description", "").strip(), rating, attachments)
        ):
            raise FieldValidationError("記録項目、タグ、メモ、評価、画像のいずれかを入力してください")
        field_repository().add_event(
            field_id,
            {
                "event_type": request.form.get("event_type", "observation"),
                "occurred_at": occurred_at,
                "title": request.form.get("title", "") or _field_record_title(record_values, target_name),
                "description": request.form.get("description", ""),
                "target_placement_id": target_placement_id,
                "target_name": target_name,
                "record_values": record_values,
                "amount": request.form.get("amount", ""),
                "unit": request.form.get("unit", ""),
                "device_id": request.form.get("device_id", ""),
                "human_evaluation": request.form.get("human_evaluation", ""),
                "rating": rating,
                "attachments": attachments,
                "tags": tags,
            },
        )
    except (FieldValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return redirect(f"/fields/{field_id}#records")


@app.route("/local/api/fields/<field_id>/record-images/<attachment_id>", methods=["GET"])
def get_field_record_image_api(field_id, attachment_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    attachment = _find_field_record_attachment(field, attachment_id)
    if attachment is None:
        plant_bundle = plant_management_repository().field_bundle(field_id)
        attachment = _find_attachment_in_records(plant_bundle.get("work_logs") or [], attachment_id)
        if attachment is None:
            calendar_actions = [action for calendar in (plant_bundle.get("calendars") or {}).values() for action in calendar.get("actions") or []]
            attachment = _find_attachment_in_records(calendar_actions, attachment_id)
    if attachment is None:
        return jsonify({"error": "record image not found"}), 404
    try:
        image_bytes = field_record_media_service().fetch_image(attachment)
    except FieldRecordMediaValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return Response(
        image_bytes,
        mimetype=attachment.get("content_type") or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@app.route("/fields/<field_id>/action-plans", methods=["POST"])
def add_field_action_plan(field_id):
    try:
        field_repository().add_action_plan(
            field_id,
            {
                "action_type": request.form.get("action_type", "observation"),
                "status": request.form.get("status", "proposed"),
                "target_device_id": request.form.get("target_device_id", ""),
                "title": request.form.get("title", ""),
                "scientific_reason": request.form.get("scientific_reason", ""),
                "preconditions": _json_form_payload("preconditions_json"),
                "expected_effect": request.form.get("expected_effect", ""),
                "risk": request.form.get("risk", ""),
                "control_payload": _json_form_payload("control_payload_json"),
                "source": request.form.get("source", "human"),
                "human_evaluation": request.form.get("human_evaluation", ""),
                "rating": _record_rating(request.form.get("rating")),
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}#records")


@app.route("/fields/<field_id>/reflections", methods=["POST"])
def add_field_reflection(field_id):
    repo = field_repository()
    field = repo.get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    context = _build_field_context(field)
    human_evaluation = request.form.get("human_evaluation", "")
    llm_reflection = ai_content_service().generate_field_reflection(context, human_evaluation=human_evaluation)
    try:
        repo.add_reflection(
            field_id,
            {
                "period_start": request.form.get("period_start", ""),
                "period_end": request.form.get("period_end", ""),
                "human_evaluation": human_evaluation,
                "llm_reflection": llm_reflection,
                "context_snapshot": context,
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}#records")


@app.route("/local/api/fields", methods=["GET"])
def list_fields_api():
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = int(request.args.get("page_size", "50"))
    except (TypeError, ValueError):
        return jsonify({"error": "page and page_size must be integers"}), 400
    prefecture = request.args.get("prefecture", "").strip()
    environment_type = request.args.get("environment_type", "").strip()
    if prefecture and prefecture not in JAPAN_PREFECTURES:
        return jsonify({"error": "unsupported prefecture"}), 400
    if environment_type and environment_type not in FIELD_ENVIRONMENT_TYPE_LABELS:
        return jsonify({"error": "unsupported environment_type"}), 400
    return jsonify(
        field_repository().search(
            query=request.args.get("q", ""),
            prefecture=prefecture,
            environment_type=environment_type,
            page=page,
            page_size=page_size,
        )
    )


@app.route("/local/api/fields/<field_id>/records", methods=["GET"])
def search_field_records_api(field_id):
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    try:
        result = field_repository().search_records(
            field_id,
            query=request.args.get("q", ""),
            kinds=_query_list("kind"),
            target=request.args.get("target", ""),
            date_from=request.args.get("date_from", ""),
            date_to=request.args.get("date_to", ""),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 20),
        )
    except (FieldValidationError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    result["items"] = [_field_record_search_view(item) for item in result["items"]]
    return jsonify(result)


@app.route("/local/api/fields/<field_id>", methods=["GET"])
def get_field_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    return jsonify({"field": field, "context": _build_field_context(field, compare_date=request.args.get("compare_date", ""))})


@app.route("/local/api/fields", methods=["POST"])
def create_field_api():
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        field = field_repository().upsert(None, request_body)
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(field), 201


@app.route("/local/api/fields/<field_id>", methods=["PUT"])
def update_field_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        field = field_repository().upsert(field_id, request_body)
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(field)


@app.route("/local/api/fields/<field_id>/weather-location", methods=["GET", "PATCH"])
def field_weather_location_api(field_id):
    repo = field_repository()
    field = repo.get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    if request.method == "GET":
        return jsonify({"field_id": field_id, "weather_location": field.get("weather_location")})
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        field = repo.upsert(field_id, {"weather_location": request_body})
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"field_id": field_id, "weather_location": field["weather_location"]})


@app.route("/local/api/fields/<field_id>/weather/observations", methods=["GET"])
def field_weather_observations_api(field_id):
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    records = weather_record_repository().list_records(
        field_id=field_id,
        record_type="observation",
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        limit=request.args.get("limit", 1000),
    )
    return jsonify({"field_id": field_id, "records": records})


@app.route("/local/api/fields/<field_id>/weather/forecasts", methods=["GET"])
def field_weather_forecasts_api(field_id):
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    records = weather_record_repository().list_records(
        field_id=field_id,
        record_type="forecast",
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        limit=request.args.get("limit", 1000),
    )
    return jsonify({"field_id": field_id, "records": records})


def _field_research_dataset(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return None
    records = weather_record_repository().list_records(
        field_id=field_id,
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        limit=10000,
    )
    return build_research_dataset(
        field,
        records,
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
    )


@app.route("/local/api/fields/<field_id>/research/dataset", methods=["GET"])
def field_research_dataset_api(field_id):
    dataset = _field_research_dataset(field_id)
    if dataset is None:
        return jsonify({"error": "field not found"}), 404
    return jsonify(dataset)


@app.route("/local/api/fields/<field_id>/research/analyses", methods=["POST"])
def field_research_analysis_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    dataset = _field_research_dataset(field_id)
    if dataset is None:
        return jsonify({"error": "field not found"}), 404
    try:
        analysis = analyze_correlation(
            dataset,
            str(request_body.get("x_metric") or ""),
            str(request_body.get("y_metric") or ""),
            method=str(request_body.get("method") or "pearson"),
            lag_days=request_body.get("lag_days", 0),
        )
        saved = cultivation_research_repository().add_analysis(field_id, analysis)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(saved), 201


@app.route("/local/api/fields/<field_id>/research/hypotheses", methods=["GET", "POST"])
def field_research_hypotheses_api(field_id):
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    repo = cultivation_research_repository()
    if request.method == "GET":
        return jsonify({"field_id": field_id, "hypotheses": repo.list_hypotheses(field_id)})
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        hypothesis = repo.add_hypothesis(field_id, request_body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(hypothesis), 201


@app.route("/local/api/fields/<field_id>/research/hypotheses/<hypothesis_id>", methods=["PATCH"])
def field_research_hypothesis_api(field_id, hypothesis_id):
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        hypothesis = cultivation_research_repository().update_hypothesis(field_id, hypothesis_id, request_body)
    except KeyError:
        return jsonify({"error": "hypothesis not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(hypothesis)


@app.route("/local/api/fields/<field_id>/research/export.csv", methods=["GET"])
def field_research_export_api(field_id):
    dataset = _field_research_dataset(field_id)
    if dataset is None:
        return jsonify({"error": "field not found"}), 404
    metric_names = sorted(
        {f"weather.{key}" for row in dataset["rows"] for key in row["weather"]}
        | {f"field_records.{key}" for row in dataset["rows"] for key in row["field_records"]}
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", *metric_names])
    for row in dataset["rows"]:
        writer.writerow(
            [
                row["date"],
                *[(row["weather"].get(name[8:]) if name.startswith("weather.") else row["field_records"].get(name[14:])) for name in metric_names],
            ]
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="field-{field_id}-research.csv"'},
    )


@app.route("/local/api/fields/<field_id>/notes", methods=["POST"])
def add_field_note_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        note = field_repository().add_note(field_id, request_body)
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(note), 201


@app.route("/local/api/fields/<field_id>/events", methods=["POST"])
def add_field_event_api(field_id):
    request_body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be an object"}), 400
    if field_repository().get(field_id) is None:
        return jsonify({"error": "field not found"}), 404
    try:
        if not request.is_json:
            request_body["record_values"] = _field_record_values_from_form(request.form)
        target_placement_id = str(request_body.get("target_placement_id") or "").strip()
        request_body["target_placement_id"] = target_placement_id
        request_body["target_name"] = _field_record_target_name(field_id, target_placement_id)
        if not request_body.get("title") and request_body.get("event_type") == "daily_record":
            request_body["title"] = _field_record_title(request_body.get("record_values") or [], request_body["target_name"])
        request_body.pop("attachments", None)
        request_body.pop("source_work_log_id", None)
        request_body["rating"] = _record_rating(request_body.get("rating"))
        request_body["attachments"] = field_record_media_service().upload_images(
            field_id,
            request_body.get("occurred_at", ""),
            request.files.getlist("images"),
        )
        if request_body.get("event_type") == "daily_record" and not any(
            (
                request_body.get("record_values"),
                str(request_body.get("description") or "").strip(),
                request_body.get("rating"),
                request_body.get("attachments"),
            )
        ):
            raise FieldValidationError("記録項目、メモ、評価、画像のいずれかを入力してください")
        event = field_repository().add_event(field_id, request_body)
    except (FieldValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(event), 201


@app.route("/local/api/fields/<field_id>/action-plans", methods=["POST"])
def add_field_action_plan_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        plan = field_repository().add_action_plan(field_id, request_body)
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(plan), 201


@app.route("/local/api/fields/<field_id>/reflections", methods=["POST"])
def add_field_reflection_api(field_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    repo = field_repository()
    field = repo.get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    context = _build_field_context(field)
    human_evaluation = request_body.get("human_evaluation", "")
    llm_reflection = request_body.get("llm_reflection") or ai_content_service().generate_field_reflection(context, human_evaluation=human_evaluation)
    try:
        reflection = repo.add_reflection(
            field_id,
            {
                "period_start": request_body.get("period_start", ""),
                "period_end": request_body.get("period_end", ""),
                "human_evaluation": human_evaluation,
                "llm_reflection": llm_reflection,
                "context_snapshot": context,
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(reflection), 201


def _split_lines_or_commas(value: str):
    parts = []
    for line in (value or "").replace(",", "\n").splitlines():
        item = line.strip()
        if item and item not in parts:
            parts.append(item)
    return parts


def _field_create_form_data(form):
    location = {
        "prefecture": form.get("prefecture", "").strip(),
        "municipality": form.get("municipality", "").strip(),
        "locality": form.get("locality", "").strip(),
        "environment_type": form.get("environment_type", "").strip(),
    }
    if location["prefecture"] not in JAPAN_PREFECTURES:
        raise FieldValidationError("prefecture is required")
    if not location["municipality"]:
        raise FieldValidationError("municipality is required")
    if location["environment_type"] not in FIELD_ENVIRONMENT_TYPE_LABELS:
        raise FieldValidationError("environment_type is required")
    return {
        "name": form.get("name", ""),
        "location": location,
    }


def _field_form_data(form):
    return {
        "name": form.get("name", ""),
        "location": {
            "prefecture": form.get("prefecture", ""),
            "municipality": form.get("municipality", ""),
            "locality": form.get("locality", ""),
            "environment_type": form.get("environment_type", ""),
        },
        "crop": form.get("crop", ""),
        "stage": form.get("stage", ""),
        "memo": form.get("memo", ""),
        "device_ids": _split_lines_or_commas(form.get("device_ids", "")),
        "camera_device_ids": _split_lines_or_commas(form.get("camera_device_ids", "")),
        "areas": _parse_field_areas_text(form.get("areas_text", "")),
        "device_placements": _parse_device_placements_form(form),
        "crop_profile": {
            "crop_name": form.get("crop", ""),
            "cultivar": form.get("cultivar", ""),
            "growth_stage": form.get("stage", ""),
            "seeding_date": form.get("seeding_date", ""),
            "transplant_date": form.get("transplant_date", ""),
            "target_harvest_date": form.get("target_harvest_date", ""),
        },
        "growth_targets": {
            "air_temperature_c": _field_range_from_form(form, "target_air_temperature"),
            "air_humidity_percent": _field_range_from_form(form, "target_air_humidity"),
            "soil_moisture_percent": _field_range_from_form(form, "target_soil_moisture"),
            "soil_temperature_c": _field_range_from_form(form, "target_soil_temperature"),
            "soil_ec_us_cm": _field_range_from_form(form, "target_soil_ec"),
            "soil_ph": _field_range_from_form(form, "target_soil_ph"),
            "par_umol_m2_s": _field_range_from_form(form, "target_par"),
        },
        "cultivation_context": {
            "cultivation_method": form.get("cultivation_method", ""),
            "soil_type": form.get("soil_type", ""),
            "substrate": form.get("substrate", ""),
            "greenhouse_type": form.get("greenhouse_type", ""),
            "mulching": form.get("mulching", ""),
            "irrigation_method": form.get("irrigation_method", ""),
            "water_source": form.get("water_source", ""),
            "bed_area_m2": form.get("bed_area_m2", ""),
            "plant_count": form.get("plant_count", ""),
            "notes": form.get("cultivation_notes", ""),
        },
        "control_policy": {
            "objective": form.get("objective", ""),
            "autonomy_level": form.get("autonomy_level", "suggest_only"),
            "allowed_actions": form.getlist("allowed_actions") or ["watering"],
            "max_watering_sec_per_day": form.get("max_watering_sec_per_day", ""),
            "min_watering_interval_min": form.get("min_watering_interval_min", ""),
            "safety_notes": form.get("safety_notes", ""),
        },
        "knowledge_context": {
            "research_queries": _split_lines_or_commas(form.get("research_queries", "")),
            "external_reference_urls": _split_lines_or_commas(form.get("external_reference_urls", "")),
            "image_observation_prompt": form.get("image_observation_prompt", ""),
            "notes": form.get("knowledge_notes", ""),
        },
    }


def _field_crop_suggestions(fields):
    values = set(FIELD_CROP_CULTIVAR_SUGGESTIONS)
    values.update(field.get("crop", "") for field in fields)
    return sorted(value for value in values if value)


def _field_cultivar_suggestions(fields):
    values = {cultivar for cultivars in FIELD_CROP_CULTIVAR_SUGGESTIONS.values() for cultivar in cultivars}
    values.update((field.get("crop_profile") or {}).get("cultivar", "") for field in fields)
    return sorted(value for value in values if value)


def _parse_field_areas_text(value: str):
    areas = []
    for line in (value or "").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split(",", 3)]
        name = parts[0] if parts else ""
        area_type = _area_type_from_text(parts[1] if len(parts) > 1 else "")
        crop_name = parts[2] if len(parts) > 2 else ""
        memo = parts[3] if len(parts) > 3 else ""
        if name:
            areas.append({"name": name, "area_type": area_type, "crop_name": crop_name, "memo": memo})
    return areas


def _area_type_from_text(value: str):
    aliases = {
        "": "section",
        "区画": "section",
        "section": "section",
        "ベッド": "bed",
        "bed": "bed",
        "畝": "ridge",
        "ridge": "ridge",
        "ゾーン": "zone",
        "zone": "zone",
        "測点": "point",
        "point": "point",
        "その他": "other",
        "other": "other",
    }
    return aliases.get((value or "").strip(), "section")


def _parse_device_placements_form(form):
    placements = []
    indexes = sorted(
        {key.rsplit("_", 1)[-1] for key in form.keys() if key.startswith("placement_device_id_") and key.rsplit("_", 1)[-1].isdigit()},
        key=int,
    )
    for index in indexes:
        device_id = form.get(f"placement_device_id_{index}", "")
        if not device_id:
            continue
        placements.append(
            {
                "device_id": device_id,
                "device_role": form.get(f"placement_device_role_{index}", "sensor"),
                "scope_type": form.get(f"placement_scope_type_{index}", "field"),
                "area_id": form.get(f"placement_area_id_{index}", ""),
                "crop_name": form.get(f"placement_crop_name_{index}", ""),
                "memo": form.get(f"placement_memo_{index}", ""),
            }
        )
    return placements


def _field_areas_text(areas):
    lines = []
    for area in areas or []:
        lines.append(
            ",".join(
                [
                    area.get("name") or "",
                    area.get("area_type") or "section",
                    area.get("crop_name") or "",
                    area.get("memo") or "",
                ]
            )
        )
    return "\n".join(lines)


def _field_range_from_form(form, prefix: str):
    return {"min": form.get(f"{prefix}_min", ""), "max": form.get(f"{prefix}_max", "")}


def _json_form_payload(name: str):
    raw_value = request.form.get(name, "")
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _record_rating(value):
    if value in (None, ""):
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError) as exc:
        raise FieldValidationError("rating must be between 1 and 5") from exc
    if rating not in {1, 2, 3, 4, 5}:
        raise FieldValidationError("rating must be between 1 and 5")
    return rating


def _field_record_values_from_form(form):
    keys = form.getlist("record_item_key")
    values = form.getlist("record_item_value")
    if len(keys) != len(values):
        raise FieldValidationError("記録項目を読み取れませんでした")
    return [{"key": key, "value": value} for key, value in zip(keys, values) if key and value not in (None, "")]


def _field_record_title(record_values, target_name=""):
    summaries = []
    for value in record_values[:2]:
        definition = FIELD_RECORD_CATALOG_BY_KEY.get(value.get("key")) if isinstance(value, dict) else None
        if definition is None or value.get("value") in (None, ""):
            continue
        summaries.append(f"{definition['label']} {value['value']}{definition['unit']}")
    title = "、".join(summaries) or "圃場記録"
    if target_name and target_name != "圃場全体":
        return f"{target_name}: {title}"
    return title


def _field_record_values_summary(record_values):
    parts = []
    for value in record_values or []:
        if not isinstance(value, dict) or value.get("value") in (None, ""):
            continue
        parts.append(f"{value.get('label') or value.get('key')} {value['value']}{value.get('unit') or ''}")
    return " / ".join(parts)


def _field_record_target_name(field_id: str, target_placement_id: str):
    if not target_placement_id:
        return "圃場全体"
    field = field_repository().get(field_id)
    if field is None:
        raise FieldValidationError("field not found")
    layout = field_layout_repository().get(field_id, field_name=field.get("name", ""))
    target = next((item for item in _build_field_record_targets(layout) if item["id"] == target_placement_id), None)
    if target is None:
        raise FieldValidationError("記録対象が圃場にありません")
    return target["label"]


def _find_attachment_in_records(records: list, attachment_id: str):
    for record in records:
        for attachment in record.get("attachments") or []:
            if attachment.get("id") == attachment_id:
                return attachment
    return None


def _find_field_record_attachment(field: dict, attachment_id: str):
    for record_type in ("events", "notes", "action_plans"):
        attachment = _find_attachment_in_records(field.get(record_type) or [], attachment_id)
        if attachment is not None:
            return attachment
    return None


def _build_field_list_item(field: dict):
    item = dict(field)
    layout = field_layout_repository().get(field["id"], field_name=field.get("name", ""))
    plant_bundle = plant_management_repository().field_bundle(field["id"])
    active_plantings = [planting for planting in plant_bundle["plantings"] if planting.get("status") == "active"]
    placements = [placement for space in layout.get("spaces", []) for placement in space.get("placements", [])]
    crop_labels = []
    for planting in active_plantings:
        label = " / ".join(value for value in (planting.get("crop_name"), planting.get("cultivar")) if value)
        if label and label not in crop_labels:
            crop_labels.append(label)
    events = field.get("events") or []
    event_work_log_ids = {event.get("source_work_log_id") for event in events if event.get("source_work_log_id")}
    approved_unlinked_work_logs = [
        work_log
        for work_log in plant_bundle.get("work_logs") or []
        if work_log.get("review_status", "approved") == "approved" and work_log.get("id") not in event_work_log_ids
    ]
    item["list_summary"] = {
        "crop_labels": crop_labels,
        "placement_count": len(placements),
        "planting_count": len(active_plantings),
        "device_count": len({(placement.get("binding") or {}).get("device_id") for placement in placements} - {None, ""}),
        "record_count": len(events) + len(approved_unlinked_work_logs),
    }
    return item


def _build_field_context(  # noqa: PLR0915
    field: dict,
    compare_date: str = "",
    record_month: str = "",
    *,
    include_automatic_measurements: bool = True,
):
    compare_day = _field_compare_day(compare_date)
    layout = field_layout_repository().get(field["id"], field_name=field.get("name", ""))
    device_records = _field_device_records(field, layout)
    plant_bundle = plant_management_repository().field_bundle(field["id"])
    active_plantings = [planting for planting in plant_bundle["plantings"] if planting.get("status") == "active"]
    placement_rows = _layout_device_placement_rows(layout, device_records)
    if placement_rows:
        device_ids = list(dict.fromkeys(row["device_id"] for row in placement_rows if row["device_role"] != "camera"))
        camera_ids = list(dict.fromkeys(row["device_id"] for row in placement_rows if row["device_role"] == "camera"))
    else:
        device_ids = field.get("device_ids") or []
        camera_ids = field.get("camera_device_ids") or []
        placement_rows = _legacy_root_device_placement_rows(field, device_records)
    devices = []
    latest_sensor_values = []
    recent_status_events = []
    recent_images = []
    statuses_for_chart = []

    for device_id in device_ids:
        record = device_records.get(device_id)
        placement = _device_placement_for(placement_rows, device_id)
        devices.append({"device_id": device_id, "record": _compact_device_record(record), "placement": placement})
        latest = _field_latest_sensor_value(device_id, record, placement)
        if latest:
            latest_sensor_values.append(latest)
        device_statuses = (record or {}).get("status_history", [])
        statuses_for_chart.extend(device_statuses[-240:])
        for status in device_statuses[-24:]:
            recent_status_events.append(_field_status_event(device_id, status))
        recent_images.extend(_field_sensor_images(device_id, limit=2))

    for camera_id in camera_ids:
        recent_images.extend(_field_camera_images(camera_id, limit=2))

    image_compare_groups = _field_image_compare_groups(camera_ids, compare_day)
    active_measurement_devices = {device_id: device_records[device_id] for device_id in device_ids if device_id in device_records}
    automatic_record_measurements = (
        _field_automatic_record_measurements(active_measurement_devices, placement_rows, record_month) if include_automatic_measurements else []
    )
    active_plantings = _build_active_planting_views(active_plantings, plant_bundle, automatic_record_measurements, layout)

    recent_status_events = sorted(recent_status_events, key=lambda item: item.get("received_at") or "", reverse=True)[:40]
    field_events = sorted(list(field.get("events") or []), key=lambda item: item.get("occurred_at") or item.get("created_at") or "", reverse=True)
    record_search_page = field_repository().search_records(field["id"], page=1, page_size=20)
    timeline = [_field_record_search_view(item) for item in record_search_page["items"]]
    growth_targets = _active_planting_growth_targets(active_plantings)
    field_snapshot = {
        key: field.get(key)
        for key in (
            "id",
            "name",
            "crop",
            "stage",
            "memo",
            "crop_profile",
            "growth_targets",
            "cultivation_context",
            "control_policy",
            "knowledge_context",
            "areas",
            "device_placements",
        )
    }
    field_snapshot["growth_targets"] = growth_targets
    field_snapshot["areas"] = []
    field_snapshot["device_placements"] = placement_rows
    field_snapshot["crop"] = ""
    field_snapshot["stage"] = ""
    field_snapshot["crop_profile"] = {}
    if active_plantings:
        primary_planting = active_plantings[0]
        field_snapshot["crop"] = primary_planting.get("crop_name", "")
        field_snapshot["stage"] = "栽培中"
        field_snapshot["crop_profile"] = {
            "crop_name": primary_planting.get("crop_name", ""),
            "cultivar": primary_planting.get("cultivar", ""),
            "growth_stage": "栽培中",
        }
    context = {
        "generated_at": datetime.now(UTC).isoformat(),
        "field": field_snapshot,
        "devices": devices,
        "latest_sensor_values": latest_sensor_values,
        "recent_status_events": recent_status_events,
        "recent_field_events": field_events[:40],
        "recent_action_plans": list(field.get("action_plans") or [])[-20:],
        "device_placement_rows": placement_rows,
        "timeline": timeline,
        "record_search_total": record_search_page["total"],
        "record_search_has_next": record_search_page["has_next"],
        "record_tags": sorted(
            {tag for record in [*(field.get("events") or []), *(field.get("notes") or [])] for tag in record.get("tags") or []}, key=str.casefold
        ),
        "recent_notes": list(field.get("notes") or [])[-20:],
        "recent_images": recent_images[:12],
        "camera_views": _build_field_camera_views(camera_ids, placement_rows),
        "compare_date": compare_day.strftime("%Y-%m-%d"),
        "image_compare": recent_images[:2],
        "image_compare_groups": image_compare_groups,
        "soil_moisture_chart": (
            _build_field_soil_moisture_chart(statuses_for_chart, field_events, include_plotlyjs=False, deferred=True) if statuses_for_chart else ""
        ),
        "watering_chart": (_build_watering_trend_chart(statuses_for_chart, include_plotlyjs=False, deferred=True) if statuses_for_chart else ""),
        "monitoring_scopes": _build_monitoring_scopes(placement_rows, latest_sensor_values),
        "post_watering_notifications": _build_field_post_watering_notification_context(field["id"], device_records, placement_rows),
        "layout": layout,
        "layout_preview": _build_layout_preview(layout, active_plantings, field_id=field["id"]),
        "installation_tree": _build_installation_tree(layout, device_records, active_plantings, field_id=field["id"]),
        "plant_bundle": plant_bundle,
        "active_plantings": active_plantings,
        "record_calendar": _build_field_record_calendar(field, plant_bundle, record_month, automatic_record_measurements),
        "record_catalog": [dict(item) for item in FIELD_RECORD_CATALOG],
        "record_categories": FIELD_RECORD_CATEGORIES,
        "recent_record_items": selected_record_catalog(field.get("events") or []),
        "record_targets": _build_field_record_targets(layout),
        "has_field_devices": bool(device_records),
    }
    dashboard_field = {**field, "growth_targets": growth_targets}
    context["dashboard"] = _build_field_status_dashboard(
        dashboard_field,
        latest_sensor_values,
        active_plantings=active_plantings,
    )
    context["action_candidates"] = build_action_candidates(context)
    context["calendar_todo_items"] = _build_calendar_todo_items(field["id"], plant_bundle)
    context["todo_count"] = len(context["calendar_todo_items"]) + len(context["action_candidates"])
    return context


def _build_field_deferred_context(field: dict, primary_context: dict, record_month: str = ""):
    layout = primary_context["layout"]
    placement_rows = primary_context["device_placement_rows"]
    plant_bundle = primary_context["plant_bundle"]
    device_records = _field_device_records(field, layout)
    active_measurement_devices = {
        device_id: device_records[device_id]
        for device_id in {row.get("device_id") for row in placement_rows if row.get("device_role") != "camera"} - {None, ""}
        if device_id in device_records
    }
    automatic_measurements = _field_automatic_record_measurements(active_measurement_devices, placement_rows, record_month)
    active_plantings = [planting for planting in plant_bundle["plantings"] if planting.get("status") == "active"]
    return {
        "active_plantings": _build_active_planting_views(active_plantings, plant_bundle, automatic_measurements, layout),
        "record_calendar": _build_field_record_calendar(field, plant_bundle, record_month, automatic_measurements),
    }


def _field_device_records(field: dict, layout: dict):
    layout_device_ids = {(placement.get("binding") or {}).get("device_id") for space in layout.get("spaces", []) for placement in space.get("placements", [])}
    relevant_device_ids = layout_device_ids | set(field.get("device_ids") or []) | set(field.get("camera_device_ids") or [])
    config_service = device_config_service()
    records = {device_id: record for device_id in relevant_device_ids - {None, ""} if (record := config_service.find_record(device_id)) is not None}
    for device_id in relevant_device_ids - {None, ""} - set(records):
        camera = camera_management_service().get(device_id)
        if camera is not None:
            records[device_id] = {**camera, "device_kind": "CAM", "state": "active" if camera.get("credentials_configured") else "pending"}
    return records


def _active_planting_growth_targets(active_plantings):
    if len(active_plantings) != 1:
        return {}
    targets = active_plantings[0].get("growth_targets")
    return targets if isinstance(targets, dict) else {}


def _layout_device_placement_rows(layout: dict, device_records: dict):
    placement_names = {
        placement.get("id"): placement.get("name") or placement.get("id") for space in layout.get("spaces", []) for placement in space.get("placements", [])
    }
    rows = []
    for space in layout.get("spaces", []):
        scope_label = "圃場（屋外）" if space.get("id") == layout.get("root_space_id") else f"{space.get('name')}内"
        for placement in space.get("placements", []):
            binding = placement.get("binding") or {}
            device_id = binding.get("device_id")
            if not device_id:
                continue
            record = device_records.get(device_id)
            role = "camera" if binding.get("resource_type") == "camera" else _infer_device_role(record)
            target_ids = binding.get("target_placement_ids") or []
            rows.append(
                {
                    "device_id": device_id,
                    "device_name": (record or {}).get("name") or device_id,
                    "device_role": role,
                    "device_role_label": DEVICE_ROLE_LABELS.get(role, role),
                    "scope_type": "layout",
                    "scope_label": scope_label,
                    "space_id": space.get("id"),
                    "placement_id": placement.get("id"),
                    "placement_name": placement.get("name"),
                    "target_placement_ids": target_ids,
                    "target_labels": [placement_names[target_id] for target_id in target_ids if target_id in placement_names],
                    "resource_type": binding.get("resource_type") or "device",
                    "resource_id": binding.get("resource_id") or "",
                    "area": None,
                    "crop_name": "",
                    "memo": placement.get("memo") or "",
                }
            )
    return rows


def _build_installation_tree(layout: dict, device_records: dict, active_plantings: list, *, field_id=""):
    field_id = field_id or layout.get("field_id") or ""
    spaces = {space.get("id"): space for space in layout.get("spaces", []) if space.get("id")}
    root_space_id = layout.get("root_space_id")
    root = spaces.get(root_space_id)
    if root is None:
        return []

    placement_names = {
        placement.get("id"): placement.get("name") or placement.get("id") for space in spaces.values() for placement in space.get("placements", [])
    }
    crop_labels = {
        planting.get("placement_id"): " / ".join(value for value in (planting.get("crop_name"), planting.get("cultivar")) if value)
        for planting in active_plantings
        if planting.get("status") == "active"
    }
    rows = [
        {
            "id": root_space_id,
            "depth": 0,
            "kind": "field",
            "label": root.get("name") or layout.get("name") or "圃場全体",
            "detail": "圃場",
            "relation": "",
            "relation_kind": "",
            "href": f"/fields/{quote(str(field_id), safe='')}",
            "action_label": "圃場詳細を開く",
        }
    ]
    visited_spaces = {root_space_id}
    watering_sources_by_target = _watering_sources_by_target(spaces.values())

    def append_space(space_id: str, depth: int):
        space = spaces.get(space_id)
        if space is None:
            return
        placements = sorted(space.get("placements", []), key=lambda placement: (placement.get("z", 0), placement.get("name", "")))
        for placement in placements:
            preset = placement.get("preset") or ""
            binding = placement.get("binding") or {}
            child_space_id = placement.get("child_space_id") or ""
            if child_space_id:
                kind = "space"
            elif binding:
                kind = "device"
            elif preset in LAYOUT_CULTIVATION_PRESETS:
                kind = "cultivation"
            else:
                kind = "equipment"

            detail_parts = [LAYOUT_PLACEMENT_LABELS.get(preset, preset or "配置物")]
            crop_label = crop_labels.get(placement.get("id"))
            if crop_label:
                detail_parts.append(crop_label)
            device_id = binding.get("device_id") or ""
            is_camera = binding.get("resource_type") == "camera"
            if device_id:
                record = device_records.get(device_id) or {}
                detail_parts.append(record.get("name") or device_id)
            target_labels = [placement_names[target_id] for target_id in binding.get("target_placement_ids", []) if target_id in placement_names]
            watering_source_names = watering_sources_by_target.get(placement.get("id"), [])
            if preset in LAYOUT_CULTIVATION_PRESETS:
                relation = f"潅水: {'、'.join(watering_source_names)}" if watering_source_names else "手動潅水"
                relation_kind = "watering" if watering_source_names else "manual"
            elif is_camera:
                relation = f"監視: {'、'.join(target_labels)}" if target_labels else "監視エリア未設定"
                relation_kind = "target" if target_labels else "manual"
            else:
                relation = f"対象: {'、'.join(target_labels)}" if target_labels else ""
                relation_kind = "target" if target_labels else ""
            rows.append(
                {
                    "id": placement.get("id"),
                    "depth": depth,
                    "kind": kind,
                    "label": placement.get("name") or placement.get("id") or "配置物",
                    "detail": " / ".join(detail_parts),
                    "relation": relation,
                    "relation_kind": relation_kind,
                    "href": (
                        f"/camera/{quote(str(device_id), safe='')}"
                        if device_id and is_camera
                        else f"/mqtt-devices/{quote(str(device_id), safe='')}"
                        if device_id
                        else _layout_placement_url(field_id, space_id, placement.get("id"))
                    ),
                    "action_label": "カメラ映像を見る" if device_id and is_camera else "機器詳細を開く" if device_id else "配置詳細を開く",
                }
            )

            resource_type = binding.get("resource_type") or "device"
            if device_id and resource_type != "device" and not is_camera:
                resource_id = binding.get("resource_id") or ""
                rows.append(
                    {
                        "id": f"{placement.get('id')}-resource",
                        "depth": depth + 1,
                        "kind": "resource",
                        "label": _layout_resource_name(device_records.get(device_id), resource_type, resource_id),
                        "detail": f"{device_id} / {resource_type}",
                        "relation": "",
                        "relation_kind": "",
                        "href": f"/mqtt-devices/{quote(str(device_id), safe='')}?tab=settings",
                        "action_label": "機器の動作設定を開く",
                    }
                )

            if child_space_id and child_space_id not in visited_spaces:
                visited_spaces.add(child_space_id)
                append_space(child_space_id, depth + 1)

    append_space(root_space_id, 1)
    return rows


def _watering_sources_by_target(spaces):
    sources_by_target = {}
    watering_devices = (placement for space in spaces for placement in space.get("placements", []) if placement.get("preset") == "watering_device")
    for source in watering_devices:
        for target_id in (source.get("binding") or {}).get("target_placement_ids", []):
            sources_by_target.setdefault(target_id, []).append(source.get("name") or source.get("id"))
    return sources_by_target


def _layout_resource_name(record: dict | None, resource_type: str, resource_id: str):
    if resource_type == "mosfet_switch":
        config = record.get("config") if isinstance(record, dict) and isinstance(record.get("config"), dict) else {}
        for switch in config.get("mosfet_switches", []):
            if isinstance(switch, dict) and switch.get("switch_id") == resource_id:
                return switch.get("name") or resource_id or "機器出力"
        return resource_id or "機器出力"
    return {
        "sensor": "センサー機能",
        "camera": "カメラ機能",
    }.get(resource_type, resource_id or "デバイス機能")


def _legacy_root_device_placement_rows(field: dict, device_records: dict):
    rows = []
    seen = set()
    for device_id in field.get("device_ids") or []:
        role = _infer_device_role(device_records.get(device_id))
        row = _format_device_placement(device_id, role, None, [])
        row["scope_label"] = "圃場（屋外）"
        row["target_placement_ids"] = []
        row["target_labels"] = []
        rows.append(row)
        seen.add(device_id)
    for device_id in field.get("camera_device_ids") or []:
        if device_id in seen:
            continue
        row = _format_device_placement(device_id, "camera", None, [])
        row["scope_label"] = "圃場（屋外）"
        row["target_placement_ids"] = []
        row["target_labels"] = []
        rows.append(row)
    return rows


def _build_layout_preview(layout: dict, active_plantings: list, *, field_id=""):
    field_id = field_id or layout.get("field_id") or ""
    root = next((space for space in layout.get("spaces", []) if space.get("id") == layout.get("root_space_id")), None)
    if root is None:
        return {"columns": 1, "rows": 1, "placements": [], "updated_at": ""}
    crops_by_placement = {
        planting.get("placement_id"): " / ".join(value for value in (planting.get("crop_name"), planting.get("cultivar")) if value)
        for planting in active_plantings
    }
    child_crop_counts = {}
    for placement in root.get("placements", []):
        child_space_id = placement.get("child_space_id")
        if child_space_id:
            child_crop_counts[child_space_id] = sum(planting.get("space_id") == child_space_id for planting in active_plantings)
    columns = max(1, root.get("grid", {}).get("columns") or 1)
    rows = max(1, root.get("grid", {}).get("rows") or 1)
    preview_placements = []
    for placement in root.get("placements", []):
        crop_label = crops_by_placement.get(placement.get("id"), "")
        child_count = child_crop_counts.get(placement.get("child_space_id"), 0)
        preview_placements.append(
            {
                "id": placement.get("id"),
                "name": placement.get("name"),
                "preset": placement.get("preset"),
                "left": round(placement.get("x", 0) / columns * 100, 3),
                "top": round(placement.get("y", 0) / rows * 100, 3),
                "width": round(max(placement.get("width", 1) / columns * 100, 2.2), 3),
                "height": round(max(placement.get("height", 1) / rows * 100, 3.0), 3),
                "subtitle": crop_label or (f"栽培場所 {child_count}件" if child_count else ""),
                "bound": bool(placement.get("binding")),
                "href": (
                    f"/camera/{quote(str((placement.get('binding') or {}).get('device_id')), safe='')}"
                    if (placement.get("binding") or {}).get("device_id") and (placement.get("binding") or {}).get("resource_type") == "camera"
                    else f"/mqtt-devices/{quote(str((placement.get('binding') or {}).get('device_id')), safe='')}"
                    if (placement.get("binding") or {}).get("device_id")
                    else _layout_placement_url(field_id, root.get("id"), placement.get("id"))
                ),
            }
        )
    return {
        "columns": columns,
        "rows": rows,
        "placements": preview_placements,
        "updated_at": layout.get("updated_at") or "",
    }


def _build_field_record_targets(layout: dict):
    targets = [{"id": "", "label": "圃場全体", "preset": "field"}]
    root_space_id = layout.get("root_space_id")
    seen = set()
    for space in layout.get("spaces") or []:
        space_name = str(space.get("name") or "").strip()
        for placement in space.get("placements") or []:
            placement_id = str(placement.get("id") or "").strip()
            preset = placement.get("preset")
            if not placement_id or placement_id in seen or preset not in LAYOUT_CULTIVATION_PRESETS:
                continue
            placement_name = str(placement.get("name") or LAYOUT_PLACEMENT_LABELS.get(preset) or "栽培場所").strip()
            label = placement_name if space.get("id") == root_space_id or not space_name else f"{space_name} / {placement_name}"
            targets.append({"id": placement_id, "label": label, "preset": preset})
            seen.add(placement_id)
    return targets


def _field_automatic_record_measurements(device_records: dict, placement_rows: list, month_value: str):
    if not device_records:
        return []
    month_start = _record_month_start(month_value)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    timezone = _local_timezone()
    range_start = datetime(month_start.year, month_start.month, 1, tzinfo=timezone).astimezone(UTC).isoformat()
    range_end = datetime(next_month.year, next_month.month, 1, tzinfo=timezone).astimezone(UTC).isoformat()
    try:
        measurements = sensor_measurement_repository().between_for_devices(list(device_records), range_start, range_end, limit=5000)
    except Exception:
        measurements = []

    deduplicated = {}
    for measurement in measurements:
        key = (measurement.get("device_id"), measurement.get("measured_at"), measurement.get("metric"))
        deduplicated[key] = measurement

    for device_id, record in device_records.items():
        for status in (record or {}).get("status_history") or []:
            measured_at = status.get("received_at") or ""
            payload = dict(status.get("payload") or {})
            if payload.get("soil_moisture_percent") is None and payload.get("last_soil_moisture") is not None:
                payload["soil_moisture_percent"] = payload["last_soil_moisture"]
            for measurement in extract_measurements_from_status(device_id, payload, measured_at):
                key = (device_id, measured_at, measurement.get("metric"))
                deduplicated.setdefault(key, measurement)
            duration_sec = payload.get("watering_duration_sec")
            if payload.get("watering_started") is True and isinstance(duration_sec, int | float) and not isinstance(duration_sec, bool) and duration_sec > 0:
                deduplicated[(device_id, measured_at, "watering_duration_min")] = {
                    "device_id": device_id,
                    "device_kind": payload.get("device_kind") or (record or {}).get("device_kind"),
                    "measured_at": measured_at,
                    "metric": "watering_duration_min",
                    "value": round(float(duration_sec) / 60, 2),
                    "unit": "分",
                    "quality": "ok",
                    "source": "device_action",
                    "payload": {"channel_mask": payload.get("channel_mask")},
                }

    placements_by_device = {row.get("device_id"): row for row in placement_rows or []}
    grouped = {}
    for measurement in deduplicated.values():
        measured = _to_local_datetime(measurement.get("measured_at"))
        if measured is None or not (month_start <= measured.date() < next_month):
            continue
        metric = measurement.get("metric") or ""
        definition = FIELD_RECORD_CATALOG_BY_KEY.get(metric)
        device_id = measurement.get("device_id") or ""
        record = device_records.get(device_id) or {}
        placement = placements_by_device.get(device_id) or {}
        item = {
            "device_id": device_id,
            "device_name": record.get("name") or device_id,
            "scope_label": placement.get("scope_label") or "圃場全体",
            "date": measured.date().isoformat(),
            "time": measured.strftime("%H:%M"),
            "measured_at": measurement.get("measured_at") or "",
            "metric": metric,
            "label": definition.get("label") if definition else METRIC_LABELS.get(metric, metric),
            "value": measurement.get("value"),
            "unit": definition.get("unit") if definition else measurement.get("unit") or "",
            "source": measurement.get("source") or "device",
            "target_placement_ids": list(placement.get("target_placement_ids") or []),
        }
        grouped.setdefault((item["date"], device_id, metric), []).append(item)

    result = []
    for items in grouped.values():
        result.extend(sorted(items, key=lambda item: item["measured_at"], reverse=True)[:24])
    return sorted(result, key=lambda item: (item["date"], item["time"], item["device_id"], item["metric"]))


def _build_active_planting_views(active_plantings: list, plant_bundle: dict, automatic_measurements: list, layout: dict):
    calendars = plant_bundle.get("calendars") or {}
    work_logs = plant_bundle.get("work_logs") or []
    category_labels = {
        "vegetable": "野菜",
        "fruit_tree": "果樹",
        "flower": "花き",
        "herb": "ハーブ",
        "other": "その他",
    }
    preset_by_placement = {placement.get("id"): placement.get("preset") for space in layout.get("spaces", []) for placement in space.get("placements", [])}
    cultivation_methods = {
        "ridge": [("ridge_soil", "畝・土耕"), ("ridge_mulch", "畝・マルチ栽培")],
        "tree": [("in_ground_tree", "地植え果樹・樹木")],
        "pot": [("container", "鉢・コンテナ栽培")],
        "hydroponic_bed": [("hydroponic", "水耕栽培"), ("nutrient_solution", "養液栽培")],
    }
    views = []
    for planting in active_plantings:
        view = dict(planting)
        calendar_record = calendars.get(planting.get("id")) or {}
        planned_actions = sorted(
            (action for action in calendar_record.get("actions", []) if action.get("status") == "planned"),
            key=lambda action: (action.get("window_start") or "", action.get("title") or ""),
        )
        activities = [
            {
                "at": planting.get("planted_on") or "",
                "at_display": planting.get("planted_on") or "",
                "kind": "planting",
                "kind_label": "定植",
                "title": f"{planting.get('crop_name') or '作物'}を登録",
                "detail": planting.get("placement_name") or "",
            }
        ]
        for log in work_logs:
            if log.get("planting_id") != planting.get("id") or log.get("review_status", "approved") != "approved":
                continue
            activities.append(
                {
                    "at": log.get("performed_on") or log.get("created_at") or "",
                    "at_display": log.get("performed_on") or "",
                    "kind": "work",
                    "kind_label": "作業",
                    "title": log.get("title") or "栽培作業",
                    "detail": log.get("note") or "カレンダーから実施を記録",
                }
            )
        for measurement in automatic_measurements:
            if planting.get("placement_id") not in measurement.get("target_placement_ids", []):
                continue
            is_watering = measurement.get("metric") in {"watering_duration_min", "watering_volume_l"}
            activities.append(
                {
                    "at": measurement.get("measured_at") or "",
                    "at_display": f"{measurement.get('date') or ''} {measurement.get('time') or ''}".strip(),
                    "kind": "watering" if is_watering else "sensor",
                    "kind_label": "潅水" if is_watering else "計測",
                    "title": f"{measurement.get('label') or measurement.get('metric')}: {measurement.get('value')} {measurement.get('unit') or ''}".strip(),
                    "detail": f"{measurement.get('device_name') or measurement.get('device_id')} / {measurement.get('scope_label') or '圃場全体'}",
                }
            )
        view["crop_category_label"] = category_labels.get(planting.get("crop_category"), "その他")
        view["placement_preset"] = preset_by_placement.get(planting.get("placement_id"), "")
        method_options = list(cultivation_methods.get(view["placement_preset"], [("other", "その他")]))
        current_method = planting.get("cultivation_method") or ""
        if current_method and current_method not in {value for value, _label in method_options}:
            method_options.insert(0, (current_method, current_method))
        view["cultivation_method_options"] = method_options
        view["calendar"] = calendar_record
        view["next_action"] = planned_actions[0] if planned_actions else None
        view["recent_activity"] = sorted(activities, key=lambda item: item.get("at") or "", reverse=True)[:10]
        views.append(view)
    return views


def _build_monitoring_scopes(placement_rows: list, latest_sensor_values: list):
    scopes = {}
    for row in placement_rows:
        label = row.get("scope_label") or "圃場全体"
        scope = scopes.setdefault(label, {"label": label, "devices": [], "sensor_values": []})
        identity = (row.get("device_id"), row.get("placement_id"), row.get("resource_type"), row.get("resource_id"))
        if not any(item.get("identity") == identity for item in scope["devices"]):
            scope["devices"].append({**row, "identity": identity})
    for item in latest_sensor_values:
        label = item.get("scope_label") or "圃場全体"
        scope = scopes.setdefault(label, {"label": label, "devices": [], "sensor_values": []})
        scope["sensor_values"].append(item)
    return list(scopes.values())


def _build_field_post_watering_notification_context(field_id: str, field_device_records: dict, placement_rows: list):
    service = post_watering_moisture_service()
    rules_by_sensor = {str(rule.get("sensor_device_id")): rule for rule in service.list_rules() if isinstance(rule, dict) and rule.get("sensor_device_id")}
    placement_by_device = {}
    for row in placement_rows or []:
        device_id = row.get("device_id")
        if device_id:
            placement_by_device.setdefault(device_id, row)

    field_sensor_records = {
        device_id: record
        for device_id, record in (field_device_records or {}).items()
        if device_id in placement_by_device
        if str(record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "").upper() in SOIL_MOISTURE_DEVICE_KINDS
    }

    discord = setting().get("discord") or {}
    discord_ready = bool(discord.get("webhook_url") and discord.get("enabled", True) and discord.get("notify_post_watering_moisture_low", True))
    if not discord.get("webhook_url"):
        discord_status_label = "Discord Webhook未設定"
    elif not discord.get("enabled", True):
        discord_status_label = "すべてのDiscord通知が停止中"
    elif not discord.get("notify_post_watering_moisture_low", True):
        discord_status_label = "水分未到達通知が停止中"
    else:
        discord_status_label = "Discord通知準備済み"

    def build_card(sensor_device_id, sensor_record, rule=None):
        device_kind = str(sensor_record.get("device_kind") or (sensor_record.get("last_status") or {}).get("device_kind") or "").upper()
        measurement_source = (rule or {}).get("measurement_source") or DEFAULT_MEASUREMENT_SOURCE
        latest_percent = soil_moisture_source_value(sensor_record.get("last_status") or {}, measurement_source)
        placement = placement_by_device.get(sensor_device_id) or {}
        monitor_state = service.rule_status(sensor_device_id) if rule else {}
        evaluation_status = monitor_state.get("status")
        if not rule:
            state = "unconfigured"
            state_label = "未設定"
        elif rule.get("enabled") is not True:
            state = "paused"
            state_label = "停止中"
        elif sensor_record.get("state") != "active":
            state = "warning"
            state_label = "センサー確認"
        elif evaluation_status == "not_reached":
            state = "warning"
            state_label = "未到達"
        elif not discord_ready:
            state = "warning"
            state_label = "通知準備待ち"
        elif evaluation_status in {"insufficient_data", "data_unavailable", "sensor_unavailable"}:
            state = "warning"
            state_label = "判定準備中"
        else:
            state = "active"
            state_label = "監視中"
        return {
            "sensor_device_id": sensor_device_id,
            "sensor_device_name": sensor_record.get("name") or sensor_device_id,
            "device_kind": device_kind or "不明",
            "scope_label": placement.get("scope_label") or sensor_record.get("location") or "圃場全体",
            "configured": bool(rule),
            "enabled": bool(rule and rule.get("enabled") is True),
            "wizard_available": bool(rule) or sensor_record.get("state") == "active",
            "state": state,
            "state_label": state_label,
            "sensor_state_label": "利用中" if sensor_record.get("state") == "active" else "停止・未確認",
            "latest_percent": latest_percent,
            "minimum_percent": (rule or {}).get("minimum_percent"),
            "window_days": (rule or {}).get("window_days"),
            "measurement_source_label": soil_moisture_source_label(sensor_record, measurement_source) if rule else "未設定",
            "last_reached_at": _format_datetime(monitor_state.get("last_reached_at")) if monitor_state.get("last_reached_at") else "未確認",
            "wizard_url": f"/settings/post-watering-moisture?{urlencode({'sensor_device_id': sensor_device_id, 'field_id': field_id})}",
            "device_settings_url": f"/mqtt-devices/{sensor_device_id}?tab=settings",
        }

    cards = [
        build_card(sensor_device_id, sensor_record, rules_by_sensor.get(sensor_device_id)) for sensor_device_id, sensor_record in field_sensor_records.items()
    ]
    cards.sort(key=lambda item: (item["scope_label"].casefold(), item["sensor_device_name"].casefold(), item["sensor_device_id"]))
    return {
        "cards": cards,
        "configured_count": sum(1 for card in cards if card["configured"]),
        "active_count": sum(1 for card in cards if card["state"] == "active"),
        "discord_ready": discord_ready,
        "discord_status_label": discord_status_label,
    }


def _field_compare_day(compare_date: str):
    if compare_date:
        try:
            return datetime.strptime(compare_date, "%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now(_local_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)


def _field_device_placement_rows(field: dict, device_records: dict):
    areas = field.get("areas") or []
    explicit = {(item.get("device_id"), item.get("device_role")): item for item in field.get("device_placements") or []}
    rows = []
    seen = set()
    for device_id in field.get("device_ids") or []:
        record = device_records.get(device_id)
        role = _infer_device_role(record)
        placement = explicit.get((device_id, role)) or _first_device_placement(explicit, device_id)
        row = _format_device_placement(device_id, role, placement, areas)
        row["device_name"] = (record or {}).get("name") or device_id
        row["device_kind"] = (record or {}).get("device_kind") or ""
        rows.append(row)
        seen.add(device_id)
    for camera_id in field.get("camera_device_ids") or []:
        if camera_id in seen:
            continue
        record = device_records.get(camera_id)
        placement = explicit.get((camera_id, "camera")) or _first_device_placement(explicit, camera_id)
        row = _format_device_placement(camera_id, "camera", placement, areas)
        row["device_name"] = (record or {}).get("name") or camera_id
        row["device_kind"] = (record or {}).get("device_kind") or "CAM"
        rows.append(row)
    return rows


def _infer_device_role(record: dict | None):
    device_kind = (record or {}).get("device_kind")
    if device_kind == "ENV":
        return "environment"
    if device_kind == "SOI":
        return "soil"
    if device_kind in {"WTR", "WRS", "FGT"}:
        return "watering"
    return "sensor"


def _first_device_placement(explicit: dict, device_id: str):
    for (candidate_device_id, _role), placement in explicit.items():
        if candidate_device_id == device_id:
            return placement
    return None


def _format_device_placement(device_id: str, role: str, placement: dict | None, areas: list):
    area_by_id = {area.get("id"): area for area in areas or []}
    placement = placement or {}
    scope_type = placement.get("scope_type") or "field"
    area_id = placement.get("area_id") or ""
    area = area_by_id.get(area_id) if area_id else None
    if scope_type == "field" or area is None:
        scope_label = "圃場全体"
        area_id = ""
    else:
        area_type_label = FIELD_AREA_TYPE_LABELS.get(area.get("area_type"), area.get("area_type") or "区画")
        scope_label = f"{area_type_label}: {area.get('name')}"
    return {
        "device_id": device_id,
        "device_role": placement.get("device_role") or role,
        "device_role_label": DEVICE_ROLE_LABELS.get(placement.get("device_role") or role, placement.get("device_role") or role),
        "scope_type": scope_type if scope_type in DEVICE_SCOPE_TYPE_LABELS else "field",
        "scope_label": scope_label,
        "area_id": area_id,
        "area": area,
        "crop_name": placement.get("crop_name") or (area or {}).get("crop_name") or "",
        "memo": placement.get("memo") or "",
    }


def _device_placement_for(placement_rows: list, device_id: str):
    for row in placement_rows:
        if row.get("device_id") == device_id:
            return row
    return None


def _field_image_compare_groups(camera_ids: list, compare_day: datetime):
    targets = [
        ("基準日", compare_day),
        ("前日", compare_day - timedelta(days=1)),
        ("7日前", compare_day - timedelta(days=7)),
    ]
    groups = []
    for label, target_day in targets:
        image = None
        for camera_id in camera_ids:
            images = _field_camera_images_for_date(camera_id, target_day, limit=1)
            if images:
                image = images[0]
                break
        groups.append({"label": label, "date": target_day.strftime("%Y-%m-%d"), "image": image})
    return groups


def _field_camera_images_for_date(camera_id: str, target_day: datetime, limit: int = 1):
    start_at = target_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_at = start_at + timedelta(days=1) - timedelta(microseconds=1)
    try:
        images = timelapse_media_service().list_frame_records(camera_id, start_at=start_at, end_at=end_at, limit=limit)
    except Exception:
        return []
    return [dict(image, camera_id=camera_id) for image in images]


def _build_field_soil_moisture_chart(statuses, field_events, include_plotlyjs=False, *, deferred=False):
    points = _soil_moisture_points(statuses)
    if not points:
        return ""

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[point["time"] for point in points],
            y=[point["soil_moisture"] for point in points],
            mode="lines+markers",
            name="土壌水分",
            line={"color": "#047857", "width": 3},
            marker={"size": 7},
            customdata=[[point["state"], point["threshold_label"]] for point in points],
            hovertemplate=("%{x|%Y-%m-%d %H:%M}<br>土壌水分: %{y}%<br>状態: %{customdata[0]}<br>しきい値: %{customdata[1]}<extra></extra>"),
        )
    )
    threshold_points = [point for point in points if point["threshold"] is not None]
    if threshold_points:
        fig.add_trace(
            go.Scatter(
                x=[point["time"] for point in threshold_points],
                y=[point["threshold"] for point in threshold_points],
                mode="lines",
                name="灌水しきい値",
                line={"color": "#f59e0b", "width": 2, "dash": "dash"},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>しきい値: %{y}%<extra></extra>",
            )
        )
    _add_field_event_markers(fig, field_events)
    fig.update_layout(
        title="土壌水分推移と圃場イベント",
        height=380,
        margin={"l": 56, "r": 24, "t": 48, "b": 48},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        yaxis_title="土壌水分（%）",
        legend={"orientation": "h", "y": -0.24},
    )
    _configure_time_axis(fig, points)
    fig.update_yaxes(range=[0, 100])
    return _plotly_div(fig, "field-soil-moisture-chart", include_plotlyjs=include_plotlyjs, deferred=deferred)


def _add_field_event_markers(fig, field_events):
    colors = {
        "watering": "#2563eb",
        "fertigation": "#7c3aed",
        "misting": "#0891b2",
        "fertilizer": "#9333ea",
        "shade": "#64748b",
        "pest": "#dc2626",
        "harvest": "#ea580c",
    }
    for event in (field_events or [])[:40]:
        event_time = _to_local_plot_time(event.get("occurred_at") or event.get("created_at"))
        if event_time is None:
            continue
        event_type = event.get("event_type") or "event"
        label = event.get("title") or event_type
        color = colors.get(event_type, "#475569")
        fig.add_shape(
            type="line",
            x0=event_time,
            x1=event_time,
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line={"color": color, "width": 1, "dash": "dot"},
        )
        fig.add_annotation(
            x=event_time,
            y=1,
            xref="x",
            yref="paper",
            text=label[:16],
            showarrow=False,
            yanchor="bottom",
            textangle=-90,
            font={"size": 10, "color": color},
        )


def _build_field_timeline(status_events: list, field_events: list, notes: list):
    timeline = []
    for event in status_events:
        timeline.append(
            {
                "kind": "device_status",
                "at": event.get("received_at"),
                "title": event.get("summary"),
                "body": event.get("device_id"),
                "rating_emoji": "",
                "attachments": [],
            }
        )
    for event in field_events:
        amount = ""
        if event.get("amount"):
            amount = f" {event.get('amount')}{event.get('unit') or ''}"
        body_parts = [
            part
            for part in (
                event.get("target_name") if event.get("target_name") not in (None, "", "圃場全体") else "",
                _field_record_values_summary(event.get("record_values")),
                event.get("description") or event.get("human_evaluation") or "",
            )
            if part
        ]
        timeline.append(
            {
                "kind": event.get("event_type") or "field_event",
                "at": event.get("occurred_at") or event.get("created_at"),
                "title": f"{event.get('title') or event.get('event_type')}{amount}",
                "body": " / ".join(body_parts),
                "rating_emoji": {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "😄"}.get(event.get("rating"), ""),
                "attachments": [
                    {"id": item.get("id"), "url": item.get("url"), "original_filename": item.get("original_filename") or "記録画像"}
                    for item in event.get("attachments") or []
                    if isinstance(item, dict) and item.get("url")
                ],
            }
        )
    for note in notes:
        timeline.append(
            {
                "kind": note.get("category") or "note",
                "at": note.get("created_at"),
                "title": note.get("text"),
                "body": note.get("human_evaluation") or "",
                "rating_emoji": {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "😄"}.get(note.get("rating"), ""),
                "attachments": [],
            }
        )
    return sorted(timeline, key=lambda item: item.get("at") or "", reverse=True)


def _field_record_search_view(item):
    amount = f" {item.get('amount')}{item.get('unit')}" if item.get("amount") else ""
    body_parts = [
        part
        for part in (
            item.get("target_name") if item.get("target_name") not in (None, "", "圃場全体") else "",
            _field_record_values_summary(item.get("record_values")),
            item.get("body") or "",
        )
        if part
    ]
    return {
        **item,
        "at": item.get("occurred_at") or "",
        "title": f"{item.get('title') or item.get('kind') or '記録'}{amount}",
        "body": " / ".join(body_parts),
        "rating_emoji": {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "😄"}.get(item.get("rating"), ""),
    }


def _compact_device_record(record: dict | None):
    if not isinstance(record, dict):
        return None
    return {
        "name": record.get("name"),
        "location": record.get("location"),
        "device_kind": record.get("device_kind"),
        "state": record.get("state"),
        "last_seen_at": record.get("last_seen_at"),
        "last_status_at": record.get("last_status_at"),
    }


def _field_latest_sensor_value(device_id: str, record: dict | None, placement: dict | None = None):
    payload = (record or {}).get("last_status") or {}
    device_kind = payload.get("device_kind") or (record or {}).get("device_kind")
    values = {}
    for key in (
        "last_soil_moisture",
        "soil_moisture_percent",
        "soil_moisture_1_pct",
        "soil_moisture_2_pct",
        "soil_temp_c",
        "soil_temperature_c",
        "soil_ec_us_cm",
        "soil_ph",
        "air_temperature_c",
        "air_humidity_percent",
        "par_umol_m2_s",
        "solar_radiation_w_m2",
        "battery_v",
        "rssi",
        "threshold",
    ):  # noqa: PLR0915
        if payload.get(key) is not None and metric_supported_for_device_kind(key, device_kind):
            values[key] = payload.get(key)
    rs485_devices = _field_rs485_sensor_values(payload, device_kind)
    if rs485_devices:
        values["rs485_devices"] = rs485_devices
    try:
        latest_measurements = sensor_measurement_repository().latest_for_device(device_id, limit=30)
    except Exception:
        latest_measurements = []
    for measurement in latest_measurements:
        metric = measurement.get("metric")
        if metric and measurement.get("value") is not None:
            values[metric] = measurement.get("value")
    try:
        sensor_latest = sensor_data_repository().get_latest(device_id)
    except Exception:
        sensor_latest = None
    if sensor_latest:
        telemetry = sensor_latest.get("telemetry") or {}
        for key in ("soil_moisture_1_pct", "soil_moisture_2_pct", "soil_temp_c", "battery_v", "rssi"):
            if telemetry.get(key) is not None:
                values[key] = telemetry.get(key)
        return {
            "device_id": device_id,
            "device_name": (record or {}).get("name") or device_id,
            "scope_label": (placement or {}).get("scope_label"),
            "target_placement_ids": (placement or {}).get("target_placement_ids") or [],
            "crop_name": (placement or {}).get("crop_name"),
            "area": (placement or {}).get("area"),
            "updated_at": sensor_latest.get("updated_at"),
            "received_at": (record or {}).get("last_status_at"),
            "values": values,
        }
    if not values:
        return None
    return {
        "device_id": device_id,
        "device_name": (record or {}).get("name") or device_id,
        "scope_label": (placement or {}).get("scope_label"),
        "target_placement_ids": (placement or {}).get("target_placement_ids") or [],
        "crop_name": (placement or {}).get("crop_name"),
        "area": (placement or {}).get("area"),
        "received_at": (record or {}).get("last_status_at"),
        "values": values,
    }


def _field_rs485_sensor_values(payload: dict, device_kind: str | None):
    devices = payload.get("rs485_devices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        return []

    metadata_keys = ("index", "enabled", "attempted", "bus_ready", "ok", "type", "name", "location", "modbus_slave_id", "baud")
    result = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        sensor = {key: device[key] for key in metadata_keys if key in device}
        for spec in _RS485_SENSOR_METRIC_SPECS:
            if not metric_supported_for_device_kind(spec["metric"], device_kind):
                continue
            value_key = spec["device_value_key"]
            if device.get(value_key) is not None:
                sensor[value_key] = device[value_key]
        result.append(sensor)
    return result


def _field_status_event(device_id: str, status_entry: dict):
    payload = status_entry.get("payload") or {}
    parts = []
    if payload.get("watering_due") is True:
        parts.append("灌水予定")
    if payload.get("watering_started") is True:
        parts.append(f"灌水開始 {payload.get('watering_duration_sec', '-')}秒")
    if payload.get("soil_calibration_suggested") is True:
        parts.append("水分計校正見直し候補")
    if payload.get("last_soil_moisture") is not None:
        parts.append(f"土壌水分 {payload.get('last_soil_moisture')}%")
    if not parts:
        parts.append("状態を受信")
    return {"device_id": device_id, "received_at": status_entry.get("received_at"), "summary": " / ".join(parts), "payload": payload}


def _field_sensor_images(device_id: str, limit: int = 2):
    try:
        images = sensor_image_repogitory().fetch_latest(device_id, limit=limit)
    except Exception:
        return []
    result = []
    for image in images:
        item = dict(image)
        item["url"] = f"/local/api/images/{item.get('image_path')}"
        result.append(item)
    return result


def _field_camera_images(camera_id: str, limit: int = 2):
    try:
        images = timelapse_media_service().list_frame_records(camera_id, limit=limit)
    except Exception:
        return []
    return [dict(image, camera_id=camera_id) for image in images]


def _build_field_camera_views(camera_ids: list, placement_rows: list):
    media_service = timelapse_media_service()
    list_videos = getattr(media_service, "list_video_records", None)
    cameras = []
    for camera_id in camera_ids:
        camera = camera_management_service().get(camera_id) or {}
        placement = _device_placement_for(placement_rows, camera_id) or {}
        try:
            frames = media_service.list_frame_records(camera_id, limit=1)
        except Exception:
            frames = []
        try:
            videos = list_videos(camera_id, limit=1) if callable(list_videos) else []
        except Exception:
            videos = []
        latest_video = videos[0] if videos and camera.get("timelapse") else None
        if latest_video:
            try:
                video_captured_at = datetime.fromisoformat(latest_video.get("captured_at") or "")
                if video_captured_at.tzinfo is not None:
                    video_captured_at = video_captured_at.astimezone().replace(tzinfo=None)
                if video_captured_at < datetime.now() - timedelta(hours=24):
                    latest_video = None
            except (TypeError, ValueError):
                latest_video = None
        cameras.append(
            {
                "id": camera_id,
                "name": camera.get("name") or placement.get("device_name") or camera_id,
                "scope_label": placement.get("scope_label") or "圃場全体",
                "latest_frame": frames[0] if frames else None,
                "latest_video": latest_video,
                "timelapse_enabled": bool(camera.get("timelapse")),
                "detail_url": camera.get("detail_url") or f"/camera/{quote(str(camera_id), safe='')}",
                "timelapse_url": f"/local/api/camera/{quote(str(camera_id), safe='')}/recent-timelapse",
            }
        )
    return cameras


# ==========================================
# Local API
# ==========================================
@app.route("/local/api/devices", methods=["GET"])
def get_devices():
    devices = sensor_device_repository().get_all()
    return jsonify(devices)


@app.route("/local/api/locations", methods=["GET"])
def get_locations():
    locations = location_repository().get_all()
    return jsonify(locations)


@app.route("/local/api/mqtt-events", methods=["GET"])
def list_mqtt_events():
    return jsonify(
        list_device_events(
            limit=_request_limit(default=100, maximum=1000),
            device_id=request.args.get("device_id"),
            event_type=request.args.get("event_type"),
            direction=request.args.get("direction"),
        )
    )


@app.route("/local/api/mqtt-connections", methods=["GET"])
def list_mqtt_connections():
    return jsonify(
        list_device_events(
            limit=_request_limit(default=100, maximum=1000),
            device_id=request.args.get("device_id"),
            connection_events_only=True,
        )
    )


@app.route("/local/api/device-configs", methods=["GET"])
def get_device_configs():
    return jsonify(device_config_service().get_all_records())


@app.route("/local/api/device-configs/<device_id>", methods=["GET"])
def get_device_config(device_id):
    return jsonify(device_config_service().get_record(device_id))


@app.route("/local/api/device-configs/<device_id>", methods=["PUT"])
def update_device_config(device_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    push = request.args.get("push", "false").lower() == "true"
    try:
        result = device_config_service().update_and_optionally_push(device_id, request_body, push=push)
    except DeviceStateConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except DeviceConfigValidationError as exc:
        payload = {"error": str(exc)}
        if exc.code:
            payload["code"] = exc.code
        if exc.details:
            payload["details"] = exc.details
        return jsonify(payload), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(result)


@app.route("/local/api/device-configs/<device_id>/push", methods=["POST"])
def push_device_config(device_id):
    try:
        published = device_config_service().publish_push(device_id)
    except DeviceStateConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except DeviceConfigValidationError as exc:
        payload = {"error": str(exc)}
        if exc.code:
            payload["code"] = exc.code
        if exc.details:
            payload["details"] = exc.details
        return jsonify(payload), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(published)


@app.route("/local/api/mqtt-devices", methods=["GET"])
def list_mqtt_devices():
    search_requested = any(key in request.args for key in ("q", "state", "device_kind", "page", "page_size"))
    if not search_requested:
        return jsonify(device_config_service().get_all_records())
    try:
        result = device_config_service().search_records(
            query=request.args.get("q", ""),
            states=_query_list("state"),
            device_kinds=_query_list("device_kind"),
            page=request.args.get("page", 1),
            page_size=request.args.get("page_size", 50),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.route("/local/api/mqtt-devices/<device_id>", methods=["GET"])
def get_mqtt_device(device_id):
    record = device_config_service().find_record(device_id)
    if record is None:
        return jsonify({"error": "device not found"}), 404
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>", methods=["DELETE"])
def delete_mqtt_device(device_id):
    user = current_user_from_request(request)
    try:
        deleted = device_removal_service().delete(device_id, deleted_by=user.email or "local-operator")
    except DeviceRemovalConflictError as exc:
        return jsonify({"error": str(exc), "references": exc.references}), 409
    if deleted is None:
        return jsonify({"error": "device not found"}), 404
    return jsonify({"deleted": True, "device_id": device_id})


@app.route("/local/api/mqtt-devices/<device_id>", methods=["PATCH"])
def update_mqtt_device_metadata(device_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    try:
        record = device_config_service().update_metadata(device_id, request_body)
    except DeviceStateConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>/approve", methods=["POST"])
def approve_mqtt_device(device_id):
    request_body = request.get_json(silent=True) or {}
    try:
        record = device_config_service().set_state(device_id, "active", approved_by=request_body.get("approved_by"))
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>/disable", methods=["POST"])
def disable_mqtt_device(device_id):
    try:
        return jsonify(device_config_service().set_state(device_id, "disabled"))
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/mqtt-devices/<device_id>/retire", methods=["POST"])
def retire_mqtt_device(device_id):
    try:
        return jsonify(device_config_service().set_state(device_id, "retired"))
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 409


@app.route("/local/api/mqtt-devices/<device_id>/runtime-config", methods=["GET"])
def get_mqtt_device_runtime_config(device_id):
    return jsonify(device_config_service().get_config(device_id))


@app.route("/local/api/mqtt-devices/<device_id>/runtime-config/payload", methods=["GET"])
def get_mqtt_device_runtime_config_payload(device_id):
    return jsonify(device_config_service().get_runtime_config_payload(device_id))


@app.route("/local/api/mqtt-devices/<device_id>/runtime-config", methods=["PUT"])
def update_mqtt_device_runtime_config(device_id):
    return update_device_config(device_id)


@app.route("/local/api/mqtt-devices/<device_id>/runtime-config/push", methods=["POST"])
def push_mqtt_device_runtime_config(device_id):
    return push_device_config(device_id)


@app.route("/local/api/mqtt-devices/<device_id>/statuses", methods=["GET"])
def list_mqtt_device_statuses(device_id):
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    return jsonify(device_config_service().list_statuses(device_id, limit=limit))


@app.route("/local/api/mqtt-devices/<device_id>/charts", methods=["GET"])
def get_mqtt_device_charts(device_id):
    record = device_config_service().find_record(device_id)
    if record is None:
        return jsonify({"error": "device not found"}), 404
    statuses = (record.get("status_history") or [])[-MQTT_ADMIN_STATUS_HISTORY_LIMIT:]
    return jsonify(_build_mqtt_device_chart_payload(statuses, record.get("device_kind")))


@app.route("/local/api/mqtt-devices/<device_id>/technical-data", methods=["GET"])
def get_mqtt_device_technical_data(device_id):
    record = device_config_service().find_record(device_id)
    if record is None:
        return jsonify({"error": "device not found"}), 404
    return jsonify(
        html=_render_mqtt_device_technical_data(
            (record.get("status_history") or [])[-MQTT_ADMIN_STATUS_HISTORY_LIMIT:],
            (record.get("ota_status_history") or [])[-20:],
            list_device_events(limit=50, device_id=device_id, connection_events_only=True),
            list_device_events(limit=50, device_id=device_id),
        )
    )


@app.route("/demo/local/api/mqtt-devices/<device_id>/technical-data", methods=["GET"])
def get_demo_mqtt_device_technical_data(device_id):
    demo_data = _demo_mqtt_admin_page_data(device_id)
    if device_id not in demo_data["devices"]:
        return jsonify({"error": "device not found"}), 404
    return jsonify(
        html=_render_mqtt_device_technical_data(
            demo_data["selected_statuses"], demo_data["selected_ota_statuses"], demo_data["connection_events"], demo_data["recent_events"]
        )
    )


def _render_mqtt_device_technical_data(statuses, ota_statuses, connection_events, recent_events):
    return render_template(
        "mqtt_device_technical_data.html",
        statuses=statuses,
        ota_statuses=ota_statuses,
        connection_events=connection_events,
        recent_events=recent_events,
        format_datetime=_format_datetime,
        format_json=_format_json,
        render_events=_render_event_table,
    )


@app.route("/demo/local/api/mqtt-devices/<device_id>/charts", methods=["GET"])
def get_demo_mqtt_device_charts(device_id):
    demo_data = _demo_mqtt_admin_page_data(device_id)
    if device_id not in demo_data["devices"]:
        return jsonify({"error": "device not found"}), 404
    record = demo_data["devices"].get(device_id) or {}
    return jsonify(_build_mqtt_device_chart_payload(demo_data["selected_statuses"], record.get("device_kind")))


def _build_mqtt_device_chart_payload(statuses, device_kind=None):
    watering_chart = _build_watering_trend_chart(statuses, include_plotlyjs=False)
    charts = {
        "watering": watering_chart,
        "soil_moisture": _build_soil_moisture_chart(statuses, include_plotlyjs=False),
        "battery_voltage": _build_metric_trend_chart(
            statuses,
            aliases=("battery_voltage_v",),
            title="バッテリー電圧推移",
            unit="V",
            color="#475569",
            div_id="battery-voltage-chart",
        ),
        "air_temperature": _build_metric_trend_chart(
            statuses,
            aliases=("air_temperature_c",),
            title="気温推移",
            unit="℃",
            color="#dc2626",
            div_id="air-temperature-chart",
        ),
        "air_humidity": _build_metric_trend_chart(
            statuses,
            aliases=("air_humidity_percent",),
            title="湿度推移",
            unit="%",
            color="#0284c7",
            div_id="air-humidity-chart",
            y_range=(0, 100),
        ),
        "soil_temperature": _build_metric_trend_chart(
            statuses,
            aliases=("soil_temperature_c",),
            title="地温推移",
            unit="℃",
            color="#b45309",
            div_id="soil-temperature-chart",
            rs485_value_key="temperature_c",
        ),
        "soil_ec": _build_metric_trend_chart(
            statuses,
            aliases=("soil_ec_us_cm",),
            title="土壌EC推移",
            unit="uS/cm",
            color="#7c3aed",
            div_id="soil-ec-chart",
            rs485_value_key="ec_us_cm",
        ),
        "soil_ph": _build_metric_trend_chart(
            statuses,
            aliases=("soil_ph",),
            title="土壌pH推移",
            unit="",
            color="#0f766e",
            div_id="soil-ph-chart",
            y_range=(0, 14),
            rs485_value_key="ph",
        ),
        "soil_n": _build_metric_trend_chart(
            statuses,
            aliases=("soil_n_mg_kg",),
            title="土壌窒素推移",
            unit="mg/kg",
            color="#15803d",
            div_id="soil-n-chart",
            rs485_value_key="n_mg_kg",
        ),
        "soil_p": _build_metric_trend_chart(
            statuses,
            aliases=("soil_p_mg_kg",),
            title="土壌リン推移",
            unit="mg/kg",
            color="#0369a1",
            div_id="soil-p-chart",
            rs485_value_key="p_mg_kg",
        ),
        "soil_k": _build_metric_trend_chart(
            statuses,
            aliases=("soil_k_mg_kg",),
            title="土壌カリウム推移",
            unit="mg/kg",
            color="#be123c",
            div_id="soil-k-chart",
            rs485_value_key="k_mg_kg",
        ),
        "batch_water": _build_metric_trend_chart(
            statuses,
            aliases=("inlet_water_ml",),
            title="今回の給水量推移",
            unit="mL",
            color="#0284c7",
            div_id="batch-water-chart",
        ),
        "batch_target": _build_metric_trend_chart(
            statuses,
            aliases=("nutrient_batch_water_target_ml",),
            title="今回の目標量推移",
            unit="mL",
            color="#047857",
            div_id="batch-target-chart",
        ),
        "par": _build_metric_trend_chart(
            statuses,
            aliases=("par_umol_m2_s",),
            title="PAR推移",
            unit="umol/m2/s",
            color="#ca8a04",
            div_id="par-chart",
            rs485_value_key="par_umol_m2_s",
        ),
    }
    chart_metrics = {
        "air_temperature": "air_temperature_c",
        "air_humidity": "air_humidity_percent",
        "battery_voltage": "battery_voltage_v",
        "soil_moisture": "soil_moisture_percent",
        "soil_temperature": "soil_temperature_c",
        "soil_ec": "soil_ec_us_cm",
        "soil_ph": "soil_ph",
        "soil_n": "soil_n_mg_kg",
        "soil_p": "soil_p_mg_kg",
        "soil_k": "soil_k_mg_kg",
        "par": "par_umol_m2_s",
    }
    return {key: value for key, value in charts.items() if metric_supported_for_device_kind(chart_metrics.get(key, key), device_kind)}


@app.route("/local/assets/plotly.min.js", methods=["GET"])
def plotly_asset():
    response = Response(_plotly_javascript(), mimetype="application/javascript")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@lru_cache(maxsize=1)
def _plotly_javascript():
    plotly_js_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    return plotly_js_path.read_text(encoding="utf-8")


@app.route("/local/api/firmware-artifacts", methods=["GET"])
def list_firmware_artifacts():
    return jsonify(ota_update_service().get_artifacts())


@app.route("/local/api/firmware-artifacts/inspect", methods=["POST"])
def inspect_firmware_artifact():
    try:
        firmware_upload = normalize_firmware_upload(_read_firmware_upload(), max_upload_bytes=_firmware_upload_limit())
    except FirmwareUploadTooLargeError as exc:
        return jsonify({"error": str(exc)}), 413
    except FirmwareUploadValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 413

    try:
        metadata = extract_firmware_manifest(firmware_upload.firmware_binary)
        firmware_upload.validate_embedded_manifest(metadata)
    except (FirmwareArtifactValidationError, FirmwareUploadValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({**metadata, "upload_format": firmware_upload.source_format})


@app.route("/local/api/firmware-artifacts/<version>", methods=["PUT"])
def upsert_firmware_artifact(version):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    try:
        artifact = ota_update_service().upsert_artifact(version, request_body)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(artifact)


@app.route("/local/api/firmware-artifacts/<device_kind>/<version>/upload", methods=["POST", "PUT"])
def upload_firmware_artifact(device_kind, version):
    try:
        firmware_binary = _read_firmware_upload()
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 413
    if not firmware_binary:
        return jsonify({"error": "firmware binary must not be empty"}), 400

    try:
        metadata = _firmware_upload_metadata()
        artifact = ota_update_service().upsert_firmware_binary(device_kind, version, firmware_binary, metadata=metadata)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(artifact), 201


def _read_firmware_upload():
    limit = _firmware_upload_limit()
    uploaded_file = request.files.get("firmware") or request.files.get("file")
    stream = uploaded_file.stream if uploaded_file is not None else request.stream
    firmware_binary = stream.read(limit + 1)
    if len(firmware_binary) > limit:
        raise FirmwareArtifactValidationError(f"firmware upload exceeds the {limit}-byte limit")
    return firmware_binary


def _firmware_upload_limit():
    return int((setting().get("security") or {}).get("firmware_max_upload_bytes", 16 * 1024 * 1024))


@app.route("/firmware/<device_kind>/<version>/firmware.bin", methods=["GET"])
def download_firmware_binary(device_kind, version):
    try:
        firmware_path = ota_update_service().get_firmware_path(device_kind, version)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    if not os.path.isfile(firmware_path):
        return jsonify({"error": "firmware binary not found"}), 404
    return send_file(firmware_path, mimetype="application/octet-stream", as_attachment=False, download_name="firmware.bin")


@app.route("/local/api/mqtt-devices/<device_id>/firmware-target", methods=["PUT"])
def set_mqtt_device_firmware_target(device_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    target = request_body.get("target_firmware_version", request_body.get("version"))
    try:
        record = ota_update_service().set_firmware_target(device_id, target)
    except DeviceStateConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>/ota-statuses", methods=["GET"])
def list_mqtt_device_ota_statuses(device_id):
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    return jsonify(ota_update_service().list_ota_statuses(device_id, limit=limit))


def _firmware_upload_metadata():
    metadata = {}
    for key in ("update_id", "build_id", "rollout_state"):
        value = request.form.get(key, request.args.get(key))
        if value is not None and value != "":
            metadata[key] = value
    for key in ("force", "allow_downgrade"):
        value = request.form.get(key, request.args.get(key))
        if value is not None and value != "":
            metadata[key] = _parse_bool(value, key)
    return metadata


def _parse_bool(value, key):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise FirmwareArtifactValidationError(f"{key} must be a boolean")


@app.route("/local/api/images/<path:image_path>")
def get_image(image_path):
    image_repo = sensor_image_repogitory()
    sensor_images = image_repo.fetch_from_cloud_as_bytes(image_path)
    if not sensor_images:
        return jsonify({"error": "no image"}), 404
    return Response(sensor_images, mimetype="image/jpeg")


@app.route("/local/api/camera/<device_id>/video_feed")
def video_feed(device_id):
    # ブラウザで再生する場合、multipart/x-mixed-replace の形式で配信
    return Response(
        camera_connector().generate_frames(device_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/local/api/camera/<device_id>/images", methods=["GET"])
def list_camera_images(device_id):
    date_value = request.args.get("date", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    limit = _request_limit(default=48, maximum=500)
    start_at, end_at, date_error = _camera_image_date_range(
        date_value,
        start_date=start_date,
        end_date=end_date,
    )
    if date_error:
        return jsonify({"error": date_error}), 400
    return jsonify(
        timelapse_media_service().list_frame_records(
            device_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )
    )


@app.route("/local/api/camera/<device_id>/recent-timelapse", methods=["POST"])
def create_recent_camera_timelapse(device_id):
    camera = camera_management_service().get(device_id)
    if camera is None:
        return jsonify({"error": "camera not found"}), 404
    now = datetime.now()
    video = timelapse_media_service().ensure_recent_video(
        device_id,
        start_at=now - timedelta(hours=24),
        end_at=now,
        fps=8,
        max_frames=96,
    )
    if video is None:
        return jsonify({"error": "タイムラプスには直近24時間の画像が2枚以上必要です"}), 422
    return jsonify(video)


@app.route("/local/api/camera-images/<path:image_path>", methods=["GET"])
def get_camera_image(image_path):
    frame_path = timelapse_media_service().resolve_frame_path(image_path)
    if frame_path is None:
        return jsonify({"error": "no image"}), 404
    return send_file(frame_path, mimetype="image/jpeg")


@app.route("/local/api/camera-videos/<path:video_path>", methods=["GET"])
def get_camera_video(video_path):
    video_path = timelapse_media_service().resolve_video_path(video_path)
    if video_path is None:
        return jsonify({"error": "no video"}), 404
    return send_file(video_path, mimetype="video/mp4", conditional=True)


def initialize_web_server():
    """Prepare the on-device database before accepting HTTP requests."""
    global _web_initialized
    if _web_initialized:
        return
    sensor_measurement_repository()
    user_preference_repository()
    _web_initialized = True


def flask_run():
    serve_http()


def serve_http():
    initialize_web_server()
    http_settings = setting().get("http") or {}
    host = http_settings.get("host", "0.0.0.0")
    port = int(http_settings.get("port", 39151))
    if http_settings.get("server", "waitress") == "flask":
        app.run(host=host, port=port)
        return

    from waitress import serve

    server_options = {
        "host": host,
        "port": port,
        "threads": int(http_settings.get("threads", 8)),
        "clear_untrusted_proxy_headers": True,
        "max_request_body_size": int(http_settings.get("max_request_bytes", 64 * 1024 * 1024)),
    }
    if authentication_mode() == "cloudflare_access":
        server_options.update(
            trusted_proxy="127.0.0.1",
            trusted_proxy_count=1,
            trusted_proxy_headers={"x-forwarded-host", "x-forwarded-proto"},
        )
    serve(app, **server_options)


def _request_limit(default: int = 100, maximum: int = 1000):
    try:
        limit = int(request.args.get("limit", str(default)))
    except ValueError:
        return default
    return max(1, min(limit, maximum))


def _camera_image_date_range(date_value: str, *, start_date: str = "", end_date: str = ""):
    if date_value and (start_date or end_date):
        return None, None, "date cannot be combined with start_date or end_date"
    if date_value:
        start_date = date_value
        end_date = date_value
    if not start_date and not end_date:
        return None, None, None
    try:
        start_at = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_day = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
    except ValueError:
        return None, None, "date values must be YYYY-MM-DD"
    end_at = end_day + timedelta(days=1) - timedelta(microseconds=1) if end_day else None
    if start_at and end_at and start_at > end_at:
        return None, None, "start_date must be on or before end_date"
    return start_at, end_at, None


def _format_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _render_event_table(events):
    if not events:
        return "<p>No events</p>"
    rows = []
    for event in reversed(events):
        payload = escape(_format_json(event.get("payload")))
        rows.append(
            "<tr>"
            f"<td>{escape(_format_datetime(event.get('occurred_at')))}</td>"
            f"<td>{escape(str(event.get('event_type') or ''))}</td>"
            f"<td>{escape(str(event.get('direction') or ''))}</td>"
            f"<td>{escape(str(event.get('topic') or ''))}</td>"
            f"<td><pre>{payload}</pre></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>time</th><th>event</th><th>direction</th><th>topic</th><th>payload</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
