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
    DEFAULT_MINIMUM_PERCENT,
    WATERING_DEVICE_KINDS,
    PostWateringMoistureValidationError,
    post_watering_device_options,
    post_watering_moisture_service,
    post_watering_rule_views,
    soil_moisture_sensor_options,
    soil_moisture_value,
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
        "post_watering_setup_url": f"/settings/post-watering-moisture?{urlencode({'watering_device_id': device_id})}",
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
        recent_events = demo_data["recent_events"] if is_detail_page else []
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
            devices = {device_id: selected_record} if selected_record is not None else {}
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
        selected_statuses = device_config_service().list_statuses(selected_device_id, limit=MQTT_ADMIN_STATUS_HISTORY_LIMIT) if selected_device_id else []
        selected_ota_statuses = ota_update_service().list_ota_statuses(selected_device_id, limit=20) if selected_device_id else []
        firmware_artifacts = ota_update_service().get_artifacts()
        recent_events = list_device_events(limit=50, device_id=selected_device_id) if selected_device_id else list_device_events(limit=50)
        connection_events = (
            list_device_events(limit=50, device_id=selected_device_id, connection_events_only=True)
            if selected_device_id
            else list_device_events(limit=50, connection_events_only=True)
        )
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
    template = """
    <!doctype html>
    <html lang="{{ ui_locale }}">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Hub 管理パネル</title>
        <link rel="stylesheet" href="/static/searchable-select.css">
        <script defer src="/static/ui-locale.js"></script>
        <style>
          :root {
            --bg: #f1f4f0;
            --panel: #ffffff;
            --line: #d3ddd5;
            --text: #1d2a22;
            --muted: #65736a;
            --blue: #1f6b52;
            --green: #1f6b52;
            --green-bg: #e9f7ef;
            --yellow: #8a5a00;
            --yellow-bg: #fff7df;
            --red: #9f1239;
            --red-bg: #fff1f2;
            --gray-bg: #eef2f7;
          }
          * { box-sizing: border-box; }
          body {
            margin: 0;
            background: var(--bg);
            color: var(--text);
            font-family: Arial, "Yu Gothic", "Meiryo", sans-serif;
            line-height: 1.45;
          }
          a { color: #176b55; text-decoration: none; }
          a:hover { text-decoration: underline; }
          .page { max-width: 1240px; margin: 0 auto; padding: 22px 28px 46px; }
          .topbar {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
            padding: 14px 0 18px;
            border-bottom: 1px solid var(--line);
          }
          h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
          h2 { margin: 0 0 12px; font-size: 20px; letter-spacing: 0; }
          h3 { margin: 0 0 10px; font-size: 16px; letter-spacing: 0; }
          .lead { margin: 6px 0 0; color: var(--muted); }
          .notice {
            border: 1px solid #bfdbfe;
            background: #eff6ff;
            color: #1e3a8a;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 0 0 18px;
          }
          .notice.warn {
            border-color: #fde68a;
            background: #fffbeb;
            color: #92400e;
          }
          .connection-check-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin: 14px 0 18px;
          }
          .connection-check-card {
            display: grid;
            align-content: start;
            gap: 6px;
            min-height: 184px;
            border: 1px solid var(--line);
            border-top: 4px solid #94a3b8;
            border-radius: 9px;
            background: #fff;
            padding: 13px;
          }
          .connection-check-card.good { border-top-color: var(--green); background: #f7fcf9; }
          .connection-check-card.ok { border-top-color: #4f7d69; background: #f8fbf9; }
          .connection-check-card.warn { border-top-color: #d39a24; background: #fffaf0; }
          .connection-check-step {
            display: inline-grid;
            place-items: center;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: #e5efe8;
            color: #215b42;
            font-size: 13px;
            font-weight: 900;
          }
          .connection-check-card > span:not(.connection-check-step) { color: var(--muted); font-size: 13px; font-weight: 700; }
          .connection-check-card > strong { color: #173c2a; font-size: 21px; line-height: 1.25; }
          .connection-check-card small { color: var(--muted); }
          .connection-check-card p { margin: 2px 0 0; font-size: 13px; line-height: 1.6; }
          .connection-timeline { display: grid; gap: 8px; margin-top: 10px; }
          .connection-event {
            display: grid;
            grid-template-columns: 10px minmax(150px, .65fr) minmax(260px, 1.35fr) auto;
            gap: 10px;
            align-items: center;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 10px 12px;
            background: #fff;
          }
          .connection-event-dot { width: 10px; height: 10px; border-radius: 50%; background: #94a3b8; }
          .connection-event.good .connection-event-dot { background: var(--green); }
          .connection-event.ok .connection-event-dot { background: #4f7d69; }
          .connection-event.warn .connection-event-dot { background: #d39a24; }
          .connection-event strong, .connection-event span { display: block; }
          .connection-event p { margin: 0; color: var(--muted); font-size: 13px; }
          .connection-event time { color: var(--muted); font-size: 12px; text-align: right; }
          .connection-reading-guide { margin: 12px 0 0; padding: 12px 14px; border-left: 4px solid #4f7d69; background: #f5f9f6; }
          .connection-reading-guide p { margin: 0; }
          .context-help.left.connection-help .context-help-panel {
            right: auto;
            left: 0;
            width: min(860px, calc(100vw - 48px));
            max-height: min(680px, calc(100vh - 96px));
            padding: 18px;
          }
          .connection-help-panel > strong { font-size: 17px; }
          .connection-help-panel > p { margin-top: 7px; }
          .connection-help-panel .connection-check-grid { margin: 14px 0; }
          .connection-help-panel .connection-check-card { min-height: 158px; }
          .connection-help-panel .connection-check-card > strong { font-size: 18px; }
          .connection-help-next { margin-top: 12px !important; color: var(--muted); }
          @media (max-width: 520px) {
            .context-help.left.connection-help .context-help-panel {
              position: fixed;
              top: auto;
              right: 12px;
              bottom: 12px;
              left: 12px;
              width: auto;
              max-height: min(76vh, 680px);
              border-width: 2px;
            }
          }
          .progress-banner {
            position: sticky;
            top: 0;
            z-index: 20;
            display: none;
            align-items: center;
            gap: 9px;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            background: #eff6ff;
            color: #1e3a8a;
            padding: 9px 12px;
            margin: 0 0 14px;
            box-shadow: 0 8px 18px rgba(15, 23, 42, .08);
          }
          .progress-banner.active { display: flex; }
          .progress-dot {
            width: 14px;
            height: 14px;
            border: 2px solid #93c5fd;
            border-top-color: var(--blue);
            border-radius: 999px;
            animation: spin .8s linear infinite;
            flex: 0 0 auto;
          }
          @keyframes spin { to { transform: rotate(360deg); } }
          .back-link { margin: 0 0 14px; }
          .back-link a {
            display: inline-flex;
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            padding: 7px 10px;
          }
          .device-guide { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr); min-height: 190px; overflow: hidden; border: 1px solid #c9d8ce; border-radius: 10px; background: linear-gradient(120deg, #f9fcf9, #eaf3ed); margin-bottom: 18px; }
          .device-guide-copy { align-self: center; padding: 24px 26px; }
          .device-guide-copy span { color: #2c745c; font-size: 11px; font-weight: 800; letter-spacing: .06em; }
          .device-guide-copy h2 { margin: 5px 0 0; color: #20372b; font-size: 25px; }
          .device-guide-copy p { max-width: 620px; margin: 8px 0 0; color: var(--muted); font-size: 13px; }
          .device-guide img { width: 100%; height: 100%; min-height: 190px; object-fit: cover; border-left: 1px solid #c9d8ce; }
          .quick-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }
          .quick-actions a {
            display: inline-flex;
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            color: var(--text);
            padding: 7px 10px;
            font-size: 14px;
          }
          .quick-actions a.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
          .field-section {
            border: 1px solid #c7d7c5;
            border-radius: 8px;
            background: #f7faf6;
            padding: 18px;
            margin-bottom: 18px;
          }
          .field-head {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
          }
          .field-head h2 { margin-bottom: 0; }
          .field-map {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
          }
          .field-zone {
            position: relative;
            display: grid;
            gap: 10px;
            min-height: 176px;
            overflow: hidden;
            border: 1px solid #adc7ad;
            border-radius: 8px;
            background: linear-gradient(180deg, #edf7ee 0%, #f8fafc 100%);
            color: var(--text);
            padding: 12px;
          }
          .field-zone:hover { text-decoration: none; border-color: #6b9f75; }
          .field-zone[aria-current="true"] { border-color: var(--blue); box-shadow: inset 3px 0 0 var(--blue); }
          .field-zone.warn { border-color: #d9a948; }
          .field-zone.danger { border-color: #e11d48; }
          .field-zone::before {
            content: "";
            position: absolute;
            inset: 52px 12px 12px;
            border-radius: 6px;
            background: repeating-linear-gradient(90deg, rgba(22, 101, 52, .10) 0 2px, transparent 2px 22px);
            pointer-events: none;
          }
          .field-zone > * { position: relative; }
          .zone-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
          }
          .zone-name { font-weight: 700; font-size: 16px; }
          .ridge-stack { display: grid; gap: 6px; }
          .ridge-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 8px;
            align-items: center;
            min-height: 36px;
            border: 1px solid rgba(148, 163, 184, .45);
            border-left: 4px solid #64748b;
            border-radius: 6px;
            background: rgba(255, 255, 255, .92);
            padding: 7px 8px;
          }
          .ridge-row.good { border-left-color: var(--green); }
          .ridge-row.ok { border-left-color: #0284c7; }
          .ridge-row.warn { border-left-color: #d97706; }
          .ridge-row.danger { border-left-color: #e11d48; }
          .ridge-row.muted { border-left-color: #94a3b8; color: var(--muted); }
          .ridge-row[aria-current="true"] { outline: 2px solid rgba(29, 78, 216, .35); }
          .ridge-name {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-weight: 700;
          }
          .ridge-meta {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
            color: var(--muted);
            font-size: 12px;
          }
          .ridge-empty {
            min-height: 28px;
            border: 1px dashed rgba(100, 116, 139, .35);
            border-radius: 6px;
            background: rgba(255, 255, 255, .42);
          }
          .nav { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
          .nav a, button {
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            color: var(--text);
            padding: 7px 10px;
            font-size: 14px;
            cursor: pointer;
          }
          button.primary { background: var(--blue); color: #fff; border-color: var(--blue); }
          button:disabled { opacity: .65; cursor: not-allowed; }
          button[aria-busy="true"] { cursor: wait; }
          button[aria-busy="true"]::after {
            content: "";
            width: 12px;
            height: 12px;
            margin-left: 7px;
            border: 2px solid currentColor;
            border-top-color: transparent;
            border-radius: 999px;
            display: inline-block;
            vertical-align: -2px;
            animation: spin .8s linear infinite;
          }
          .result { border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 10px 12px; margin: 0 0 18px; min-height: 40px; color: var(--muted); }
          .result[hidden] { display: none; }
          .error { border-color: #fecdd3; background: var(--red-bg); color: var(--red); }
          .ok { border-color: #bbf7d0; background: var(--green-bg); color: var(--green); }
          .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 18px;
          }
          .detail-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
          }
          .device-identity { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 18px; align-items: center; }
          .device-identity img { width: 220px; aspect-ratio: 2 / 1; object-fit: cover; border: 1px solid var(--line); border-radius: 8px; }
          .detail-header h2 { margin-bottom: 4px; }
          .detail-tabs {
            display: grid;
            gap: 14px;
            margin-bottom: 18px;
          }
          .tab-list {
            display: flex;
            gap: 2px;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 10;
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255, 255, 255, .96);
            padding: 6px;
            box-shadow: 0 8px 18px rgba(15, 23, 42, .06);
          }
          .tab-button { flex: 0 0 auto; white-space: nowrap; }
          .tab-button[aria-selected="true"] {
            background: var(--blue);
            border-color: var(--blue);
            color: #fff;
            font-weight: 700;
          }
          .tab-panel[hidden] { display: none; }
          .tab-panel {
            display: grid;
            gap: 18px;
          }
          .extension-tab-button::after {
            content: "追加";
            display: inline-flex;
            margin-left: 7px;
            border: 1px solid currentColor;
            border-radius: 999px;
            padding: 1px 5px;
            font-size: 10px;
            font-weight: 800;
            line-height: 1.2;
            opacity: .78;
          }
          html[lang="en"] .extension-tab-button::after { content: "Add-on"; }
          .extension-overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
          .extension-overview-card {
            border: 1px solid #bed6c6;
            border-left: 5px solid #2f7d57;
            border-radius: 8px;
            padding: 16px;
            background: linear-gradient(135deg, #f4faf6, #fff);
          }
          .extension-overview-card.water { border-color: #b8d5e6; border-left-color: #2477a8; background: linear-gradient(135deg, #eff8fc, #fff); }
          .extension-overview-card.sun { border-color: #ead5a2; border-left-color: #b87818; background: linear-gradient(135deg, #fff9e8, #fff); }
          .extension-overview-card.neutral { border-color: var(--line); border-left-color: #64748b; background: #fff; }
          .extension-overview-card h3 { margin: 0 0 6px; font-size: 18px; }
          .extension-overview-card p { margin: 0; color: #34463a; line-height: 1.75; }
          .extension-shell { overflow: hidden; border-top: 5px solid #2f7d57; }
          .extension-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
          .extension-heading h2 { margin-bottom: 5px; font-size: 25px; }
          .extension-origin { flex: 0 0 auto; border-radius: 999px; background: #edf6f0; color: #245d43; padding: 6px 10px; font-size: 12px; font-weight: 800; }
          .extension-blocks { display: grid; gap: 16px; }
          .extension-block { border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: #fff; }
          .extension-block > h3 { margin: 0 0 12px; font-size: 18px; }
          .extension-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
          .extension-metric { display: grid; gap: 4px; min-height: 96px; align-content: center; border-radius: 8px; background: #f3f8f4; padding: 13px; }
          .extension-metric span { color: #52655a; font-size: 13px; font-weight: 700; }
          .extension-metric strong { color: #173c2a; font-size: 24px; }
          .extension-process { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px; counter-reset: extension-step; }
          .extension-process-step { position: relative; min-height: 150px; border: 1px solid #c8d9cd; border-radius: 8px; background: #f7fbf8; padding: 42px 12px 12px; counter-increment: extension-step; }
          .extension-process-step::before { content: counter(extension-step); position: absolute; top: 10px; left: 12px; display: grid; place-items: center; width: 25px; height: 25px; border-radius: 999px; background: #2f7d57; color: #fff; font-size: 13px; font-weight: 900; }
          .extension-process-step:not(:last-child)::after { content: "›"; position: absolute; z-index: 1; top: 56px; right: -9px; color: #2f7d57; font-size: 26px; font-weight: 900; }
          .extension-process-step strong { display: block; margin-bottom: 6px; color: #173c2a; }
          .extension-process-step p { margin: 0; color: #4d5f54; font-size: 13px; line-height: 1.65; }
          .extension-callout { border-left: 5px solid #2f7d57; background: #f3f9f5; }
          .extension-callout.water { border-left-color: #2477a8; background: #eff8fc; }
          .extension-callout.sun { border-left-color: #b87818; background: #fff9e8; }
          .extension-callout.neutral { border-left-color: #64748b; background: #f8fafc; }
          .extension-callout p { margin: 0; line-height: 1.75; }
          .priority-panel { border-top: 4px solid #166534; }
          .priority-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 16px 0 10px; }
          .priority-heading h3 { margin: 0; font-size: 16px; }
          .readiness-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
          .readiness-card { min-height: 104px; padding: 12px; border: 1px solid #d7e0d9; border-top: 4px solid #98a69d; border-radius: 7px; background: #fff; }
          .readiness-card.good { border-top-color: #2b805c; }
          .readiness-card.warn { border-top-color: #c27b2d; }
          .readiness-card span, .readiness-card small { display: block; color: var(--muted); }
          .readiness-card strong { display: block; margin: 5px 0; font-size: 18px; }
          .metric.priority { border-color: #166534; background: #f0f8f2; }
          .metric.priority .value { color: #14532d; font-size: 28px; }
          .location-list { display: grid; border-top: 1px solid var(--line); }
          .location-row { display: grid; grid-template-columns: minmax(220px, 1.1fr) minmax(0, 1fr) auto; gap: 16px; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--line); }
          .location-path { display: grid; gap: 4px; min-width: 0; }
          .location-path a { font-weight: 700; }
          .location-path small { color: var(--muted); }
          .relation-targets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
          .relation-targets > span { color: var(--muted); font-size: 12px; font-weight: 700; }
          .relation-targets a { display: inline-flex; border: 1px solid #b9d1c2; border-radius: 5px; background: #f1f8f3; color: #14532d; padding: 5px 8px; font-size: 13px; }
          .location-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
          .location-actions a { display: inline-flex; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text); padding: 6px 9px; font-size: 13px; }
          .line-title { font-weight: 700; font-size: 15px; }
          .line-sub { color: var(--muted); font-size: 12px; margin-top: 3px; }
          .line-mask { color: var(--muted); font-size: 12px; white-space: nowrap; }
          .compact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .device-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 12px;
          }
          .device-list-search { display: grid; grid-template-columns: 20px minmax(0, 520px) auto; align-items: center; gap: 6px; margin: 12px 0; color: var(--muted); }
          .device-list-search::before { content: "⌕"; font-size: 18px; text-align: center; }
          .device-list-search input { min-height: 38px; }
          .device-list-search button { min-height: 38px; }
          .device-filter-empty { margin: 12px 0 0; }
          .device-result-summary { margin: 0 0 10px; color: var(--muted); font-size: 12px; }
          .device-catalog-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; }
          .device-catalog-head h2 { margin-bottom: 4px; }
          .camera-add-link { display: inline-flex; align-items: center; min-height: 38px; padding: 7px 12px; border: 1px solid var(--green); border-radius: 6px; color: #fff; background: var(--green); font-weight: 800; text-decoration: none; }
          .camera-add-link:hover { background: #166534; }
          .device-pagination { display: flex; align-items: center; justify-content: center; gap: 10px; margin-top: 14px; }
          .device-pagination a { padding: 7px 10px; border: 1px solid var(--line); border-radius: 5px; background: #fff; }
          .select-filter { display: grid; gap: 5px; max-width: 520px; margin: 0 0 9px; color: var(--muted); font-size: 12px; }
          .select-filter-empty { margin: 6px 0 0; color: var(--muted); font-size: 12px; }
          .device-tile {
            position: relative;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fff;
            overflow: hidden;
          }
          .device-tile.has-operational-error { border-color: #e11d48; box-shadow: inset 4px 0 0 #e11d48; }
          .device-tile[aria-current="true"] { border-color: var(--blue); box-shadow: inset 3px 0 0 var(--blue); }
          .device-tile.has-operational-error[aria-current="true"] { border-color: #e11d48; box-shadow: inset 4px 0 0 #e11d48; }
          .device-tile-link { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 14px 14px 52px; color: inherit; }
          .device-operational-alert {
            display: grid;
            gap: 5px;
            border: 1px solid #e11d48;
            border-left-width: 5px;
            border-radius: 7px;
            background: var(--red-bg);
            color: var(--red);
            padding: 12px 14px;
          }
          .device-operational-alert strong { font-size: 15px; }
          .device-operational-alert span { line-height: 1.55; }
          .device-operational-alert a { color: var(--red); font-weight: 800; text-decoration: underline; }
          .device-operational-alert.catalog-alert { margin: 12px 0; }
          .device-operational-alert.tile-alert { grid-column: 1 / -1; padding: 9px 11px; }
          .priority-panel > .device-operational-alert { margin-bottom: 16px; }
          .device-delete-button { position: absolute; right: 14px; bottom: 12px; min-height: 30px; border-color: var(--line); color: var(--muted); background: #fff; font-size: 12px; }
          .device-delete-button:hover { border-color: #fecdd3; color: var(--red); background: var(--red-bg); }
          .camera-edit-link { position: absolute; left: 14px; bottom: 12px; display: inline-flex; align-items: center; min-height: 28px; padding: 0 9px; border: 1px solid var(--line); border-radius: 5px; color: var(--text); background: #fff; font-size: 12px; text-decoration: none; }
          .device-title { font-size: 16px; font-weight: 700; }
          .device-sub { color: var(--muted); font-size: 13px; margin-top: 2px; }
          .tile-metrics { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 6px; }
          .mini { background: #f8fafc; border-radius: 6px; padding: 8px; min-height: 58px; }
          .mini span { display: block; color: var(--muted); font-size: 12px; }
          .mini strong { display: block; margin-top: 3px; font-size: 14px; }
          .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 3px 9px;
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
          }
          .badge.good { background: var(--green-bg); color: var(--green); }
          .badge.ok { background: #e0f2fe; color: #075985; }
          .badge.warn { background: var(--yellow-bg); color: var(--yellow); }
          .badge.danger { background: var(--red-bg); color: var(--red); }
          .badge.muted { background: var(--gray-bg); color: var(--muted); }
          .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 12px;
          }
          .metric {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fff;
            padding: 14px;
            min-height: 110px;
          }
          .metric .label { color: var(--muted); font-size: 13px; }
          .metric .value { display: block; margin-top: 8px; font-size: 24px; font-weight: 700; }
          .metric .hint { margin-top: 6px; color: var(--muted); font-size: 13px; }
          .metric-action { position: relative; display: block; color: inherit; text-decoration: none; transition: border-color .15s ease, transform .15s ease; }
          .metric-action:hover { border-color: var(--green); text-decoration: none; transform: translateY(-1px); }
          .metric-action-label { display: block; margin-top: 8px; color: var(--green); font-size: 12px; font-weight: 800; }
          .post-watering-setup-cta { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 14px; padding: 14px 16px; border: 1px solid #b9d6c6; border-radius: 10px; color: #174d36; background: linear-gradient(135deg, #f4fbf6, #e5f3e9); }
          .post-watering-setup-cta strong, .post-watering-setup-cta span { display: block; }
          .post-watering-setup-cta span { margin-top: 3px; color: var(--muted); font-size: 12px; }
          .post-watering-setup-cta a { flex: 0 0 auto; padding: 9px 13px; border-radius: 7px; color: #fff; background: var(--green); font-size: 12px; font-weight: 800; }
          .post-watering-setup-cta a:hover { text-decoration: none; background: #155640; }
          .section-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: 18px; align-items: start; }
          .list { display: grid; gap: 10px; }
          .list-row {
            display: grid;
            grid-template-columns: 150px 1fr;
            gap: 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px;
            background: #fff;
          }
          .list-time { color: var(--muted); font-size: 13px; }
          .list-main { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
          .schedule-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
          .schedule {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px;
            background: #fff;
          }
          .schedule strong { display: block; font-size: 20px; }
          .config-form { display: flex; flex-direction: column; gap: 16px; }
          .setup-journey { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 5px 0 2px; }
          .setup-step { position: relative; display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 11px; align-items: center; min-height: 82px; padding: 13px; overflow: hidden; border: 1px solid #cbdcd1; border-radius: 12px; color: #183f30; background: linear-gradient(145deg, #fbfefc, #edf6f0); text-decoration: none; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease; }
          .setup-step:hover { border-color: #5a9778; box-shadow: 0 8px 20px rgba(31, 83, 59, .12); text-decoration: none; transform: translateY(-2px); }
          .setup-step-number { position: absolute; top: 5px; right: 9px; color: #b8d2c2; font-size: 28px; font-weight: 900; }
          .setup-step-icon { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 12px; color: #21704f; background: #dff1e7; font-size: 24px; }
          .setup-step strong, .setup-step small { display: block; }
          .setup-step small { margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.35; }
          .setup-stage { scroll-margin-top: 16px; padding: 18px; border: 1px solid #d2ded6; border-radius: 12px; background: #fcfefd; }
          .setup-stage > h3:first-child { margin-top: 0; }
          .setup-stage-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
          .setup-stage-head h3 { margin: 0; }
          .setup-status-board { order: 0; }
          .connection-stage { order: 1; }
          .watering-rule-stage { order: 2; }
          .schedule-stage { order: 3; }
          .calibration-stage { order: 5; }
          .environment-stage { order: 6; }
          .advanced-settings { order: 8; }
          .config-form > details { order: 8; }
          .setup-save-bar { order: 9; padding: 12px; border: 1px solid #c7d8cd; border-radius: 12px; background: #f8fcf9; box-shadow: 0 10px 28px rgba(29, 61, 44, .09); }
          .setup-step-icon svg { width: 28px; height: 28px; }
          .firmware-workbench { display: grid; grid-template-columns: minmax(260px, .75fr) minmax(420px, 1.25fr); gap: 16px; align-items: start; }
          .firmware-current { display: grid; align-content: start; gap: 12px; padding: 18px; border: 1px solid #c8d8ce; border-radius: 9px; background: linear-gradient(145deg, #f8fcf9, #eaf3ed); }
          .firmware-current .version { color: #173f30; font-size: 34px; font-weight: 850; line-height: 1; }
          .firmware-current img { width: 100%; max-height: 150px; margin-top: auto; object-fit: cover; border-radius: 7px; }
          .firmware-upload-card { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--line); border-radius: 9px; background: #fff; }
          .firmware-dropzone { display: grid; place-items: center; min-height: 154px; padding: 18px; border: 2px dashed #79a68d; border-radius: 9px; color: #315d4c; background: #f4faf6; text-align: center; cursor: pointer; transition: .15s ease; }
          .firmware-dropzone:hover, .firmware-dropzone.dragover { border-color: #1f6b52; background: #e7f3eb; transform: translateY(-1px); }
          .firmware-dropzone strong { display: block; font-size: 16px; }
          .firmware-dropzone span { margin-top: 5px; color: var(--muted); font-size: 12px; }
          .firmware-dropzone input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
          .firmware-advanced { margin: 0; }
          .firmware-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
          .firmware-meta > div { padding: 9px; border-radius: 6px; background: #f5f7f5; }
          .firmware-meta span { display: block; color: var(--muted); font-size: 10px; }
          .firmware-meta strong { display: block; margin-top: 3px; overflow-wrap: anywhere; font-size: 12px; }
          #firmware-maintenance, #firmware-artifact-details { min-width: 0; max-width: 100%; }
          #firmware-artifact-details .detail-body { max-width: 100%; overflow-x: auto; }
          #firmware-artifact-details table { min-width: 1080px; }
          .config-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
          .config-field { min-width: 180px; flex: 1; }
          .threshold-control { display: grid; grid-template-columns: 1fr 86px; gap: 8px; align-items: center; }
          .switch-row {
            display: inline-flex;
            gap: 8px;
            align-items: center;
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 8px 10px;
            background: #fff;
            font-weight: 700;
          }
          .switch-row input { width: auto; }
          .schedule-editor, .mosfet-switch-editor { display: grid; gap: 10px; }
          .irrigation-mode-picker { display: grid; gap: 9px; margin: 14px 0; padding: 0; border: 0; }
          .irrigation-mode-picker legend { padding: 0; color: #264f3d; font-size: 13px; font-weight: 850; }
          .irrigation-mode-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
          .irrigation-mode-option { position: relative; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 9px; align-items: start; min-height: 82px; padding: 13px; border: 2px solid #d4dfd7; border-radius: 11px; background: #fff; cursor: pointer; transition: border-color .15s ease, background-color .15s ease, box-shadow .15s ease; }
          .irrigation-mode-option:hover { border-color: #7eaa91; background: #f7fbf8; }
          .irrigation-mode-option:has(input:checked) { border-color: #2d865d; color: #174f35; background: #eaf6ee; box-shadow: inset 0 0 0 1px #2d865d; }
          .irrigation-mode-option input { width: 19px; height: 19px; margin-top: 1px; accent-color: #27845a; }
          .irrigation-mode-option strong, .irrigation-mode-option small { display: block; }
          .irrigation-mode-option small { margin-top: 4px; color: var(--muted); font-size: 11px; font-weight: 500; line-height: 1.45; }
          .irrigation-mode-settings { display: grid; gap: 10px; margin-bottom: 13px; padding: 14px; border: 1px solid #bdd8c8; border-radius: 11px; background: #f2f9f4; }
          .irrigation-mode-settings[hidden], [data-schedule-duration-field][hidden] { display: none !important; }
          .irrigation-mode-settings .config-toolbar { align-items: start; }
          .irrigation-pattern-summary { margin: 0; padding: 10px 12px; border-radius: 8px; color: #245a41; background: #deefe4; font-size: 12px; font-weight: 750; }
          .irrigation-mode-note { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
          .output-routing { display: grid; grid-template-columns: minmax(220px, .65fr) minmax(360px, 1.35fr); gap: 14px; margin-top: 9px; padding: 14px; border: 1px solid #cddbd2; border-radius: 9px; background: #f8fbf8; }
          .output-routing-trigger { cursor: pointer; transition: border-color .16s ease, box-shadow .16s ease, background-color .16s ease; }
          .output-routing-trigger:hover { border-color: #6eaa89; background: #f3faf5; box-shadow: 0 10px 26px rgba(32, 94, 65, .12); }
          .output-routing-trigger:focus-visible { outline: 3px solid rgba(45, 123, 89, .28); outline-offset: 3px; border-color: #2d7b59; }
          .output-routing > img { width: 100%; height: 100%; min-height: 210px; object-fit: cover; border-radius: 7px; }
          .output-overview { display: grid; gap: 12px; align-content: start; }
          .output-overview-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
          .output-overview-head h4 { margin: 0; font-size: 16px; }
          .route-edit-prompt { display: inline-flex; align-items: center; gap: 5px; flex: 0 0 auto; padding: 6px 9px; border-radius: 999px; color: #286248; background: #e3f2e8; font-size: 11px; font-weight: 800; }
          .route-edit-prompt svg { width: 14px; height: 14px; }
          .output-routing-trigger:hover .route-edit-prompt { color: #fff; background: #2d7b59; }
          .switch-flow-board { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 16px; align-items: center; }
          .controller-node { display: grid; place-items: center; min-height: 112px; padding: 12px; border: 2px solid #4d846b; border-radius: 12px; color: #245740; background: #e4f1e8; font-weight: 800; text-align: center; }
          .switch-output-list { position: relative; display: grid; gap: 8px; }
          .switch-output { position: relative; display: grid; grid-template-columns: 10px 42px minmax(0, 1fr) auto; gap: 9px; align-items: center; min-height: 66px; padding: 9px 10px; border: 1px solid #d4ddd6; border-radius: 9px; background: #fff; }
          .switch-output::before { content: ""; position: absolute; left: -17px; width: 16px; border-top: 2px solid #8eb39e; }
          .switch-output.disabled { opacity: .58; background: #f5f6f5; }
          .switch-output.disabled::before { border-top-style: dashed; border-top-color: #b9c0bc; }
          .switch-output-dot { width: 10px; height: 10px; border-radius: 50%; background: #a6b0aa; }
          .switch-output.enabled .switch-output-dot { background: #2a8a5e; box-shadow: 0 0 0 4px #e2f3e9; }
          .switch-output-icon { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 10px; color: #256247; background: #e8f4ec; }
          .switch-output-icon svg { width: 30px; height: 30px; }
          .switch-output strong, .switch-output small { display: block; }
          .switch-output small { margin-top: 2px; color: var(--muted); }
          .switch-output .terminal { color: #315f4c; font-size: 11px; font-weight: 800; }
          .pump-program-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 14px; }
          .pump-program-card { overflow: hidden; border: 1px solid #d3ded6; border-radius: 11px; background: #fff; transition: border-color .15s ease, box-shadow .15s ease, opacity .15s ease; }
          .pump-program-card.enabled { border-color: #74a98a; box-shadow: 0 8px 22px rgba(38, 105, 72, .09); }
          .pump-program-card.disabled { opacity: .72; background: #f5f7f5; }
          .pump-program-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; }
          .pump-program-identity { display: grid; grid-template-columns: 40px minmax(0, 1fr); align-items: center; gap: 9px; min-width: 0; }
          .pump-program-icon { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 10px; background: #e8f4ec; font-size: 23px; }
          .pump-program-identity strong, .pump-program-identity small { display: block; }
          .pump-program-identity small { margin-top: 2px; color: var(--muted); font-size: 11px; }
          .pump-program-toggle { flex: 0 0 auto; }
          .pump-program-settings { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 12px; border-top: 1px solid #dce5df; background: #f6fbf7; }
          .pump-program-settings[hidden] { display: none !important; }
          .pump-program-settings .config-field { min-width: 0; }
          .pump-program-settings .threshold-control { grid-template-columns: minmax(0, 1fr) auto; }
          .definition-global-fields { margin-top: 12px; }
          .output-warning { grid-column: 1 / -1; margin: 0; }
          .config-dialog { width: min(760px, calc(100vw - 28px)); max-height: min(86vh, 840px); overflow: auto; padding: 0; border: 0; border-radius: 12px; box-shadow: 0 24px 70px rgba(20, 42, 30, .26); }
          .config-dialog.builder-dialog { width: min(1040px, calc(100vw - 28px)); }
          .config-dialog::backdrop { background: rgba(20, 36, 27, .56); }
          .dialog-head { position: sticky; top: 0; z-index: 2; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--line); background: #fff; }
          .dialog-head h3 { margin: 0; }
          .dialog-body { display: grid; gap: 14px; padding: 20px; }
          .dialog-actions { position: sticky; bottom: 0; display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--line); background: rgba(255, 255, 255, .97); }
          .builder-intro { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 12px; align-items: center; padding: 13px; border-radius: 11px; color: #265542; background: #e9f5ed; }
          .builder-intro-icon { display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; color: #fff; background: #2d7b59; font-size: 27px; }
          .output-edit-row { display: grid; grid-template-columns: 132px 74px minmax(0, 1fr); gap: 0; align-items: stretch; overflow: hidden; border: 1px solid #cbd9cf; border-radius: 14px; background: #fbfefc; transition: opacity .15s ease, border-color .15s ease, box-shadow .15s ease; }
          .output-edit-row.connected { border-color: #61a47f; box-shadow: 0 8px 22px rgba(33, 102, 70, .1); }
          .output-edit-row.disconnected { opacity: .72; background: #f3f5f3; }
          .builder-port-card { display: grid; align-content: center; justify-items: center; gap: 10px; min-height: 214px; padding: 16px 12px; color: #245c43; background: linear-gradient(160deg, #e7f4eb, #d7eadf); text-align: center; }
          .builder-port-card strong, .builder-port-card small { display: block; }
          .builder-port-card small { color: #587166; font-size: 11px; }
          .builder-port-symbol { display: grid; place-items: center; width: 58px; height: 58px; border: 3px solid #6d9f85; border-radius: 18px; background: #fff; font-size: 25px; box-shadow: inset 0 0 0 5px #edf7f0; }
          .builder-toggle { position: relative; display: grid; grid-template-columns: 35px auto; gap: 7px; align-items: center; cursor: pointer; font-size: 12px; font-weight: 800; }
          .builder-toggle input { position: absolute; width: 1px; height: 1px; opacity: 0; }
          .builder-toggle-track { position: relative; width: 35px; height: 21px; border-radius: 99px; background: #aab6af; transition: background .15s ease; }
          .builder-toggle-track::after { content: ""; position: absolute; top: 3px; left: 3px; width: 15px; height: 15px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, .2); transition: transform .15s ease; }
          .builder-toggle input:checked + .builder-toggle-track { background: #29865b; }
          .builder-toggle input:checked + .builder-toggle-track::after { transform: translateX(14px); }
          .builder-wire { position: relative; display: grid; place-items: center; min-height: 100%; overflow: hidden; }
          .builder-wire::before { content: ""; width: 100%; border-top: 4px dashed #b9c3bd; }
          .builder-wire::after { content: ""; position: absolute; right: 2px; width: 10px; height: 10px; border-radius: 50%; background: #b9c3bd; }
          .connected .builder-wire::before { border-top-style: solid; border-top-color: #34a36b; box-shadow: 0 0 8px rgba(42, 151, 96, .35); animation: wire-pulse 1.8s ease-in-out infinite; }
          .connected .builder-wire::after { background: #34a36b; box-shadow: 0 0 0 5px #dcf2e5; }
          @keyframes wire-pulse { 50% { border-color: #77c99c; } }
          .builder-endpoint { display: grid; gap: 13px; padding: 16px; }
          .builder-endpoint-head { display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 11px; align-items: center; }
          .builder-endpoint-preview { display: grid; place-items: center; width: 58px; height: 58px; border-radius: 15px; color: #1f6949; background: #e5f3e9; }
          .builder-endpoint-preview svg { width: 43px; height: 43px; }
          .builder-endpoint-head strong, .builder-endpoint-head small { display: block; }
          .builder-endpoint-head small { margin-top: 3px; color: var(--muted); }
          .builder-choice-label { display: block; margin-bottom: 7px; color: #52685d; font-size: 11px; font-weight: 800; }
          .equipment-type-grid, .equipment-target-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
          .equipment-target-grid { grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); }
          .equipment-card { display: grid; justify-items: center; gap: 5px; min-height: 92px; padding: 10px 8px; border: 2px solid #d5dfd8; border-radius: 11px; color: #294b3c; background: #fff; text-align: center; cursor: pointer; transition: border-color .14s ease, background .14s ease, transform .14s ease; }
          .equipment-card:hover:not(:disabled) { border-color: #79ac90; transform: translateY(-1px); }
          .equipment-card[aria-pressed="true"] { border-color: #2d8a5d; color: #19583b; background: #e6f5eb; box-shadow: inset 0 0 0 1px #2d8a5d; }
          .equipment-card:disabled { cursor: not-allowed; filter: grayscale(.8); opacity: .48; }
          .equipment-card svg { width: 38px; height: 38px; }
          .equipment-card strong { font-size: 12px; }
          .equipment-card small { color: var(--muted); font-size: 10px; line-height: 1.25; }
          .equipment-target-card { min-height: 72px; align-content: center; grid-template-columns: 30px minmax(0, 1fr); justify-items: start; text-align: left; }
          .equipment-target-card svg { width: 28px; height: 28px; }
          .equipment-target-card span { min-width: 0; }
          .equipment-target-card strong, .equipment-target-card small { display: block; overflow-wrap: anywhere; }
          .builder-name-details { margin: 0; }
          .builder-name-details .detail-body { padding-top: 10px; }
          .sensor-rack { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
          .sensor-device-card { overflow: hidden; border: 2px solid #d4dfd8; border-radius: 14px; background: #fff; transition: border-color .16s ease, box-shadow .16s ease; }
          .sensor-device-card[hidden], .sensor-device-body[hidden], [data-env-sensor-advanced][hidden] { display: none !important; }
          .sensor-device-card.active { border-color: #4a9870; box-shadow: 0 9px 24px rgba(35, 102, 70, .12); }
          .sensor-device-head { display: grid; grid-template-columns: 66px minmax(0, 1fr) auto; gap: 12px; align-items: center; min-height: 98px; padding: 14px; background: linear-gradient(145deg, #f9fcfa, #edf5f0); }
          .sensor-device-head strong, .sensor-device-head small { display: block; }
          .sensor-device-head > span:nth-child(2) > strong { color: #194b35; font-size: 17px; }
          .sensor-device-head small { margin-top: 3px; color: var(--muted); font-size: 11px; }
          .sensor-device-illustration { display: grid; place-items: center; width: 66px; height: 66px; border-radius: 20px; }
          .sensor-device-illustration.par { color: #956b14; background: linear-gradient(145deg, #fff8d9, #f8e9aa); }
          .sensor-device-illustration.soil { color: #6d5835; background: linear-gradient(145deg, #f4ead8, #dce9d6); }
          .sensor-device-illustration svg { width: 48px; height: 48px; }
          .sensor-power-switch { display: grid; justify-items: center; gap: 5px; min-width: 70px; color: var(--muted); cursor: pointer; font-size: 10px; font-weight: 800; }
          .sensor-power-switch input { position: absolute; width: 1px; height: 1px; opacity: 0; }
          .sensor-power-track { position: relative; width: 48px; height: 28px; border-radius: 99px; background: #aab6af; box-shadow: inset 0 1px 3px rgba(0, 0, 0, .18); transition: background .15s ease; }
          .sensor-power-track::after { content: ""; position: absolute; top: 4px; left: 4px; width: 20px; height: 20px; border-radius: 50%; background: #fff; box-shadow: 0 2px 5px rgba(0, 0, 0, .22); transition: transform .15s ease; }
          .sensor-power-switch input:checked + .sensor-power-track { background: #2a8d5e; }
          .sensor-power-switch input:checked + .sensor-power-track::after { transform: translateX(20px); }
          .sensor-device-body { display: grid; gap: 12px; padding: 14px; border-top: 1px solid #d7e1da; }
          .sensor-live-strip { display: grid; grid-template-columns: 12px minmax(0, 1fr); gap: 9px; align-items: center; padding: 10px; border-radius: 9px; color: #315e4a; background: #edf7f0; }
          .sensor-live-strip strong, .sensor-live-strip small { display: block; }
          .sensor-live-strip small { color: var(--muted); font-size: 10px; }
          .sensor-live-dot { width: 10px; height: 10px; border-radius: 50%; background: #31a16a; box-shadow: 0 0 0 5px #d8efe2; }
          .sensor-tune-button { display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 9px; align-items: center; min-height: 70px; padding: 10px 12px; border: 2px solid #c8dbcf; border-radius: 11px; color: #245a41; background: #fff; text-align: left; }
          .sensor-tune-button > span:first-child { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 12px; background: #e9f4ec; font-size: 22px; }
          .sensor-tune-button strong, .sensor-tune-button small { display: block; }
          .sensor-tune-button small { color: var(--muted); font-size: 10px; }
          .sensor-adjustment-value { display: inline-flex !important; width: fit-content; margin-top: 5px; padding: 3px 7px; border-radius: 99px; color: #5d665f; background: #eef1ef; font-size: 10px; font-weight: 850; line-height: 1.2; }
          .sensor-adjustment-value.recorded { color: #185f3e; background: #dff2e6; }
          .sensor-tune-button:hover { border-color: #4a9870; background: #f3faf5; }
          .soil-metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; }
          .soil-metric-grid button { display: grid; justify-items: center; align-content: center; gap: 4px; min-height: 70px; padding: 7px 5px; border: 2px solid #d8e0da; border-radius: 10px; background: #fff; }
          .soil-metric-grid button:hover, .soil-metric-grid button[aria-pressed="true"] { border-color: #3f966a; color: #1f6545; background: #e9f6ed; }
          .soil-metric-grid button span { display: grid; place-items: center; width: 31px; height: 31px; border-radius: 50%; color: #275d44; background: #edf4ef; font-size: 12px; font-weight: 900; }
          .soil-metric-grid button strong { font-size: 10px; }
          .soil-metric-grid button .sensor-adjustment-value { min-height: 18px; margin-top: 1px; padding: 3px 5px; text-align: center; overflow-wrap: anywhere; }
          .sensor-tuning-bench { --dial-progress: 0deg; display: grid; gap: 16px; margin-top: 14px; padding: 18px; border: 2px solid #64a581; border-radius: 15px; background: linear-gradient(145deg, #fbfefc, #eaf5ee); box-shadow: 0 12px 28px rgba(30, 95, 62, .12); }
          .sensor-calibration-dialog { width: min(720px, calc(100vw - 28px)); }
          .sensor-calibration-dialog .sensor-tuning-bench { margin: 0; border: 0; border-radius: 0; box-shadow: none; }
          .sensor-bench-head { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 15px; align-items: center; }
          .sensor-bench-head strong, .sensor-bench-head small, .sensor-bench-head span { display: block; }
          .sensor-bench-head > span:last-child > small { color: #2d7655; font-weight: 900; letter-spacing: .05em; }
          .sensor-bench-head > span:last-child > strong { margin-top: 2px; color: #153f2e; font-size: 21px; }
          .sensor-bench-head > span:last-child > span { margin-top: 4px; color: var(--muted); font-size: 12px; }
          .sensor-bench-dial { position: relative; display: grid !important; place-items: center; width: 86px; height: 86px; border-radius: 50%; color: #1c6545; background: conic-gradient(#2f9a68 var(--dial-progress), #d9e5dd 0); box-shadow: inset 0 0 0 8px #f8fcf9, 0 5px 15px rgba(24, 78, 51, .15); font-size: 17px; font-weight: 900; }
          .sensor-bench-dial::before { content: ""; position: absolute; inset: 17px; border-radius: 50%; background: #fff; }
          .sensor-bench-dial span { position: relative; }
          .sensor-range-control { display: grid; gap: 8px; padding: 14px; border-radius: 12px; background: #fff; }
          .sensor-range-control > label { color: #315d49; font-size: 12px; font-weight: 850; }
          .sensor-range-readout { display: flex; align-items: baseline; justify-content: center; gap: 7px; color: #174d34; }
          .sensor-range-readout output { font-size: 36px; font-weight: 900; line-height: 1; }
          .sensor-range-readout span { color: var(--muted); font-size: 13px; font-weight: 800; }
          .sensor-range-control input[type="range"] { width: 100%; accent-color: #27875b; }
          .sensor-range-scale { display: flex; justify-content: space-between; color: var(--muted); font-size: 10px; }
          .sensor-bench-actions { display: flex; justify-content: flex-end; gap: 8px; }
          .sensor-maintenance-details { margin-top: 12px; }
          .sensor-maintenance-intro { grid-column: 1 / -1; margin: 0; padding: 10px 12px; border-radius: 8px; color: #5f5a42; background: #fff9df; font-size: 12px; }
          .sensor-maintenance-details [data-env-sensor-advanced] { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; grid-column: 1 / -1; padding: 10px; border: 1px solid #e0e6e2; border-radius: 9px; }
          .calibration-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 15px; border: 1px solid #cddbd2; border-radius: 9px; background: #f8fbf8; }
          .calibration-card h3 { margin: 0 0 4px; }
          .calibration-status { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; }
          .guide-steps { display: grid; gap: 12px; counter-reset: guide-step; }
          .guide-step { position: relative; min-height: 74px; padding: 13px 14px 13px 58px; border: 1px solid var(--line); border-radius: 9px; background: #fff; }
          .guide-step::before { counter-increment: guide-step; content: counter(guide-step); position: absolute; left: 14px; top: 14px; display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; color: #fff; background: var(--green); font-weight: 850; }
          .guide-step strong, .guide-step span { display: block; }
          .guide-step span { margin-top: 4px; color: var(--muted); font-size: 13px; }
          .schedule-row {
            display: grid;
            grid-template-columns: minmax(120px, .8fr) minmax(130px, .8fr) minmax(130px, .8fr) auto;
            gap: 10px;
            align-items: end;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px;
            background: #fff;
          }
          .schedule-row.has-spacing-conflict { border-color: #d97706; box-shadow: inset 4px 0 0 #d97706; background: #fffbeb; }
          .schedule-row.is-spacing-target [data-schedule-time] { border-color: #b45309; background: #fff7ed; box-shadow: 0 0 0 2px rgba(217, 119, 6, .2); }
          .schedule-row-warning { grid-column: 1 / -1; margin: 0; padding: 9px 11px; border-radius: 7px; color: #7c2d12; background: #ffedd5; font-size: 12px; font-weight: 750; line-height: 1.55; }
          .schedule-spacing-guide { display: grid; gap: 8px; margin: 12px 0; padding: 13px 14px; border: 1px solid #ead7a5; border-radius: 9px; color: #665122; background: #fffdf3; }
          .schedule-spacing-guide strong { color: #5b4514; }
          .schedule-spacing-guide p { margin: 0; font-size: 12px; line-height: 1.55; }
          .schedule-spacing-warning { margin: 10px 0; padding: 14px 16px; border: 2px solid #d97706; border-radius: 10px; color: #713f12; background: #fff7ed; }
          .schedule-spacing-warning:focus { outline: 3px solid rgba(217, 119, 6, .25); outline-offset: 3px; }
          .schedule-spacing-warning strong { display: block; margin-bottom: 5px; font-size: 15px; }
          .schedule-spacing-warning p { margin: 0; line-height: 1.55; }
          .schedule-spacing-warning ul { display: grid; gap: 7px; margin: 10px 0 0; padding-left: 20px; }
          .icon-button { min-width: 38px; }
          .chart-card { display: grid; gap: 10px; }
          .device-chart-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
          }
          .device-chart-heading h2 { margin: 0; }
          .chart-settings-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            min-width: 48px;
            min-height: 48px;
            flex: 0 0 auto;
            padding: 7px 10px;
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            color: var(--text);
            font-size: 14px;
            font-weight: 800;
            text-decoration: none;
          }
          .chart-settings-link:hover, .chart-settings-link:focus-visible { border-color: var(--blue); color: var(--blue); }
          .rs485-sensor-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
          .rs485-sensor-card { overflow: hidden; border: 1px solid var(--line); border-radius: 9px; background: #fff; }
          .rs485-sensor-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 13px 14px; background: #f8fafc; }
          .rs485-sensor-head strong, .rs485-sensor-head small { display: block; }
          .rs485-sensor-head small { margin-top: 3px; color: var(--muted); }
          .rs485-sensor-measurements { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1px; background: var(--line); border-top: 1px solid var(--line); }
          .rs485-sensor-measurement { min-height: 76px; padding: 11px 12px; color: inherit; background: #fff; text-decoration: none; }
          .rs485-sensor-measurement:hover { color: var(--green); background: #f3faf5; text-decoration: none; }
          .rs485-sensor-measurement span, .rs485-sensor-measurement strong { display: block; }
          .rs485-sensor-measurement span { color: var(--muted); font-size: 12px; }
          .rs485-sensor-measurement strong { margin-top: 5px; font-size: 18px; }
          .rs485-sensor-no-value { grid-column: 1 / -1; margin: 0; padding: 12px 14px; color: var(--muted); background: #fff; }
          .range-controls {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            margin-bottom: 4px;
          }
          .range-controls button.active { border-color: var(--blue); color: var(--blue); font-weight: 700; }
          .range-controls input { width: auto; min-width: 150px; }
          .chart-body { min-height: 360px; }
          .chart-loading { min-height: 360px; display: grid; place-items: center; color: var(--muted); background: #f8fafc; border: 1px dashed var(--line); border-radius: 8px; }
          .empty { color: var(--muted); background: #f8fafc; border: 1px dashed var(--line); border-radius: 8px; padding: 14px; }
          details {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fff;
            margin-bottom: 12px;
          }
          summary { cursor: pointer; padding: 13px 14px; font-weight: 700; }
          details .detail-body { border-top: 1px solid var(--line); padding: 14px; }
          .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; align-items: end; }
          label { display: block; font-weight: 700; margin-bottom: 5px; }
          input, select, textarea {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 14px;
            background: #fff;
          }
          textarea {
            min-height: 220px;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 13px;
          }
          .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
          table { border-collapse: collapse; width: 100%; margin-bottom: 14px; }
          th, td { border: 1px solid var(--line); padding: 7px 9px; vertical-align: top; font-size: 13px; }
          th { background: #f1f5f9; text-align: left; }
          pre { white-space: pre-wrap; word-break: break-word; background: #f8fafc; border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
          .muted { color: var(--muted); }
          .raw-json { margin-top: 10px; }
          @media (max-width: 900px) {
            .page { padding: 16px; }
            .topbar { display: block; }
            .nav { justify-content: flex-start; margin-top: 12px; }
            .detail-header { display: block; }
            .field-head { display: block; }
            .location-row { grid-template-columns: 1fr; }
            .location-actions { justify-content: flex-start; }
            .section-grid { grid-template-columns: 1fr; }
            .post-watering-setup-cta { align-items: stretch; flex-direction: column; }
            .post-watering-setup-cta a { text-align: center; }
            .tile-metrics { grid-template-columns: 1fr; }
            .list-row { grid-template-columns: 1fr; }
            .ridge-row { grid-template-columns: 1fr; }
            .ridge-meta { justify-content: flex-start; }
            .schedule-row { grid-template-columns: 1fr; }
            .irrigation-mode-options { grid-template-columns: 1fr; }
            .calibration-card { grid-template-columns: 1fr; }
            .tab-list { margin-inline: -16px; border-radius: 0; padding-inline: 16px; }
            .device-guide, .device-identity { grid-template-columns: 1fr; }
            .firmware-workbench { grid-template-columns: 1fr; }
            .firmware-meta { grid-template-columns: 1fr; }
            .readiness-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .connection-check-grid { grid-template-columns: 1fr; }
            .connection-check-card { min-height: auto; }
            .connection-event { grid-template-columns: 10px minmax(0, 1fr); align-items: start; }
            .connection-event p, .connection-event time { grid-column: 2; text-align: left; }
            .extension-process { grid-template-columns: 1fr; }
            .extension-process-step { min-height: auto; padding-left: 52px; padding-top: 13px; }
            .extension-process-step::before { top: 13px; }
            .extension-process-step:not(:last-child)::after { content: "↓"; top: auto; right: auto; bottom: -18px; left: 18px; }
            .output-routing, .switch-flow-board { grid-template-columns: 1fr; }
            .setup-journey { grid-template-columns: 1fr; }
            .sensor-rack { grid-template-columns: 1fr; }
            .output-edit-row { grid-template-columns: 92px 42px minmax(0, 1fr); }
            .builder-port-card { min-height: 100%; padding-inline: 8px; }
            .builder-port-symbol { width: 48px; height: 48px; }
            .equipment-type-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .switch-output::before { display: none; }
            .pump-program-list, .pump-program-settings { grid-template-columns: 1fr; }
            .device-guide img { max-height: 190px; border-top: 1px solid #c9d8ce; border-left: 0; }
            .device-identity img { width: 100%; max-height: 180px; }
          }
          @media (max-width: 560px) {
            .extension-heading { display: grid; }
            .extension-origin { justify-self: start; }
            .extension-metrics { grid-template-columns: 1fr 1fr; }
            .output-edit-row { grid-template-columns: 1fr; }
            .builder-port-card { grid-template-columns: auto minmax(0, 1fr) auto; justify-items: start; min-height: auto; text-align: left; }
            .builder-port-symbol { width: 43px; height: 43px; border-radius: 13px; }
            .builder-wire { min-height: 38px; }
            .builder-wire::before { width: 4px; height: 100%; border-top: 0; border-left: 4px dashed #b9c3bd; }
            .connected .builder-wire::before { border-left-style: solid; border-left-color: #34a36b; }
            .builder-wire::after { right: auto; bottom: 1px; }
            .builder-endpoint { padding: 14px 12px; }
            .equipment-target-grid { grid-template-columns: 1fr 1fr; }
            .sensor-device-head { grid-template-columns: 54px minmax(0, 1fr) auto; padding: 11px; }
            .sensor-device-illustration { width: 54px; height: 54px; border-radius: 16px; }
            .sensor-device-illustration svg { width: 40px; height: 40px; }
            .soil-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .sensor-bench-head { grid-template-columns: 68px minmax(0, 1fr); }
            .sensor-bench-dial { width: 66px; height: 66px; box-shadow: inset 0 0 0 6px #f8fcf9, 0 5px 15px rgba(24, 78, 51, .15); font-size: 13px; }
            .sensor-bench-dial::before { inset: 14px; }
            .sensor-bench-actions { align-items: stretch; flex-direction: column-reverse; }
            .sensor-bench-actions button { width: 100%; }
            .sensor-maintenance-details [data-env-sensor-advanced] { grid-template-columns: 1fr; }
            .setup-save-bar .actions { align-items: stretch; }
            .setup-save-bar button { width: 100%; }
          }
        </style>
        <link rel="stylesheet" href="/static/hub-ui.css">
      </head>
      <body class="hub-shell hub-device-maintenance {{ accessibility_body_class }}">
        <div class="page">
          <div id="global-progress" class="progress-banner" role="status" aria-live="polite">
            <span class="progress-dot" aria-hidden="true"></span>
            <span id="global-progress-message">処理中...</span>
          </div>
          {% set page_selected = admin_view.selected %}
          <div class="topbar">
            <div>
              <p class="muted">{% if is_detail_page %}<a href="{{ list_path }}">機器一覧</a> / {{ page_selected.title }}{% else %}<a href="/fields">圃場一覧</a> / 機器保守{% endif %}</p>
              <h1>{{ page_selected.title if is_detail_page else '機器保守' }}</h1>
              <p class="lead">{{ '現在値、出力先、動作設定、機器更新を確認します。' if is_detail_page else '圃場で使う機器を、設置場所と現在状態から探します。' }}</p>
            </div>
            <nav class="nav" aria-label="ページ移動">
              <a href="/fields">圃場一覧</a>
            </nav>
          </div>
          {% if demo_mode %}
          <div class="notice"><strong>デモデータ表示中</strong> 操作は保存されません。UI/UX 確認専用です。<a href="/mqtt-devices">実データへ戻る</a></div>
          {% endif %}
          {% if is_detail_page %}
          <div id="action-result" class="result"{% if not demo_mode %} hidden{% endif %}>{{ "デモモードです。操作しても保存されません。" if demo_mode else "" }}</div>
          {% endif %}

          {% if not is_detail_page %}<section class="device-guide"><div class="device-guide-copy"><span>DEVICE CARE</span><h2>まず、場所と状態を見る</h2><p>日常の確認は圃場ビューから。ここでは機器を横断検索し、交換・設定・更新などの保守を行います。</p></div><img src="/static/ui-illustrations/device-family.png" alt="圃場で使うセンサーと制御機器のイラスト"></section>{% endif %}

          {% if not is_detail_page and admin_view.field_zones %}
          <section class="field-section" aria-label="圃場ビュー">
            <div class="field-head">
              <div>
                <h2>圃場ビュー</h2>
                <p class="lead">場所ごとに水やり機をまとめ、畝や点滴ラインの状態として確認します。</p>
              </div>
              <span class="badge muted">{{ admin_view.devices|length }} 台</span>
            </div>
            <div class="field-map">
              {% for zone in admin_view.field_zones %}
              <a class="field-zone {{ zone.class }}" href="{{ device_link_prefix }}{{ zone.primary_device_id }}" aria-current="{{ 'true' if zone.selected else 'false' }}">
                <div class="zone-top">
                  <span class="zone-name">{{ zone.name }}</span>
                  <span class="badge {{ zone.class }}">{{ zone.device_count }} 台</span>
                </div>
                <div class="ridge-stack">
                  {% for row in zone.rows %}
                  <div class="ridge-row {{ row.class }}" aria-current="{{ 'true' if row.selected else 'false' }}">
                    <span class="ridge-name">{{ row.name }}</span>
                    <span class="ridge-meta">
                      <span>{{ row.kind_label }}</span>
                      <span>{{ row.soil }}</span>
                      <span>{{ row.watering }}</span>
                    </span>
                  </div>
                  {% endfor %}
                  {% for _ in zone.empty_rows %}
                  <div class="ridge-empty" aria-hidden="true"></div>
                  {% endfor %}
                </div>
              </a>
              {% endfor %}
            </div>
          </section>
          {% endif %}

          {% if not is_detail_page %}
          <section class="panel">
            <div class="device-catalog-head"><div class="context-help-row"><h2>機器一覧</h2><details class="context-help left"><summary aria-label="機器一覧の使い方を開く" title="機器一覧の使い方">?</summary><div class="context-help-panel" role="note"><strong>機器一覧の使い方</strong><p>登録した機器とネットワークカメラを確認できます。名前や設置場所で検索できます。</p></div></details></div>{% if not demo_mode %}<a class="camera-add-link" href="/cameras/new">＋ カメラを登録</a>{% endif %}</div>
            <form class="device-list-search" id="device-list-search-form" method="get" action="{{ list_path }}">
              <input id="device-list-search" name="q" type="search" value="{{ device_query }}" placeholder="機器名、ID、種別、設置場所を検索" aria-label="機器を検索" autocomplete="off">
              <button type="submit">検索</button>
            </form>
            {% if admin_view.operational_error_count %}
            <div class="device-operational-alert catalog-alert" role="alert">
              <strong>運転異常：{{ admin_view.operational_error_count }}台の機器で予定した動作を実行できませんでした</strong>
              <span>赤く表示された機器を開き、原因と対処を確認してください。</span>
            </div>
            {% endif %}
            <p class="device-result-summary" id="device-result-summary">{{ (device_catalog.total | int) + (camera_devices | length) }}件中 {{ (admin_view.devices | length) + (camera_devices | length) }}件を表示 / {{ device_catalog.page }}ページ</p>
            {% if admin_view.devices or camera_devices %}
            <div class="device-grid" id="device-list-grid">
              {% for device in admin_view.devices %}
              <article class="device-tile{% if device.operational_error %} has-operational-error{% endif %}" aria-current="{{ 'true' if device.id == selected_device_id else 'false' }}" data-device-id="{{ device.id }}">
                <a class="device-tile-link" href="{{ device_link_prefix }}{{ device.id }}">
                <div>
                  <div class="device-title">{{ device.name }}</div>
                  <div class="device-sub">{{ device.kind_label }} / {{ device.location }}</div>
                </div>
                <div>
                  <span class="badge {{ 'danger' if device.operational_error else device.state_class }}">{{ '運転異常' if device.operational_error else 'Hub登録：' ~ device.state_label }}</span>
                </div>
                {% if device.operational_error %}
                <div class="device-operational-alert tile-alert" role="alert">
                  <strong>予定した動作を実行できませんでした</strong>
                  <span>{{ device.operational_error.reason_labels | join(' / ') }}　原因と対処を確認する →</span>
                </div>
                {% endif %}
                <div class="tile-metrics">
                  {% for metric in device.operational_metrics %}<div class="mini"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div>{% endfor %}
                </div>
                </a>
                {% if not demo_mode %}<button type="button" class="device-delete-button" data-delete-device="{{ device.id }}" data-delete-device-name="{{ device.name }}">一覧から削除</button>{% endif %}
              </article>
              {% endfor %}
              {% for camera in camera_devices %}
              <article class="device-tile" data-camera-id="{{ camera.id }}">
                <a class="device-tile-link" href="{{ camera.detail_url or camera.preview_url }}">
                  <div>
                    <div class="device-title">{{ camera.name }}</div>
                    <div class="device-sub">ネットワークカメラ / {{ camera.camera_type }}</div>
                  </div>
                  <div><span class="badge good">登録済み</span></div>
                  <div class="tile-metrics">
                    <div class="mini"><span>接続先</span><strong>{{ camera.ip_address }}</strong></div>
                    <div class="mini"><span>ストリーム</span><strong>{{ camera.stream }}</strong></div>
                    <div class="mini"><span>タイムラプス</span><strong>{{ "有効" if camera.timelapse else "無効" }}</strong></div>
                  </div>
                </a>
                <a class="camera-edit-link" href="{{ camera.settings_url or '/camera/' ~ camera.id ~ '#settings' }}">設定</a>
                <button type="button" class="device-delete-button" data-delete-camera="{{ camera.id }}" data-delete-camera-name="{{ camera.name }}">登録を解除</button>
              </article>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty">{% if device_query %}一致する機器はありません。{% else %}まだ機器が登録されていません。{% endif %}</div>
            {% endif %}
            {% if device_catalog.has_previous or device_catalog.has_next %}<nav class="device-pagination" aria-label="機器一覧ページ">{% if device_catalog.previous_url %}<a href="{{ device_catalog.previous_url }}">前へ</a>{% endif %}<span>{{ device_catalog.page }} / {{ device_catalog.page_count }}</span>{% if device_catalog.next_url %}<a href="{{ device_catalog.next_url }}">次へ</a>{% endif %}</nav>{% endif %}
          </section>
          {% endif %}

          {% if is_detail_page and admin_view.selected %}
          {% set selected = admin_view.selected %}
          <section class="panel priority-panel">
            {% if selected.operational_error %}
            <div class="device-operational-alert" role="alert">
              <strong>運転異常：予定した動作を実行できませんでした</strong>
              <span>{{ selected.operational_error.reason_labels | join(' / ') }}{% if selected.operational_error.batch_skip_reason %} / 実行しなかった理由: {{ selected.operational_error.batch_skip_reason }}{% endif %}</span>
              <a href="{{ device_link_prefix }}{{ selected.id }}?tab=maintenance#operational-error-details">原因と対処を確認する →</a>
            </div>
            {% endif %}
            <div class="device-identity"><div class="detail-header">
              <div>
                <h2>{{ selected.title }}</h2>
                <p class="lead">{{ selected.kind_label }} / {% if selected.location_href %}<a href="{{ selected.location_href }}" target="_blank" rel="noopener" aria-label="{{ selected.location }}を新しいタブで開く">{{ selected.location }} ↗</a>{% else %}{{ selected.location }}{% endif %}</p>
                {% if selected.memo %}<p>{{ selected.memo }}</p>{% endif %}
                <details class="advanced-info identity-details"><summary>機器番号を確認（上級者向け）</summary><div class="detail-body"><code>{{ selected.id }}</code><p class="muted">問い合わせや機器交換のときに使用する識別番号です。</p></div></details>
              </div>
              <span class="badge {{ selected.state_class }}">Hub登録：{{ selected.state_label }}</span>
            </div><img src="/static/ui-illustrations/device-family.png" alt="農業用センサーと制御機器のイラスト"></div>
            <div class="priority-heading"><h3>{{ selected.operational_heading }}</h3><span class="muted">運用判断に必要な情報</span></div>
            <div class="metrics">
              {% for metric in selected.operational_metrics %}
              {% if metric.settings_anchor %}<a class="metric metric-action {{ metric.class }}" href="{{ device_link_prefix }}{{ selected.id }}?tab=settings#{{ metric.settings_anchor }}" aria-label="{{ metric.label }}の設定を変更">{% elif metric.history_anchor %}<a class="metric metric-action {{ metric.class }}" href="{{ device_link_prefix }}{{ selected.id }}?tab=monitoring#{{ metric.history_anchor }}" aria-label="{{ metric.label }}の履歴を見る">{% else %}<div class="metric {{ metric.class }}">{% endif %}
                <span class="label">{{ metric.label }}</span>
                <span class="value">{% if metric.class in ['good', 'ok', 'warn', 'danger', 'muted'] %}<span class="badge {{ metric.class }}">{{ metric.value }}</span>{% else %}{{ metric.value }}{% endif %}</span>
                <div class="hint">{{ metric.hint }}</div>
                {% if metric.settings_anchor %}<span class="metric-action-label">設定を変更 →</span>{% elif metric.history_anchor %}<span class="metric-action-label">推移を見る →</span>{% endif %}
              {% if metric.settings_anchor or metric.history_anchor %}</a>{% else %}</div>{% endif %}
              {% endfor %}
            </div>
            {% if not demo_mode and (selected.supports_irrigation or selected.supports_fertigation) %}
            <div class="post-watering-setup-cta">
              <div><strong>潅水後に、水が届いたかDiscordで確認</strong><span>判定に使う土壌水分センサーと、潅水後の最低水分率を案内に沿って設定します。</span></div>
              <a href="{{ selected.post_watering_setup_url }}">設定ウィザードを開く →</a>
            </div>
            {% endif %}
          </section>

          <div class="detail-tabs">
            <div class="tab-list" role="tablist" aria-label="機器詳細メニュー">
              <button type="button" class="tab-button" data-tab-key="overview" data-tab-target="tab-overview" role="tab" aria-controls="tab-overview" aria-selected="true" tabindex="0">概要</button>
              <button type="button" class="tab-button" data-tab-key="monitoring" data-tab-target="tab-monitoring" role="tab" aria-controls="tab-monitoring" aria-selected="false" tabindex="-1">現在値・履歴</button>
              <button type="button" class="tab-button" data-tab-key="settings" data-tab-target="tab-config" role="tab" aria-controls="tab-config" aria-selected="false" tabindex="-1">動作設定</button>
              <button type="button" class="tab-button" data-tab-key="firmware" data-tab-target="tab-firmware" role="tab" aria-controls="tab-firmware" aria-selected="false" tabindex="-1">機器を更新</button>
              <button type="button" class="tab-button" data-tab-key="maintenance" data-tab-target="tab-maintenance" role="tab" aria-controls="tab-maintenance" aria-selected="false" tabindex="-1">保守・管理{% if selected.operational_error %} ⚠{% endif %}</button>
              {% for extension in selected.ui_extensions %}{% for extension_tab in extension.tabs %}<button type="button" class="tab-button extension-tab-button" data-tab-key="{{ extension_tab.key }}" data-tab-target="{{ extension_tab.dom_id }}" role="tab" aria-controls="{{ extension_tab.dom_id }}" aria-selected="false" tabindex="-1">{{ extension_tab.label }}</button>{% endfor %}{% endfor %}
            </div>

            <section id="tab-overview" class="tab-panel" role="tabpanel">
              <section class="panel" aria-label="設置場所と関連先">
                <div class="field-head">
                  <div>
                    <h2>設置場所・関連先</h2>
                    <p class="lead">圃場の設置ビューを正本として、機器の設置先と作用対象を表示します。</p>
                  </div>
                  <span class="badge {{ 'good' if selected.layout_context.assigned else 'muted' }}">{{ selected.layout_context.assignments|length }} 箇所</span>
                </div>
                {% if selected.layout_context.assignments %}
                <div class="location-list">
                  {% for assignment in selected.layout_context.assignments %}
                  <div class="location-row">
                    <div class="location-path">
                      <a href="{{ assignment.href }}" target="_blank" rel="noopener" aria-label="{{ assignment.path }}を新しいタブで開く">{{ assignment.path }} ↗</a>
                      <small>{{ assignment.placement_kind }}{% if not assignment.field_level %} / {{ assignment.resource_name }}{% endif %}</small>
                    </div>
                    <div class="relation-targets">
                      {% if assignment.targets %}<span>{{ assignment.relation_label }}</span>{% for target in assignment.targets %}<a href="{{ target.href }}" target="_blank" rel="noopener" title="{{ target.path }}を新しいタブで開く">{{ target.name }} ↗</a>{% endfor %}{% else %}<span>{{ assignment.relation_label }}は未設定</span>{% endif %}
                    </div>
                    <div class="location-actions"><a href="{{ assignment.field_href }}" target="_blank" rel="noopener" aria-label="圃場を新しいタブで開く">圃場を開く ↗</a><a href="{{ assignment.layout_href }}" target="_blank" rel="noopener" aria-label="設置ビューを新しいタブで開く">設置ビューを編集 ↗</a></div>
                  </div>
                  {% endfor %}
                </div>
                {% else %}
                <div class="empty">圃場の設置ビューに配置されていません。対象圃場の設置ビューから機器を紐づけてください。</div>
                {% endif %}
              </section>

              <section class="panel" aria-label="動作確認">
                <div class="field-head"><div class="context-help-row"><h2>動作確認</h2><details class="context-help left"><summary aria-label="動作確認の見方を開く" title="動作確認の見方">?</summary><div class="context-help-panel" role="note"><strong>動作確認の見方</strong><p>通信、設定、時刻、出力先を順番に確認します。橙色の項目だけ対応すれば運用を始められます。</p></div></details></div><a href="{{ device_link_prefix }}{{ selected.id }}?tab=settings">設定を確認</a></div>
                <div class="readiness-grid">{% for check in selected.readiness_checks %}<div class="readiness-card {{ check.class }}"><span>{{ check.label }}</span><strong>{{ check.value }}</strong><small>{{ check.hint }}</small></div>{% endfor %}</div>
              </section>

              {% for extension in selected.ui_extensions %}{% if extension.overview_cards %}
              <section class="panel" aria-label="{{ extension.name }}による追加情報">
                <div class="field-head"><div><h2>この機器の追加ガイド</h2><p class="lead">{{ extension.name }} が提供する補助情報です。</p></div><span class="extension-origin">Extension {{ extension.version }}</span></div>
                <div class="extension-overview-grid">
                  {% for card in extension.overview_cards %}<article class="extension-overview-card {{ card.tone or 'leaf' }}"><h3>{{ card.title }}</h3><p>{{ card.description }}</p></article>{% endfor %}
                </div>
              </section>
              {% endif %}{% endfor %}

              <div class="section-grid">
                {% if selected.supports_irrigation or selected.supports_fertigation %}
                <section class="panel">
                  <h2>{{ '液肥づくりの予約' if selected.supports_fertigation else '灌水予約' }}</h2>
                  {% if selected.scheduled_operation and selected.scheduled_operation.warning %}<p class="notice warn"><strong>{{ selected.scheduled_operation.value }}</strong><br>{{ selected.scheduled_operation.warning }}</p>{% endif %}
                  {% if selected.schedules %}
                  <div class="schedule-grid">
                    {% for schedule in selected.schedules %}
                    <div class="schedule">
                      <strong>{{ schedule.time }}</strong>
                      <div class="line-sub">{{ schedule.duration }} / {{ schedule.channel }}</div>
                      {% if schedule.state_label %}<span class="badge {{ schedule.state_class }}">{{ schedule.state_label }}</span>{% endif %}
                    </div>
                    {% endfor %}
                  </div>
                  {% else %}
                  <div class="empty">{{ '液肥づくり' if selected.supports_fertigation else '灌水' }}の予約はまだありません。</div>
                  {% endif %}
                </section>
                {% endif %}

                <section class="panel">
                  <h2>機器の通信・更新</h2>
                  <div class="compact-grid">
                    <div class="mini"><span>最終通信</span><strong>{{ selected.last_seen_age }}</strong></div>
                    <div class="mini"><span>次回起動</span><strong>{{ selected.next_wake }}</strong></div>
                    <div class="mini"><span>現在のバージョン</span><strong>{{ selected.firmware }}</strong></div>
                    <div class="mini"><span>更新状態</span><strong>{{ selected.ota_state }}</strong></div>
                  </div>
                </section>
              </div>
            </section>

            <section id="tab-config" class="tab-panel" role="tabpanel" hidden>
          <section class="panel">
            <div class="context-help-row"><h2>この機器の呼び名</h2><details class="context-help left"><summary aria-label="表示情報の説明を開く" title="表示情報について">?</summary><div class="context-help-panel" role="note"><strong>表示情報について</strong><p>圃場で見分けやすい名前と、覚えておきたいことだけを整えます。</p></div></details></div>
            <form id="metadata-form" data-stateful-form data-pristine-message="機器情報は変更されていません。"{% if selected_device.state == 'retired' %} data-state-blocked="true" data-blocked-message="廃止済みの機器情報は変更できません。"{% endif %}>
              <div class="form-grid">
                <div><label for="metadata-name">表示名</label><input id="metadata-name" name="name" type="text" value="{{ selected_device.name or '' }}"></div>
                <div><label for="metadata-memo">メモ</label><input id="metadata-memo" name="memo" type="text" value="{{ selected_device.memo or '' }}"></div>
              </div>
              <div class="actions"><span class="muted" data-stateful-reason></span><button type="submit" class="primary" data-stateful-submit>表示情報を保存</button></div>
            </form>
          </section>
          <section class="panel">
            <h2>{{ '水やりセットアップ' if selected.supports_irrigation else '液肥づくりセットアップ' if selected.supports_fertigation else '機器セットアップ' }}</h2>
            {% if selected.supports_irrigation %}
            <nav class="setup-journey" aria-label="水やりセットアップの手順">
              <a class="setup-step" href="#output-connections"><span class="setup-step-number">1</span><span class="setup-step-icon" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 16h8M18 16h8M12 11l6 5-6 5V11ZM20 11l-6 5 6 5V11Z"/></svg></span><span><strong>設備をつなぐ</strong><small>接続口から水の行き先を組み立てる</small></span></a>
              <a class="setup-step" href="#watering-rules"><span class="setup-step-number">2</span><span class="setup-step-icon" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M16 4C13 10 8 14 8 20a8 8 0 0 0 16 0c0-6-5-10-8-16Z"/></svg></span><span><strong>水やりを決める</strong><small>水分の目安と予約時刻を決める</small></span></a>
              <a class="setup-step" href="#soil-moisture-reference"><span class="setup-step-number">3</span><span class="setup-step-icon" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M16 27V13M16 18c-6 0-9-4-9-9 6 0 9 3 9 9ZM16 15c6 0 9-4 9-9-6 0-9 3-9 9ZM8 27h16"/></svg></span><span><strong>センサーを合わせる</strong><small>いつもの土に表示を合わせる</small></span></a>
            </nav>
            {% endif %}
            <form id="runtime-config-form" class="config-form" data-stateful-form data-pristine-message="動作設定は変更されていません。"{% if selected_device.state == 'retired' %} data-state-blocked="true" data-blocked-message="廃止済みの動作設定は変更できません。"{% endif %}>
              <div class="metrics setup-status-board">
                <div class="metric"{% if not selected.supports_irrigation %} hidden{% endif %}>
                  <span class="label">灌水しきい値</span>
                  <span class="value"><span id="threshold-display">{{ selected.config_summary.threshold }}</span></span>
                  <div class="hint">この値以下を灌水判定に使います</div>
                </div>
                <div class="metric"{% if not selected.supports_irrigation %} hidden{% endif %}>
                  <span class="label">強制灌水</span>
                  <span class="value"><span id="force-display">{{ selected.config_summary.force }}</span></span>
                  <div class="hint">ON の場合、条件に関わらず予約時刻に灌水します</div>
                </div>
                <div class="metric"{% if not selected.supports_irrigation %} hidden{% endif %}>
                  <span class="label">予約数</span>
                  <span class="value"><span id="schedule-count-display">{{ selected.config_summary.schedule_count }}</span></span>
                  <div class="hint">最大 8 件まで登録できます</div>
                </div>
                <span id="debug-log-display" hidden>{{ selected.config_summary.debug_log }}</span><span id="ota-interval-display" hidden>{{ selected.config_summary.ota_interval }}</span>
              </div>

              {% if selected.supports_fertigation %}
              <section id="fertigation-recipe" class="setup-stage">
                <div class="setup-stage-head"><div class="context-help-row"><h3>ポンプの時間設定</h3><details class="context-help left"><summary aria-label="時間指定運転の説明を開く" title="時間指定運転">?</summary><div class="context-help-panel" role="note"><strong>時間指定運転</strong><p>使用するポンプだけを有効にします。無効なポンプは繰り返し0回として保存され、保持した時間設定は再度有効にしたときに使えます。</p></div></details></div><span class="badge good">ポンプごとに設定</span></div>
                <p id="scheduled-operation-inline-warning" class="notice warn"{% if not selected.scheduled_operation.warning %} hidden{% endif %}>{{ selected.scheduled_operation.warning }}</p>
                <div class="config-toolbar definition-config-fields definition-global-fields">
                  {% for field in selected.definition.ui.configuration_fields %}
                  {% if not field.output_id %}{% if field.type == 'boolean' %}<label class="switch-row"><input type="checkbox" data-definition-path="{{ field.path }}" data-definition-type="boolean">{{ field.label }}</label>
                  {% else %}<div class="config-field"><label>{{ field.label }}</label><div class="threshold-control"><input type="number" data-definition-path="{{ field.path }}" data-definition-type="number" min="{{ field.min }}" max="{{ field.max }}" step="1"><span>{{ field.unit }}</span></div></div>{% endif %}{% endif %}
                  {% endfor %}
                </div>
                <div class="pump-program-list" aria-label="ポンプごとの時間設定">
                  {% for output in selected.output_settings.outputs %}
                  <article class="pump-program-card {{ 'enabled' if output.enabled else 'disabled' }}" data-timed-output-card="{{ output.switch_id }}">
                    <div class="pump-program-head">
                      <div class="pump-program-identity"><span class="pump-program-icon" aria-hidden="true">{{ ['🚰','🅰️','🅱️','🌀','🌱'][loop.index0] }}</span><span><strong>{{ output.role_label }}ポンプ</strong><small>{{ output.name }} / <span data-timed-output-summary>{{ output.program_summary }}</span></small></span></div>
                      <label class="switch-row pump-program-toggle" for="timed-output-enabled-{{ output.switch_id }}"><input id="timed-output-enabled-{{ output.switch_id }}" type="checkbox" data-timed-output-enabled aria-controls="timed-output-settings-{{ output.switch_id }}"{% if output.enabled %} checked{% endif %}>使用する</label>
                    </div>
                    <div id="timed-output-settings-{{ output.switch_id }}" class="pump-program-settings" data-timed-output-settings{% if not output.enabled %} hidden{% endif %}>
                      {% for field in selected.definition.ui.configuration_fields %}{% if field.output_id == output.switch_id %}
                      <div class="config-field"><label for="timed-output-{{ output.switch_id }}-{{ loop.index }}">{{ field.short_label or field.label }}</label><div class="threshold-control"><input id="timed-output-{{ output.switch_id }}-{{ loop.index }}" type="number" data-definition-path="{{ field.path }}" data-definition-type="number" data-timed-output-field{% if field.path.endswith('.on_sec') %} data-timed-output-on-sec{% elif field.path.endswith('.repeat_count') %} data-timed-output-repeat-count{% endif %} min="{{ field.min }}" max="{{ field.max }}" step="1"><span>{{ field.unit }}</span></div></div>
                      {% endif %}{% endfor %}
                    </div>
                  </article>
                  {% endfor %}
                </div>
                <details class="context-help left"><summary aria-label="ON・OFF設定の補足を開く" title="ON・OFF設定の補足">?</summary><div class="context-help-panel" role="note"><strong>ON・OFFと繰り返し</strong><p>有効なポンプはON時間1〜1800秒、OFF時間0〜1800秒、繰り返し1〜99回で設定します。無効にすると繰り返しは0回になります。出力は順番に動き、同時には動きません。</p></div></details>
              </section>
              {% endif %}

              <section id="watering-rules" class="setup-stage watering-rule-stage"{% if not selected.supports_irrigation %} hidden{% endif %}>
                <div class="context-help-row"><h3>水やりの判断</h3><details class="context-help left"><summary aria-label="水やり判断の説明を開く" title="水やりの判断とは">?</summary><div class="context-help-panel" role="note"><strong>水やりの判断とは</strong><p>土の乾き具合を見て、水やりを始める目安を決めます。</p></div></details></div>
              <div class="config-toolbar">
                <div class="config-field">
                  <label for="moisture-threshold">灌水しきい値</label>
                  <div class="threshold-control">
                    <input id="moisture-threshold" type="range" min="0" max="100" step="1">
                    <input id="moisture-threshold-number" type="number" min="0" max="100" step="1">
                  </div>
                </div>
                <label class="switch-row" for="force-watering">
                  <input id="force-watering" type="checkbox">
                  予約時刻には水分条件を無視して灌水する
                </label>
              </div>
              {% if selected.device_kind == 'WTR' %}
              <div class="config-toolbar startup-watering-test-panel">
                <div><strong>電源投入時の敷設試験</strong><p class="field-help">電源投入またはリセット後に一度だけ、選んだ接続口へ短時間通水します。通常運転ではOFFにしてください。</p></div>
                <label class="switch-row" for="startup-watering-test-enabled"><input id="startup-watering-test-enabled" type="checkbox">敷設試験を有効にする</label>
                <div class="config-field"><label for="startup-watering-test-duration">通水時間（秒）</label><input id="startup-watering-test-duration" type="number" min="1" max="30" step="1"></div>
                <div class="config-field"><label for="startup-watering-test-channel">試験する接続口</label><select id="startup-watering-test-channel"><option value="1">接続口1</option><option value="2">接続口2</option><option value="3">接続口1と2</option></select></div>
                <p class="notice warn">電源を入れるたびに水が出ます。配管と排水を確認し、人が立ち会う敷設試験中だけ有効にしてください。</p>
              </div>
              {% endif %}
              </section>
              <details><summary>通信・開発者向け設定</summary><div class="detail-body"><p class="lead">通常は変更不要です。時刻同期、保守確認間隔、デバッグ送信を調整します。</p><div class="config-toolbar"><div class="config-field"><label for="timezone-offset">機器の時刻基準</label><select id="timezone-offset"><option value="32400">日本時間（UTC+09:00）</option><option value="0">UTC</option></select></div><div class="config-field"><label for="ntp-server">時刻同期サーバー（NTP）</label><input id="ntp-server" type="text" autocomplete="off"></div><label class="switch-row" for="debug-log-on-wake"><input id="debug-log-on-wake" type="checkbox">次回起動時に診断ログを送る</label><div class="config-field"><label for="ota-check-interval">更新確認の間隔</label><select id="ota-check-interval"><option value="3600">1時間</option><option value="10800">3時間</option><option value="21600">6時間</option><option value="43200">12時間</option><option value="86400">24時間</option></select></div></div></div></details>

              <section id="output-connections" class="setup-stage connection-stage"{% if not selected.supports_irrigation %} hidden{% endif %}>
                <div class="setup-stage-head"><div class="context-help-row"><h3>設備をつなぐ</h3><details class="context-help left"><summary aria-label="設備のつながりの説明を開く" title="設備のつながり">?</summary><div class="context-help-panel" role="note"><strong>設備のつながり</strong><p>制御ボックスから水を送る設備まで、今のつながりを確認できます。接続図を選ぶとルートを変更できます。</p></div></details></div></div>
                <div id="open-output-settings" class="output-routing output-routing-trigger" role="button" tabindex="0" aria-haspopup="dialog" aria-controls="output-settings-dialog" aria-label="現在の水やりルートを変更">
                  <img src="/static/ui-illustrations/controller-flow.png" alt="制御機器から潅水設備やセンサーへつながるイラスト" loading="lazy">
                  <div class="output-overview">
                    <div class="output-overview-head"><h4>現在の水やりルート</h4><span class="route-edit-prompt"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></svg>クリックして変更</span></div>
                    <div class="switch-flow-board"><div class="controller-node">制御<br>ボックス</div><div id="output-connection-map" class="switch-output-list" aria-live="polite">{% for output in selected.output_settings.outputs %}<div class="switch-output {{ 'enabled' if output.enabled else 'disabled' }}"><span class="switch-output-dot"></span><span class="switch-output-icon" aria-hidden="true">💧</span><div><strong>{{ output.name }}</strong><small>{{ output.controlled_load or '接続先未設定' }}</small></div><span class="terminal">接続口 {{ output.number }}</span></div>{% endfor %}</div></div>
                  </div>
                  {% if selected.output_settings.unsupported_count %}<p class="notice warn output-warning">保存済み設定に、この機種では編集できない接続が {{ selected.output_settings.unsupported_count }} 件あります。既存値は維持されます。</p>{% endif %}
                </div>
                <dialog id="output-settings-dialog" class="config-dialog builder-dialog" aria-labelledby="output-settings-title">
                  <div class="dialog-head"><div><h3 id="output-settings-title">水やりルートを組み立てる</h3><p class="lead">接続口をONにすると線がつながります。絵を選んで、設備までのルートを完成させましょう。</p></div><button type="button" data-close-output-dialog aria-label="水やりルート設定を閉じる">× <span>閉じる</span></button></div>
                  <div class="dialog-body"><div class="builder-intro"><span class="builder-intro-icon" aria-hidden="true">3</span><span><strong>作り方は3ステップ</strong><br><small>接続口を使う → 設備の種類を選ぶ → 圃場の設備を選ぶ</small></span></div><div id="mosfet-switch-editor" class="mosfet-switch-editor"></div>{% if selected.output_settings.layout_href %}<p class="muted">候補に設備がない場合は、<a href="{{ selected.output_settings.layout_href }}" target="_blank" rel="noopener" data-preserve-current-work aria-label="圃場の設置ビューを新しいタブで開く">圃場の設置ビュー ↗</a>で、この機器の対象を設定してください。組み立て中の内容はこの画面に残ります。</p>{% endif %}<p class="muted">「組み立てを反映」後、設定画面下部の「機器へ送る」を押すと実機へ反映されます。</p></div>
                  <div class="dialog-actions"><button type="button" data-cancel-output-dialog>キャンセル</button><button type="button" class="primary" data-apply-output-dialog>組み立てを反映</button></div>
                </dialog>
              </section>

              <div id="watering-schedules" class="setup-stage schedule-stage"{% if not selected.supports_irrigation and not selected.supports_fertigation %} hidden{% endif %}>
                <h3>{{ 'ポンプ運転の予約' if selected.supports_fertigation else '灌水予約' }}</h3>
                {% if selected.supports_watering_pattern %}
                <fieldset class="irrigation-mode-picker" aria-describedby="irrigation-mode-help">
                  <legend>灌水モード</legend>
                  <div class="irrigation-mode-options">
                    <label class="irrigation-mode-option" for="irrigation-mode-standard">
                      <input id="irrigation-mode-standard" name="irrigation-mode" type="radio" value="standard">
                      <span><strong>通常灌水</strong><small>予約ごとに設定した時間、続けて水を出します。</small></span>
                    </label>
                    <label class="irrigation-mode-option" for="irrigation-mode-pulse">
                      <input id="irrigation-mode-pulse" name="irrigation-mode" type="radio" value="pulse">
                      <span><strong>分割灌水</strong><small>水を出す・止める動きを繰り返し、ゆっくり浸透させます。</small></span>
                    </label>
                  </div>
                  <p id="irrigation-mode-help" class="irrigation-mode-note">選んだモードは、この機器のすべての灌水予約に適用されます。</p>
                </fieldset>
                <div id="irrigation-pattern-settings" class="irrigation-mode-settings" hidden>
                  <div class="config-toolbar">
                    <div class="config-field">
                      <label for="watering-pattern-on-sec">水を出す時間（秒）</label>
                      <input id="watering-pattern-on-sec" type="number" min="0" max="3600" step="1">
                    </div>
                    <div class="config-field">
                      <label for="watering-pattern-off-sec">水を止める時間（秒）</label>
                      <input id="watering-pattern-off-sec" type="number" min="0" max="3600" step="1">
                    </div>
                    <div class="config-field">
                      <label for="watering-pattern-repeat-count">繰り返し回数</label>
                      <input id="watering-pattern-repeat-count" type="number" min="0" max="20" step="1">
                    </div>
                  </div>
                  <p id="irrigation-pattern-summary" class="irrigation-pattern-summary" aria-live="polite"></p>
                </div>
                {% else %}
                <input id="irrigation-mode-standard" name="irrigation-mode" type="radio" value="standard" checked hidden>
                <input id="watering-pattern-on-sec" type="number" value="0" hidden>
                <input id="watering-pattern-off-sec" type="number" value="0" hidden>
                <input id="watering-pattern-repeat-count" type="number" value="0" hidden>
                {% endif %}
                <div class="schedule-spacing-guide">
                  <strong>予約の間には、運転時間＋5分の余裕が必要です</strong>
                  <p>{{ '有効なポンプを順番に動かす全工程' if selected.supports_fertigation else '水を出す・止める動きを含む1回の灌水' }}が終わってから、次の予約まで5分以上空けます。間隔が足りない予約は保存できません。</p>
                </div>
                <div id="schedule-spacing-warning" class="schedule-spacing-warning" role="alert" aria-live="assertive" tabindex="-1" hidden>
                  <strong>予約時刻を見直してください</strong>
                  <p id="schedule-spacing-warning-summary"></p>
                  <ul id="schedule-spacing-warning-list"></ul>
                </div>
                <div id="schedule-editor" class="schedule-editor"></div>
                <div class="actions">
                  <button type="button" id="add-schedule">＋ {{ '液肥づくり' if selected.supports_fertigation else '水やり' }}予約を追加</button>
                </div>
              </div>

              <section id="soil-moisture-reference" class="setup-stage calibration-stage"{% if selected.device_kind not in ["WTR", "SOI"] %} hidden{% endif %}>
                <div class="calibration-card">
                  <div><h3>土壌水分計の基準合わせ</h3><p class="lead">乾いた状態と十分に湿った状態を順番に記録すると、0〜100%の表示が圃場に合いやすくなります。</p><div class="calibration-status"><span class="badge {{ 'good' if selected.soil_calibration_calibrated else 'muted' }}" id="soil-calibration-status">{{ '基準設定済み' if selected.soil_calibration_calibrated else '基準未設定' }}</span><span class="badge warn" id="soil-calibration-action-summary" hidden></span></div></div>
                  <button type="button" id="open-soil-calibration-guide" class="primary">手順を見ながら設定</button>
                </div>
                <select id="soil-calibration-mode" hidden aria-label="次に記録する基準"><option value="normal">通常</option><option value="capture_dry">乾いた状態を記録</option><option value="capture_wet">湿った状態を記録</option><option value="reset">基準をリセット</option></select>
                <details class="config-details"><summary>上級者設定</summary><div class="detail-body"><p class="sensor-maintenance-intro">通常は変更する必要がありません。メーカー資料を確認できる方だけ使用してください。</p><div class="config-toolbar"><label class="switch-row" for="soil-calibration-calibrated"><input id="soil-calibration-calibrated" type="checkbox">記録した基準を使用する</label><label class="switch-row" for="soil-calibration-auto-mode"><input id="soil-calibration-auto-mode" type="checkbox">基準の候補を自動で探す</label><label class="switch-row" for="soil-calibration-apply-auto"><input id="soil-calibration-apply-auto" type="checkbox">候補を自動で反映する</label><label class="switch-row" for="soil-calibration-drift-check"><input id="soil-calibration-drift-check" type="checkbox">基準のずれを検知する</label><div class="config-field"><label for="soil-calibration-dry-raw">乾燥時の計測値</label><input id="soil-calibration-dry-raw" type="number" min="1" max="4095" step="1"></div><div class="config-field"><label for="soil-calibration-wet-raw">湿潤時の計測値</label><input id="soil-calibration-wet-raw" type="number" min="0" max="4094" step="1"></div><div class="config-field"><label for="soil-calibration-min-delta-raw">必要な計測差</label><input id="soil-calibration-min-delta-raw" type="number" min="10" max="2000" step="1"></div><div class="config-field"><label for="soil-calibration-drift-tolerance-raw">ずれの許容値</label><input id="soil-calibration-drift-tolerance-raw" type="number" min="10" max="2000" step="1"></div><div class="config-field"><label for="soil-calibration-sample-count">平均する回数</label><input id="soil-calibration-sample-count" type="number" min="1" max="100" step="1"></div><div class="config-field"><label for="soil-calibration-sample-interval-ms">計測間隔（ミリ秒）</label><input id="soil-calibration-sample-interval-ms" type="number" min="0" max="1000" step="1"></div></div></div></details>
                <dialog id="soil-calibration-guide" class="config-dialog" aria-labelledby="soil-calibration-guide-title">
                  <div class="dialog-head"><div><h3 id="soil-calibration-guide-title">土壌水分計の基準合わせ</h3><p class="lead">乾燥と湿潤を同時には記録せず、1段階ずつ機器へ反映します。</p></div><button type="button" data-close-calibration-guide aria-label="土壌水分計の基準合わせを閉じる">× <span>閉じる</span></button></div>
                  <div class="dialog-body"><div class="guide-steps"><div class="guide-step"><strong>センサーを乾いた状態にする</strong><span>水分を拭き取り、値が落ち着くまで待ちます。普段使う用土の乾燥状態で行うと、表示が栽培環境に合いやすくなります。</span></div><div class="guide-step"><strong>乾いた基準を記録して機器へ送る</strong><span>下のボタンを選び、設定画面下部の「保存して機器へ反映」を押します。次回通信で設定受信済みになるまで待ちます。</span><div class="actions"><button type="button" data-calibration-mode="capture_dry">乾いた基準を記録する</button></div></div><div class="guide-step"><strong>用土を十分に湿らせる</strong><span>たっぷり潅水し、余分な水が抜けた後、いつもと同じ深さへセンサーを挿します。水中へ直接入れないでください。</span></div><div class="guide-step"><strong>湿った基準を記録して機器へ送る</strong><span>下のボタンを選び、もう一度「保存して機器へ反映」を押します。</span><div class="actions"><button type="button" data-calibration-mode="capture_wet">湿った基準を記録する</button></div></div></div><p class="notice warn">基準をやり直す場合だけリセットしてください。リセット後は乾燥・湿潤の両方を記録し直します。</p></div>
                  <div class="dialog-actions"><button type="button" data-calibration-mode="reset">基準をリセット</button><button type="button" class="primary" data-close-calibration-guide>閉じる</button></div>
                </dialog>
              </section>

              <div class="setup-stage environment-stage"{% if selected.device_kind not in ["WRS", "ENV", "PAR"] %} hidden{% endif %}>
                <div class="setup-stage-head"><div class="context-help-row"><h3>つないだセンサー</h3><details class="context-help left"><summary aria-label="センサー選択の説明を開く" title="センサー選択について">?</summary><div class="context-help-panel" role="note"><strong>センサー選択について</strong><p>実際につないでいる機材だけをONにします。ONにした機材の調整メニューだけが開きます。</p></div></details></div></div>
                <div class="sensor-rack">
                  <article class="sensor-device-card" data-env-sensor-card="par"{% if selected.device_kind not in ["WRS", "ENV", "PAR"] %} hidden{% endif %}>
                    <div class="sensor-device-head">
                      <span class="sensor-device-illustration par" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="32" cy="25" r="11"/><path d="M32 5v7M32 38v7M12 25h7M45 25h7M18 11l5 5M46 11l-5 5M17 53h30"/></svg></span>
                      <span><strong>光センサー</strong><small>日射や、光合成に使える光を測ります</small></span>
                      <label class="sensor-power-switch" for="env-par-enabled"><input id="env-par-enabled" type="checkbox"><span class="sensor-power-track" aria-hidden="true"></span><span data-env-sensor-state="par">使用しない</span></label>
                    </div>
                    <div class="sensor-device-body" data-env-sensor-panel="par" hidden>
                      <div class="sensor-live-strip"><span class="sensor-live-dot"></span><span><strong>光を計測する準備ができています</strong><small>表示が基準計とずれているときだけ調整してください</small></span></div>
                      <button type="button" class="sensor-tune-button" data-env-tune-target="par_umol_m2_s"><span aria-hidden="true">☀</span><span><strong>光の表示を合わせる</strong><small>基準計と同じ値になるよう調整</small><span class="sensor-adjustment-value" data-env-calibration-summary="par_umol_m2_s">未調整</span></span></button>
                    </div>
                  </article>

                  <article class="sensor-device-card" data-env-sensor-card="soil"{% if selected.device_kind not in ["WRS", "ENV"] %} hidden{% endif %}>
                    <div class="sensor-device-head">
                      <span class="sensor-device-illustration soil" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M24 8h16v25H24zM28 33v21M36 33v21"/><path d="M12 50c10-6 30-6 40 0M29 19h6"/></svg></span>
                      <span><strong>土のセンサー</strong><small>水分・地温・EC・pH・養分を測ります</small></span>
                      <label class="sensor-power-switch" for="env-soil-enabled"><input id="env-soil-enabled" type="checkbox"><span class="sensor-power-track" aria-hidden="true"></span><span data-env-sensor-state="soil">使用しない</span></label>
                    </div>
                    <div class="sensor-device-body" data-env-sensor-panel="soil" hidden>
                      <div class="sensor-live-strip"><span class="sensor-live-dot"></span><span><strong>土の状態を計測する準備ができています</strong><small>合わせたい項目を1つ選びます</small></span></div>
                      <div class="soil-metric-grid" aria-label="調整する土壌計測項目">
                        <button type="button" data-env-tune-target="soil_moisture_percent"><span>滴</span><strong>土壌水分</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_moisture_percent">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_temperature_c"><span>℃</span><strong>地温</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_temperature_c">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_ec_us_cm"><span>EC</span><strong>土壌EC</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_ec_us_cm">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_ph"><span>pH</span><strong>土壌pH</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_ph">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_n_mg_kg"><span>N</span><strong>窒素</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_n_mg_kg">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_p_mg_kg"><span>P</span><strong>リン</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_p_mg_kg">未調整</small></button>
                        <button type="button" data-env-tune-target="soil_k_mg_kg"><span>K</span><strong>カリウム</strong><small class="sensor-adjustment-value" data-env-calibration-summary="soil_k_mg_kg">未調整</small></button>
                      </div>
                    </div>
                  </article>
                </div>

                <div hidden aria-hidden="true">
                  <input id="env-par-slave" type="hidden"><input id="env-par-function" type="hidden"><input id="env-par-register" type="hidden">
                  <input id="env-soil-slave" type="hidden"><input id="env-soil-function" type="hidden"><input id="env-soil-start-register" type="hidden"><input id="env-power-settle-ms" type="hidden">
                </div>

                <dialog id="env-calibration-dialog" class="config-dialog sensor-calibration-dialog" aria-labelledby="env-calibration-dialog-heading">
                  <div class="dialog-head"><div><h3 id="env-calibration-dialog-heading">センサーの表示を合わせる</h3><p class="lead">手元の基準と同じ値になるよう、つまみを動かします。</p></div><button type="button" data-close-env-calibration aria-label="センサーの表示合わせを閉じる">× <span>閉じる</span></button></div>
                  <section id="env-calibration-workbench" class="sensor-tuning-bench" aria-live="polite">
                    <div class="sensor-bench-head"><span class="sensor-bench-dial" aria-hidden="true"><span id="env-calibration-dial-value">0</span></span><span><small>表示の調整</small><strong id="env-calibration-title">光の表示を合わせる</strong><span id="env-calibration-help">信頼できる基準計の値へダイヤルを合わせます</span></span></div>
                    <select id="env-calibration-mode" hidden aria-label="校正操作"><option value="normal">通常</option><option value="capture_reference">基準値を記録</option><option value="reset">未校正に戻す</option></select>
                    <select id="env-calibration-target" hidden aria-label="記録する項目"><option value="par_umol_m2_s">光合成に使える光</option><option value="soil_moisture_percent">土壌水分</option><option value="soil_temperature_c">地温</option><option value="soil_ec_us_cm">土壌EC</option><option value="soil_ph">土壌pH</option><option value="soil_n_mg_kg">窒素</option><option value="soil_p_mg_kg">リン</option><option value="soil_k_mg_kg">カリウム</option></select>
                    <div class="sensor-range-control"><label for="env-calibration-reference-value">手元の基準が示している値</label><div class="sensor-range-readout"><output id="env-calibration-reference-display">0</output><span id="env-calibration-unit"></span></div><input id="env-calibration-reference-value" type="range" min="0" max="2500" step="10"><div class="sensor-range-scale"><span id="env-calibration-min">0</span><span id="env-calibration-mid">1250</span><span id="env-calibration-max">2500</span></div></div>
                    <p class="muted">記録後、画面下部の「組み立てた設定を機器へ送る」で実機へ反映します。</p>
                  </section>
                  <div class="dialog-actions"><button type="button" data-env-calibration-action="reset">調整を取り消す</button><button type="button" data-close-env-calibration>閉じる</button><button type="button" class="primary" data-env-calibration-action="capture_reference">この値を記録</button></div>
                </dialog>

                <details class="config-details sensor-maintenance-details">
                  <summary>上級者設定</summary>
                  <div class="config-toolbar">
                    <p class="sensor-maintenance-intro">通常は変更する必要がありません。計測機器について詳しい方が、メーカー資料に基づいて微調整するときだけ使用してください。</p>
                    <div data-env-sensor-advanced="par">
                    <label class="switch-row" for="env-cal-par-calibrated"><input id="env-cal-par-calibrated" type="checkbox"> 光の補正を使用する</label>
                    <div class="config-field"><label for="env-cal-par-scale">光の倍率</label><input id="env-cal-par-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-par-offset">光のずれ補正</label><input id="env-cal-par-offset" type="number" step="0.01"></div>
                    </div>
                    <div data-env-sensor-advanced="soil">
                    <label class="switch-row" for="env-cal-moisture-calibrated"><input id="env-cal-moisture-calibrated" type="checkbox"> 水分 校正済み</label>
                    <div class="config-field"><label for="env-cal-moisture-scale">水分の倍率</label><input id="env-cal-moisture-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-moisture-offset">水分のずれ補正</label><input id="env-cal-moisture-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-temperature-calibrated"><input id="env-cal-temperature-calibrated" type="checkbox"> 地温 校正済み</label>
                    <div class="config-field"><label for="env-cal-temperature-scale">地温の倍率</label><input id="env-cal-temperature-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-temperature-offset">地温のずれ補正</label><input id="env-cal-temperature-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-ec-calibrated"><input id="env-cal-ec-calibrated" type="checkbox"> EC 校正済み</label>
                    <div class="config-field"><label for="env-cal-ec-scale">ECの倍率</label><input id="env-cal-ec-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-ec-offset">ECのずれ補正</label><input id="env-cal-ec-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-ph-calibrated"><input id="env-cal-ph-calibrated" type="checkbox"> pH 校正済み</label>
                    <div class="config-field"><label for="env-cal-ph-scale">pHの倍率</label><input id="env-cal-ph-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-ph-offset">pHのずれ補正</label><input id="env-cal-ph-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-n-calibrated"><input id="env-cal-n-calibrated" type="checkbox"> 窒素 校正済み</label>
                    <div class="config-field"><label for="env-cal-n-scale">窒素の倍率</label><input id="env-cal-n-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-n-offset">窒素のずれ補正</label><input id="env-cal-n-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-p-calibrated"><input id="env-cal-p-calibrated" type="checkbox"> リン 校正済み</label>
                    <div class="config-field"><label for="env-cal-p-scale">リンの倍率</label><input id="env-cal-p-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-p-offset">リンのずれ補正</label><input id="env-cal-p-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-k-calibrated"><input id="env-cal-k-calibrated" type="checkbox"> カリウム 校正済み</label>
                    <div class="config-field"><label for="env-cal-k-scale">カリウムの倍率</label><input id="env-cal-k-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-k-offset">カリウムのずれ補正</label><input id="env-cal-k-offset" type="number" step="0.01"></div>
                    </div>
                  </div>
                </details>
              </div>

              <div class="actions setup-save-bar">
                <span class="muted" data-stateful-reason></span>
                <button type="submit" data-stateful-submit>下書きを保存</button>
                <button type="button" id="save-push-runtime-config" class="primary" data-requires-dirty{% if selected_device.state != 'active' %} data-state-blocked="true" disabled aria-describedby="device-push-disabled" title="利用中の機器にだけ送信できます"{% endif %}>組み立てた設定を機器へ送る</button>
                <button type="button" id="push-runtime-config"{% if selected_device.state != 'active' %} disabled aria-describedby="device-push-disabled" title="利用中の機器にだけ送信できます"{% endif %}>保存済み設定をもう一度反映</button>
              </div>
              {% if selected.scheduled_operation %}
              <dialog id="scheduled-operation-warning-dialog" class="config-dialog" aria-labelledby="scheduled-operation-warning-title">
                <div class="dialog-head"><div><h3 id="scheduled-operation-warning-title">この設定では予約時刻に潅水されません</h3><p class="lead">機器へ送る前に、潅水ポンプの設定を確認してください。</p></div><button type="button" data-cancel-scheduled-operation-warning aria-label="警告を閉じる">× <span>閉じる</span></button></div>
                <div class="dialog-body">
                  <ul id="scheduled-operation-warning-list"></ul>
                  {% if selected.scheduled_operation.enable_control_available %}<label class="switch-row" id="scheduled-operation-enable-row"><input id="scheduled-operation-enable-before-save" type="checkbox">{{ selected.scheduled_operation.spec.enable_checkbox_label }}</label>{% endif %}
                </div>
                <div class="dialog-actions"><button type="button" data-cancel-scheduled-operation-warning>設定に戻る</button><button type="button" id="scheduled-operation-warning-continue" class="primary">確認して続ける</button></div>
              </dialog>
              {% endif %}
              {% if selected_device.state == 'retired' %}<p class="empty" id="device-push-disabled">廃止済みのため、動作設定は閲覧のみです。</p>{% elif selected_device.state != 'active' %}<p class="empty" id="device-push-disabled">現在は{{ selected.state_label }}です。設定は保存できますが、機器への送信は「利用中」へ変更してから行ってください。</p>{% endif %}
            </form>
          </section>
            </section>

            <section id="tab-monitoring" class="tab-panel" role="tabpanel" hidden>
          {% if selected.rs485_sensor_groups %}
          <section class="panel" aria-label="接続センサーの現在値">
            <div class="field-head">
              <div><h2>接続センサーの現在値</h2><p class="lead">センサー名と設置場所ごとに、最後に受信した状態を表示します。</p></div>
              <span class="badge good">{{ selected.rs485_sensor_groups|length }} 台</span>
            </div>
            <div class="rs485-sensor-grid">
              {% for sensor in selected.rs485_sensor_groups %}
              <article class="rs485-sensor-card">
                <div class="rs485-sensor-head"><span><strong>{{ sensor.name }}</strong><small>{{ sensor.location }}</small></span><span class="badge {{ sensor.state_class }}">{{ sensor.state_label }}</span></div>
                <div class="rs485-sensor-measurements">
                  {% for measurement in sensor.measurements %}<a class="rs485-sensor-measurement" href="#{{ measurement.history_anchor }}" aria-label="{{ sensor.name }}の{{ measurement.label }}の履歴を見る"><span>{{ measurement.label }}</span><strong>{{ measurement.value }}</strong></a>{% else %}<p class="rs485-sensor-no-value">有効な計測値はまだありません。</p>{% endfor %}
                </div>
              </article>
              {% endfor %}
            </div>
          </section>
          {% endif %}
          {% if selected.monitoring_charts %}
          <div class="section-grid">
            {% for chart in selected.monitoring_charts %}
            <section class="panel">
              <div class="device-chart-heading">
                <h2>{{ selected.title }} / {{ chart.title }}</h2>
                <a class="chart-settings-link" href="{{ device_link_prefix }}{{ selected.id }}?tab=settings" title="{{ selected.title }}の動作設定" aria-label="{{ selected.title }}の動作設定">&#9881; <span>設定</span></a>
              </div>
              <div class="chart-card" data-chart-id="{{ chart.dom_id }}" data-chart-kind="{{ chart.kind }}" data-empty-message="{{ chart.empty_message }}">
                <div class="range-controls" aria-label="{{ chart.title }}の表示期間">
                  <button type="button" data-range-days="3" class="active">直近3日</button>
                  <button type="button" data-range-days="14">2週間</button>
                  <button type="button" data-range-months="1">1か月</button>
                  <button type="button" data-range-all="true">全期間</button>
                  <input type="date" data-range-start aria-label="開始日">
                  <input type="date" data-range-end aria-label="終了日">
                  <button type="button" data-range-custom="true">カスタム</button>
                </div>
                <div class="chart-body"><div class="chart-loading">{{ chart.title }}を読み込み中...</div></div>
              </div>
            </section>
            {% endfor %}
          </div>
          {% else %}
          <div class="empty">この機器で表示できる計測・稼働グラフはまだありません。</div>
          {% endif %}

          {% if selected.watering_history %}
          <details>
            <summary>直近の灌水記録</summary>
            <div class="detail-body">
              <div class="list">
                {% for item in selected.watering_history %}
                <div class="list-row">
                  <div class="list-time">{{ item.time }}</div>
                  <div class="list-main">
                    <span class="badge {{ item.class }}">{{ item.label }}</span>
                    <span>実行時間: {{ item.duration }}</span>
                    <span>対象: {{ item.channel }}</span>
                    <span>土壌水分: {{ item.soil }}</span>
                    <span>しきい値: {{ item.threshold }}</span>
                    {% if item.catch_up %}<span>予約後の追いつき実行</span>{% endif %}
                    {% if item.reason %}<span>理由: {{ item.reason }}</span>{% endif %}
                  </div>
                </div>
                {% endfor %}
              </div>
            </div>
          </details>
          {% endif %}

          <details class="panel advanced-info communication-history">
              <summary><span><strong>詳しい通信履歴</strong><small>上級者向け・通常の運用では確認不要です</small></span></summary>
              <div class="detail-body">
              {% if selected.wake_history %}
              <div class="list">
                {% for item in selected.wake_history %}
                <div class="list-row">
                  <div class="list-time">{{ item.time }}</div>
                  <div class="list-main">
                    <span>通信番号: {{ item.seq }}</span>
                    <span>次回の通信予定: {{ item.next_wake }}</span>
                    <span>設定を受信: {{ item.config_received }}</span>
                    <span>時計を同期: {{ item.time_synced }}</span>
                    <span>電波強度: {{ item.rssi }}</span>
                  </div>
                </div>
                {% endfor %}
              </div>
              {% else %}
              <div class="empty">詳しい通信履歴はまだありません。</div>
              {% endif %}
              </div>
          </details>
            </section>

            <section id="tab-firmware" class="tab-panel" role="tabpanel" hidden>
          <section id="ota-target" class="panel">
            <div class="field-head"><div class="context-help-row"><h2>機器ソフトウェアの更新</h2><details class="context-help left"><summary aria-label="機器ソフトウェア更新の説明を開く" title="ここでできること">?</summary><div class="context-help-panel" role="note"><strong>ここでできること</strong><p>現在のバージョン確認、新しいファイルの登録、更新予約をこの画面で完了できます。</p></div></details></div><span class="badge {{ selected.ota_class }}">{{ selected.ota_state }}</span></div>
            <div class="firmware-workbench">
              <div class="firmware-current">
                <span class="muted">現在のバージョン</span><div class="version">{{ selected.firmware }}</div>
                <div><span class="muted">更新予約</span><strong>{{ selected.target_firmware }}</strong></div>
                {% if selected.ota_error %}<div class="notice error">{{ selected.ota_error }}</div>{% endif %}
                <img src="/static/ui-illustrations/firmware-care.png" alt="機器ソフトウェアを安全に更新するイラスト" loading="lazy">
              </div>
              <form id="firmware-upload-form" class="firmware-upload-card" enctype="multipart/form-data" data-stateful-form data-pristine-message=".inasfw ファイルを選択してください。" data-invalid-message=".inasfw ファイルの読み取りが完了していません。" data-current-device-kind="{{ selected_device.device_kind if selected_device and selected_device.device_kind else '' }}">
                <div><h3>新しい更新ファイルを登録</h3><p class="lead">INAS更新ファイル（.inasfw）を置くと、対応機種とバージョンを自動で読み取ります。</p></div>
                <label class="firmware-dropzone" id="firmware-dropzone" for="firmware-file"><strong>.inasfw ファイルをここへドロップ</strong><span>またはクリックして選択</span><input id="firmware-file" name="firmware" type="file" accept=".inasfw,application/zip"></label>
                <div id="firmware-manifest-summary" class="empty">まだファイルが選択されていません。</div>
                <div class="firmware-meta"><div><span>対応機種</span><strong id="firmware-device-kind-display">-</strong></div><div><span>バージョン</span><strong id="firmware-version-display">-</strong></div><div><span>ビルド</span><strong id="firmware-build-id-display">-</strong></div></div>
                <input id="firmware-device-kind" name="device_kind" type="hidden" value="{{ selected_device.device_kind if selected_device and selected_device.device_kind else 'WTR' }}">
                <input id="firmware-version" name="version" type="hidden"><input id="firmware-build-id" name="build_id" type="hidden">
                <details class="firmware-advanced"><summary>配信オプション</summary><div class="detail-body"><label for="firmware-rollout-state">配信状態</label><select id="firmware-rollout-state" name="rollout_state"><option value="active">配信中</option><option value="paused">一時停止</option><option value="revoked">取り消し</option></select><label class="switch-row"><input id="firmware-force" name="force" type="checkbox">同じバージョンでも置き換える</label><label class="switch-row"><input id="firmware-allow-downgrade" name="allow_downgrade" type="checkbox">古いバージョンへの更新を許可</label><button type="button" id="inspect-firmware-manifest">ファイル情報を再読込</button></div></details>
                <div class="actions"><span class="muted" data-stateful-reason></span><button type="submit" class="primary" data-stateful-submit>登録する</button></div>
              </form>
            </div>
            <form id="firmware-target-form" data-stateful-form data-pristine-message="更新予約は変更されていません。"{% if selected_device.state == 'retired' %} data-state-blocked="true" data-blocked-message="廃止済みの更新予約は変更できません。"{% endif %}>
              <label for="target-firmware-version">この機器に適用するバージョン</label><select id="target-firmware-version" aria-label="更新する機器ソフトウェアのバージョン" data-searchable-select data-search-placeholder="バージョン、ビルドを検索" data-empty-message="一致する候補はありません。"><option value="">更新予約なし</option>{% for artifact in firmware_target_options %}<option value="{{ artifact.version }}" {% if selected_device.target_firmware_version == artifact.version %}selected{% endif %}>{{ artifact.label }}</option>{% endfor %}</select>
              <div class="actions"><span class="muted" data-stateful-reason></span><button type="submit" class="primary" data-stateful-submit>このバージョンへ更新予約</button><button type="button" id="clear-firmware-target"{% if not selected_device.target_firmware_version or selected_device.state == 'retired' %} disabled title="{{ '廃止済みの機器は変更できません' if selected_device.state == 'retired' else '解除する更新予約はありません' }}"{% endif %}>予約を解除</button></div>
            </form>
          </section>

          <section class="panel">
            <h2>機器ソフトウェアの更新履歴</h2>
            {% if selected.ota_history %}
            <div class="list">
              {% for item in selected.ota_history %}
              <div class="list-row">
                <div class="list-time">{{ item.time }}</div>
                <div class="list-main"><span>{{ item.state }}</span><span>{{ item.from_version }} → {{ item.to_version }}</span>{% if item.error %}<span class="badge danger">{{ item.error }}</span>{% endif %}</div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty">更新履歴はまだありません。</div>
            {% endif %}
          </section>

          <section id="firmware-maintenance" class="panel">
            <h2>登録済み更新ファイル</h2>
            <details id="firmware-artifact-details">
              <summary>配信ファイルの詳細を表示（<span id="firmware-artifact-count">{{ firmware_artifacts|length }}</span>件）</summary>
              <div class="detail-body">
                <table>
                  <thead><tr><th>キー</th><th>バージョン</th><th>種別</th><th>ビルドID</th><th>Manifest</th><th>状態</th><th>サイズ</th><th>SHA-256</th><th>配信先</th><th>更新日時</th></tr></thead>
                  <tbody id="firmware-artifact-rows">
                    {% for key, artifact in firmware_artifacts.items() %}
                    <tr data-firmware-artifact-key="{{ key }}">
                      <td>{{ key }}</td>
                      <td>{{ artifact.version }}</td>
                      <td>{{ artifact.device_kind }}</td>
                      <td>{{ artifact.build_id or '未取得' }}</td>
                      <td>{{ artifact.manifest_label }}</td>
                      <td>{{ artifact.rollout_state }}</td>
                      <td>{{ artifact.size }}</td>
                      <td>{{ artifact.sha256 }}</td>
                      <td><a href="{{ artifact.url }}" target="_blank" rel="noopener" aria-label="更新ファイルを新しいタブで開く">配信ファイルを開く ↗</a></td>
                      <td>{{ artifact.updated_at }}</td>
                    </tr>
                    {% endfor %}
                    {% if not firmware_artifacts %}<tr data-firmware-artifact-empty><td colspan="10">登録済みファイルはありません。</td></tr>{% endif %}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
            </section>

            <section id="tab-maintenance" class="tab-panel" role="tabpanel" hidden>
          <section class="panel">
            <div class="context-help-row">
              <h2>保守・管理</h2>
              <details id="connection-help" class="context-help left connection-help">
                <summary aria-label="困ったときのヘルプを開く" title="困ったとき">?</summary>
                <div class="context-help-panel connection-help-panel" role="note">
                  <strong>困ったとき：通信を確認する</strong>
                  <p>専門用語やコマンドは不要です。上から順に見て、最初に「未取得」または「記録なし」になる場所を探します。</p>
                  <div class="connection-check-grid">
                    {% for check in selected.connection_diagnostics.checks %}
                    <article class="connection-check-card {{ check.class }}">
                      <span class="connection-check-step" aria-hidden="true">{{ check.step }}</span>
                      <span>{{ check.label }}</span>
                      <strong>{{ check.value }}</strong>
                      <small>{{ check.detail }}</small>
                      <p>{{ check.reason }}</p>
                    </article>
                    {% endfor %}
                  </div>
                  <div class="connection-reading-guide">
                    <p><strong>判断のしかた:</strong> 「Hubが最後に確認」が更新されていれば、その時刻までは電源・Wi-Fi・Hubへの接続が成功しています。「Hubへの接続」だけ記録され、その後の最終確認が更新されない場合は、機器を再起動して次回通信まで待ちます。</p>
                  </div>
                  <p class="connection-help-next">実際の成功・切断時刻は、このタブの「通信・接続履歴」を開くと確認できます。</p>
                </div>
              </details>
            </div>
            <p class="lead">機器の利用状態、接続履歴、管理者向けデータを必要なときだけ確認します。通信で困ったときは「?」を開いてください。</p>
            {% if selected.operational_error %}
            <div id="operational-error-details" class="device-operational-alert" role="alert"><strong>予定した動作を実行できませんでした</strong><span>{{ selected.operational_error.reason_labels | join(' / ') }}{% if selected.operational_error.batch_skip_reason %}<br>実行しなかった理由: {{ selected.operational_error.batch_skip_reason }}{% endif %}</span></div>
            {% endif %}
            <details>
              <summary>機器の利用状態を変更</summary>
              <div class="detail-body">
                <p>現在: <span class="badge {{ selected.state_class }}">{{ selected.state_label }}</span></p>
                {% if selected_device.state == 'pending' %}
                <p class="lead">登録内容を確認後、承認すると動作設定の送信や運用を開始できます。</p>
                <label for="approved-by">承認者</label><input id="approved-by" type="text" value="operator">
                <div class="actions">
                  <button type="button" data-state-action="approve">承認する</button>
                  <button type="button" data-state-action="retire">登録を廃止する</button>
                </div>
                {% elif selected_device.state == 'active' %}
                <p class="lead">稼働を止める場合は停止してください。廃止は停止後に選択できます。</p>
                <div class="actions"><button type="button" data-state-action="disable">停止する</button></div>
                {% elif selected_device.state == 'disabled' %}
                <p class="lead">運用を再開するか、今後使用しない機器として廃止できます。</p>
                <label for="approved-by">再開者</label><input id="approved-by" type="text" value="operator">
                <div class="actions"><button type="button" data-state-action="approve">稼働を再開する</button><button type="button" data-state-action="retire">廃止する</button></div>
                {% else %}
                <div class="empty">廃止済みです。機器状態はこれ以上変更できません。</div>
                {% endif %}
              </div>
            </details>

            <details>
              <summary>動作設定 JSON</summary>
              <div class="detail-body">
                <p class="lead">下のJSONは、この機種へ実際に送る項目だけを表示します。Hubに保持している旧設定は削除されません。</p>
                <textarea id="runtime-config-json">{{ format_json(selected.runtime_config_payload) }}</textarea>
                <details><summary>Hubに保持している互換設定</summary><pre>{{ format_json(selected_device.config) }}</pre></details>
                <div class="actions">
                  <button type="button" id="apply-runtime-json">JSON をフォームに反映</button>
                  <button type="button" id="save-runtime-json">JSON で保存</button>
                  <button type="button" id="save-push-runtime-json" class="primary"{% if selected_device.state != 'active' %} disabled title="利用中の機器にだけ送信できます"{% endif %}>JSONで保存して機器へ反映</button>
                </div>
              </div>
            </details>

            <details>
              <summary>通信・接続履歴</summary>
              <div class="detail-body">
                {% if selected.connection_diagnostics.events %}
                <div class="connection-timeline">
                  {% for event in selected.connection_diagnostics.events %}
                  <article class="connection-event {{ event.class }}">
                    <span class="connection-event-dot" aria-hidden="true"></span>
                    <strong>{{ event.label }}</strong>
                    <p>{{ event.description }}</p>
                    <time datetime="{{ event.occurred_at }}">{{ event.time }}<span>{{ event.age }}</span></time>
                  </article>
                  {% endfor %}
                </div>
                {% else %}
                <div class="empty"><strong>この機器の接続記録はまだありません。</strong><br>「?」の通信ヘルプを開き、電源と初期設定から順に確認してください。</div>
                {% endif %}
              </div>
            </details>

            <details>
              <summary>管理者向けの技術データ</summary>
              <div class="detail-body">
                <h3>Status History</h3>
                <table><thead><tr><th>受信時刻</th><th>詳細 JSON</th></tr></thead><tbody>{% for status in selected_statuses | reverse %}<tr><td>{{ format_datetime(status.received_at) }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>{% endfor %}</tbody></table>
                <h3>OTA Status History</h3>
                <table><thead><tr><th>受信時刻</th><th>詳細 JSON</th></tr></thead><tbody>{% for status in selected_ota_statuses | reverse %}<tr><td>{{ format_datetime(status.received_at) }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>{% endfor %}</tbody></table>
                <h3>接続履歴</h3>
                {{ render_events(connection_events) | safe }}
                <h3>MQTT Event History</h3>
                {{ render_events(recent_events) | safe }}
              </div>
            </details>
          </section>
            </section>

            {% for extension in selected.ui_extensions %}{% for extension_tab in extension.tabs %}
            <section id="{{ extension_tab.dom_id }}" class="tab-panel" role="tabpanel" hidden>
              <section class="panel extension-shell" aria-label="{{ extension_tab.title }}">
                <div class="extension-heading">
                  <div><h2>{{ extension_tab.title }}</h2><p class="lead">{{ extension_tab.description }}</p></div>
                  <span class="extension-origin">{{ extension.name }} / {{ extension.version }}</span>
                </div>
                <div class="extension-blocks">
                  {% for block in extension_tab.blocks %}
                    {% if block.type == 'process_flow' %}
                    <section class="extension-block"><h3>{{ block.title }}</h3><div class="extension-process">{% for item in block['items'] %}<article class="extension-process-step"><strong>{{ item.title }}</strong><p>{{ item.description }}</p></article>{% endfor %}</div></section>
                    {% elif block.type == 'metric_grid' %}
                    <section class="extension-block"><h3>{{ block.title }}</h3><div class="extension-metrics">{% for item in block['items'] %}<div class="extension-metric"><span>{{ item.label }}</span><strong>{{ item.display_value }}</strong></div>{% endfor %}</div></section>
                    {% elif block.type == 'callout' %}
                    <section class="extension-block extension-callout {{ block.tone or 'leaf' }}"><h3>{{ block.title }}</h3><p>{{ block.description }}</p></section>
                    {% endif %}
                  {% endfor %}
                </div>
              </section>
            </section>
            {% endfor %}{% endfor %}
          </div>
          {% endif %}
        </div>

        <script src="/static/context-help.js"></script>
        <script src="/static/stateful-actions.js"></script>
        <script src="/static/select-filter.js"></script>
        <script>
          const selectedDeviceId = {{ selected_device_id | tojson }};
          const selectedDeviceState = {{ (selected_device.state if selected_device else '') | tojson }};
          const demoMode = {{ demo_mode | tojson }};
          const chartEndpoint = selectedDeviceId ? ((demoMode ? "/demo/local/api/mqtt-devices/" : "/local/api/mqtt-devices/") + encodeURIComponent(selectedDeviceId) + "/charts") : null;
          const initialRuntimeConfig = {{ (selected_device.config if selected_device else {}) | tojson }};
          const deviceDefinition = {{ (admin_view.selected.definition if admin_view.selected else {}) | tojson }};
          const deviceRuntimeSendKeys = (((deviceDefinition || {}).runtime_config || {}).send_keys || []);
          const runtimeConfigFixedValues = (((deviceDefinition || {}).runtime_config || {}).fixed_values || {});
          const scheduledOperationDefinition = (((deviceDefinition || {}).ui || {}).scheduled_operation || null);
          const supportsWateringPattern = deviceRuntimeSendKeys.includes("watering_pattern");
          const deviceKind = ((deviceDefinition || {}).device || {}).kind || "";
          const isFertigationDevice = deviceKind === "FGT";
          const isIrrigationScheduleDevice = ["WTR", "WRS", "FGT"].includes(deviceKind);
          const scheduleSafetyBufferSec = 5 * 60;
          const deviceOutputCapabilities = {{ (admin_view.selected.output_settings.outputs if admin_view.selected else []) | tojson }};
          const unsupportedOutputSettings = {{ (admin_view.selected.output_settings.unsupported if admin_view.selected else []) | tojson }};
          let plotlyLoadPromise = null;
          let pendingWorkCount = 0;
          let lastActionButton = null;
          let currentMosfetSwitches = [];

          const deviceListSearch = document.getElementById("device-list-search");
          if (deviceListSearch) {
            const form = document.getElementById("device-list-search-form");
            let searchTimer = null;
            deviceListSearch.addEventListener("input", () => {
              window.clearTimeout(searchTimer);
              searchTimer = window.setTimeout(() => form?.requestSubmit(), 450);
            });
          }

          document.querySelectorAll("[data-delete-device]").forEach((button) => {
            button.addEventListener("click", async () => {
              const deviceId = button.getAttribute("data-delete-device");
              const deviceName = button.getAttribute("data-delete-device-name") || deviceId;
              const confirmed = window.confirm(
                deviceName + "（" + deviceId + "）を一覧から削除しますか？\\n\\n計測履歴は残ります。圃場で使用中の機器は削除できません。再接続すると再び認識されます。",
              );
              if (!confirmed) return;
              button.disabled = true;
              try {
                await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(deviceId), { method: "DELETE" }, "デバイスを削除しています...");
                window.location.reload();
              } catch (error) {
                button.disabled = false;
                window.alert("削除できませんでした: " + error.message);
              }
            });
          });

          document.querySelectorAll("[data-delete-camera]").forEach((button) => {
            button.addEventListener("click", async () => {
              const cameraId = button.getAttribute("data-delete-camera");
              const cameraName = button.getAttribute("data-delete-camera-name") || cameraId;
              const confirmed = window.confirm(
                cameraName + "（" + cameraId + "）の登録を解除しますか？\\n\\n撮影済み画像は残ります。圃場やInstagramで使用中のカメラは解除できません。",
              );
              if (!confirmed) return;
              button.disabled = true;
              try {
                await requestJson("/local/api/cameras/" + encodeURIComponent(cameraId), { method: "DELETE" }, "カメラ登録を解除しています...");
                window.location.reload();
              } catch (error) {
                button.disabled = false;
                window.alert("解除できませんでした: " + error.message);
              }
            });
          });

          if (selectedDeviceState === "retired") {
            document.querySelectorAll("#metadata-form input, #metadata-form select, #metadata-form textarea, #metadata-form button, #runtime-config-form input, #runtime-config-form select, #runtime-config-form textarea, #runtime-config-form button, #runtime-config-json, #apply-runtime-json, #save-runtime-json, #save-push-runtime-json, #firmware-target-form select, #firmware-target-form button, #clear-firmware-target").forEach((control) => {
              control.disabled = true;
              control.title = "廃止済みの機器は変更できません";
            });
          }

          document.addEventListener("click", (event) => {
            const button = event.target.closest("button");
            if (button) lastActionButton = button;
          }, true);

          function resultBox() {
            return document.getElementById("action-result");
          }

          function showResult(message, ok) {
            const box = resultBox();
            box.hidden = false;
            box.className = "result " + (ok ? "ok" : "error");
            box.textContent = message;
          }

          function showProgress(message) {
            pendingWorkCount += 1;
            const banner = document.getElementById("global-progress");
            const text = document.getElementById("global-progress-message");
            if (text) text.textContent = message || "処理中...";
            if (banner) banner.classList.add("active");
          }

          function hideProgress() {
            pendingWorkCount = Math.max(0, pendingWorkCount - 1);
            if (pendingWorkCount > 0) return;
            const banner = document.getElementById("global-progress");
            if (banner) banner.classList.remove("active");
          }

          function setButtonBusy(button, busy, message) {
            if (!button) return;
            if (busy) {
              if (!button.dataset.idleText) button.dataset.idleText = button.textContent;
              button.textContent = message || "処理中";
              button.disabled = true;
              button.setAttribute("aria-busy", "true");
              return;
            }
            button.disabled = false;
            button.removeAttribute("aria-busy");
            if (button.dataset.idleText) {
              button.textContent = button.dataset.idleText;
              delete button.dataset.idleText;
            }
          }

          function activateDetailTab(targetId, updateUrl = true) {
            const targetPanel = document.getElementById(targetId);
            if (!targetPanel) return;
            let activeKey = "overview";
            document.querySelectorAll(".tab-button").forEach((button) => {
              const selected = button.getAttribute("data-tab-target") === targetId;
              button.setAttribute("aria-selected", selected ? "true" : "false");
              button.setAttribute("tabindex", selected ? "0" : "-1");
              if (selected) activeKey = button.getAttribute("data-tab-key") || "overview";
            });
            document.querySelectorAll(".tab-panel").forEach((panel) => {
              panel.hidden = panel.id !== targetId;
            });
            if (updateUrl) {
              const url = new URL(window.location.href);
              if (activeKey === "overview") url.searchParams.delete("tab");
              else url.searchParams.set("tab", activeKey);
              window.history.replaceState({}, "", url);
            }
          }

          const detailTabButtons = Array.from(document.querySelectorAll(".tab-button"));
          detailTabButtons.forEach((button, index) => {
            button.addEventListener("click", () => activateDetailTab(button.getAttribute("data-tab-target")));
            button.addEventListener("keydown", (event) => {
              let nextIndex = null;
              if (event.key === "ArrowRight") nextIndex = (index + 1) % detailTabButtons.length;
              if (event.key === "ArrowLeft") nextIndex = (index - 1 + detailTabButtons.length) % detailTabButtons.length;
              if (event.key === "Home") nextIndex = 0;
              if (event.key === "End") nextIndex = detailTabButtons.length - 1;
              if (nextIndex === null) return;
              event.preventDefault();
              const nextButton = detailTabButtons[nextIndex];
              activateDetailTab(nextButton.getAttribute("data-tab-target"));
              nextButton.focus();
            });
          });
          const requestedTab = new URL(window.location.href).searchParams.get("tab");
          const tabAliases = { irrigation: "monitoring", config: "settings", diagnostics: "maintenance" };
          const requestedKey = tabAliases[requestedTab] || requestedTab || "overview";
          const requestedButton = detailTabButtons.find((button) => button.getAttribute("data-tab-key") === requestedKey);
          if (requestedButton) activateDetailTab(requestedButton.getAttribute("data-tab-target"), false);
          if (window.location.hash) {
            window.requestAnimationFrame(() => document.querySelector(window.location.hash)?.scrollIntoView({ block: "start" }));
          }

          function openDialog(dialog) {
            if (!dialog) return;
            if (typeof dialog.showModal === "function") dialog.showModal();
            else dialog.setAttribute("open", "");
          }

          function closeDialog(dialog) {
            if (!dialog) return;
            if (typeof dialog.close === "function") dialog.close();
            else dialog.removeAttribute("open");
          }

          async function requestJson(url, options, progressMessage) {
            const method = ((options || {}).method || "GET").toUpperCase();
            if (demoMode && method !== "GET") {
              return { demo: true };
            }
            const button = method === "GET" ? null : lastActionButton;
            lastActionButton = null;
            showProgress(progressMessage || (method === "GET" ? "読み込み中..." : "処理中..."));
            setButtonBusy(button, true, "処理中");
            try {
              const response = await fetch(url, options || {});
              const text = await response.text();
              let body = {};
              if (text) {
                try {
                  body = JSON.parse(text);
                } catch (error) {
                  body = { error: text };
                }
              }
              if (!response.ok) {
                throw new Error(body.error || ("HTTP " + response.status));
              }
              return body;
            } finally {
              setButtonBusy(button, false);
              hideProgress();
            }
          }

          function reloadSoon() {
            if (demoMode) {
              return;
            }
            showProgress("反映内容を読み込んでいます...");
            window.setTimeout(() => window.location.reload(), 500);
          }

          function graphDates(chartId) {
            const graph = document.getElementById(chartId);
            if (!graph || !Array.isArray(graph.data)) return [];
            const dates = [];
            graph.data.forEach((trace) => {
              (trace.x || []).forEach((value) => {
                const date = new Date(value);
                if (!Number.isNaN(date.getTime())) dates.push(date);
              });
            });
            return dates;
          }

          function formatDateInput(date) {
            return date.toISOString().slice(0, 10);
          }

          function activateRangeButton(card, activeButton) {
            card.querySelectorAll(".range-controls button").forEach((button) => button.classList.remove("active"));
            if (activeButton) activeButton.classList.add("active");
          }

          function setChartRange(chartId, start, end) {
            if (!window.Plotly) return;
            window.Plotly.relayout(chartId, { "xaxis.range": [start.toISOString(), end.toISOString()] });
          }

          function setChartAllRange(chartId) {
            if (!window.Plotly) return;
            window.Plotly.relayout(chartId, { "xaxis.autorange": true });
          }

          function attachChartRangeControls(card) {
            const chartId = card.getAttribute("data-chart-id");
            const dates = graphDates(chartId);
            if (!dates.length) return;
            const minDate = new Date(Math.min(...dates.map((date) => date.getTime())));
            const maxDate = new Date(Math.max(...dates.map((date) => date.getTime())));
            const startInput = card.querySelector("[data-range-start]");
            const endInput = card.querySelector("[data-range-end]");
            if (startInput) startInput.value = formatDateInput(minDate);
            if (endInput) endInput.value = formatDateInput(maxDate);

            card.querySelectorAll("[data-range-days], [data-range-months], [data-range-all], [data-range-custom]").forEach((button) => {
              button.addEventListener("click", () => {
                if (button.hasAttribute("data-range-all")) {
                  setChartAllRange(chartId);
                  activateRangeButton(card, button);
                  return;
                }
                if (button.hasAttribute("data-range-custom")) {
                  const startValue = startInput ? startInput.value : "";
                  const endValue = endInput ? endInput.value : "";
                  if (!startValue || !endValue) {
                    showResult("カスタム期間の開始日と終了日を入力してください", false);
                    return;
                  }
                  const start = new Date(startValue + "T00:00:00");
                  const end = new Date(endValue + "T23:59:59");
                  if (start > end) {
                    showResult("カスタム期間の開始日は終了日より前にしてください", false);
                    return;
                  }
                  setChartRange(chartId, start, end);
                  activateRangeButton(card, button);
                  return;
                }
                const end = new Date(maxDate.getTime());
                const start = new Date(maxDate.getTime());
                if (button.hasAttribute("data-range-days")) {
                  start.setDate(start.getDate() - Number(button.getAttribute("data-range-days")));
                } else if (button.hasAttribute("data-range-months")) {
                  start.setMonth(start.getMonth() - Number(button.getAttribute("data-range-months")));
                }
                setChartRange(chartId, start, end);
                activateRangeButton(card, button);
              });
            });
          }

          function setHtmlAndRunScripts(container, html) {
            container.innerHTML = html;
            container.querySelectorAll("script").forEach((oldScript) => {
              const script = document.createElement("script");
              Array.from(oldScript.attributes).forEach((attr) => script.setAttribute(attr.name, attr.value));
              script.text = oldScript.textContent;
              oldScript.replaceWith(script);
            });
          }

          function showChartEmpty(card, message) {
            const body = card.querySelector(".chart-body");
            if (body) body.innerHTML = '<div class="empty">' + message + "</div>";
          }

          function ensurePlotlyLoaded() {
            if (window.Plotly) return Promise.resolve();
            if (plotlyLoadPromise) return plotlyLoadPromise;
            plotlyLoadPromise = new Promise((resolve, reject) => {
              const script = document.createElement("script");
              script.src = "/local/assets/plotly.min.js";
              script.onload = resolve;
              script.onerror = () => reject(new Error("Plotly を読み込めませんでした"));
              document.head.appendChild(script);
            });
            return plotlyLoadPromise;
          }

          async function loadCharts() {
            if (!chartEndpoint) return;
            const cards = Array.from(document.querySelectorAll(".chart-card[data-chart-kind]"));
            if (!cards.length) return;
            try {
              const [charts] = await Promise.all([requestJson(chartEndpoint, null, "推移グラフを読み込んでいます..."), ensurePlotlyLoaded()]);
              cards.forEach((card) => {
                const body = card.querySelector(".chart-body");
                const kind = card.getAttribute("data-chart-kind");
                const html = charts[kind];
                if (!body) return;
                if (!html) {
                  showChartEmpty(card, card.getAttribute("data-empty-message") || "時系列データはまだありません。");
                  return;
                }
                setHtmlAndRunScripts(body, html);
                window.setTimeout(() => attachChartRangeControls(card), 0);
              });
            } catch (error) {
              cards.forEach((card) => showChartEmpty(card, "推移グラフを読み込めませんでした: " + error.message));
            }
          }

          loadCharts();

          document.querySelectorAll("[data-state-action]").forEach((button) => {
            button.addEventListener("click", async () => {
              if (!selectedDeviceId) return;
              const action = button.getAttribute("data-state-action");
              const body = action === "approve" ? { approved_by: document.getElementById("approved-by").value || null } : {};
              try {
                await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/" + action, {
                  method: "POST",
                  headers: { "content-type": "application/json" },
                  body: JSON.stringify(body),
                }, "デバイス状態を更新しています...");
                showResult("デバイス状態を更新しました", true);
                reloadSoon();
              } catch (error) {
                showResult(error.message, false);
              }
            });
          });

          const metadataForm = document.getElementById("metadata-form");
          if (metadataForm) {
            metadataForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              const body = {
                name: document.getElementById("metadata-name").value || null,
                memo: document.getElementById("metadata-memo").value || null,
              };
              try {
                await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId), {
                  method: "PATCH",
                  headers: { "content-type": "application/json" },
                  body: JSON.stringify(body),
                }, "表示情報を保存しています...");
                showResult("表示情報を保存しました", true);
                reloadSoon();
              } catch (error) {
                showResult(error.message, false);
              }
            });
          }

          function padNumber(value) {
            return String(value).padStart(2, "0");
          }

          function scheduleToTime(schedule) {
            return padNumber(schedule.hour || 0) + ":" + padNumber(schedule.minute || 0);
          }

          function formatDurationSeconds(seconds) {
            seconds = Number(seconds);
            if (!Number.isFinite(seconds) || seconds <= 0) return "未設定";
            if (seconds % 3600 === 0) return String(seconds / 3600) + "時間";
            if (seconds % 60 === 0) return String(seconds / 60) + "分";
            return String(seconds) + "秒";
          }

          function todayDateString() {
            const date = new Date();
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, "0");
            const day = String(date.getDate()).padStart(2, "0");
            return year + "-" + month + "-" + day;
          }

          function scheduleFrequency(schedule) {
            const frequency = (schedule || {}).frequency || {};
            const mode = ["daily", "interval", "weekdays"].includes(frequency.mode) ? frequency.mode : "daily";
            return {
              mode,
              interval_days: Number.isInteger(frequency.interval_days) ? frequency.interval_days : 2,
              start_date: frequency.start_date || todayDateString(),
              weekdays: Array.isArray(frequency.weekdays) ? frequency.weekdays : [],
            };
          }

          function setFrequencyControlsVisible(row) {
            const mode = row.querySelector("[data-schedule-frequency-mode]").value;
            row.querySelectorAll("[data-frequency-panel]").forEach((panel) => {
              panel.hidden = panel.getAttribute("data-frequency-panel") !== mode;
            });
          }

          function normalizeMosfetSwitches(switches) {
            const source = Array.isArray(switches) ? switches : [];
            const savedById = new Map(source.filter((item) => item && item.switch_id).map((item) => [String(item.switch_id), item]));
            return deviceOutputCapabilities.map((capability) => {
              const saved = savedById.get(String(capability.switch_id)) || {};
              const notes = String(saved.notes || capability.notes || "").trim();
              const savedType = notes.split(/\\r?\\n/).find((line) => line.startsWith("equipment_type="));
              return {
                ...capability,
                name: String(saved.name || capability.name || capability.default_name).trim(),
                enabled: saved.enabled !== false,
                controlled_load: String(saved.controlled_load || capability.controlled_load || "").trim(),
                equipment_type: String(saved.equipment_type || (savedType ? savedType.slice("equipment_type=".length) : "") || capability.equipment_type || "other"),
                notes,
              };
            });
          }

          function channelLabel(channelMask) {
            const names = currentMosfetSwitches
              .filter((sw) => sw.enabled !== false && Number.isInteger(sw.channel_mask) && sw.channel_mask > 0 && (channelMask & sw.channel_mask))
              .map((sw) => sw.name || "接続口 " + sw.number);
            if (names.length) return names.join("・");
            return "現在の設定（この機種では利用できません）";
          }

          function scheduleChannelOptions(selectedValue) {
            const outputValues = currentMosfetSwitches
              .filter((sw) => sw.enabled !== false && Number.isInteger(sw.channel_mask) && sw.channel_mask > 0)
              .map((sw) => sw.channel_mask);
            const masks = [];
            for (let combination = 1; combination < (1 << outputValues.length); combination += 1) {
              let value = 0;
              outputValues.forEach((outputValue, index) => {
                if (combination & (1 << index)) value |= outputValue;
              });
              if (value > 0 && !masks.includes(value)) masks.push(value);
            }
            const options = masks.map((value) => ({ value, label: channelLabel(value), unsupported: false }));
            if (Number.isInteger(selectedValue) && selectedValue > 0 && !masks.includes(selectedValue)) {
              options.push({ value: selectedValue, label: "現在の設定（この機種では利用できません）", unsupported: true });
            }
            return options;
          }

          function setScheduleChannelOptions(select, selectedValue) {
            if (!select) return;
            const value = Number.isInteger(selectedValue) && selectedValue > 0 ? selectedValue : Number(select.value || 1);
            select.innerHTML = "";
            scheduleChannelOptions(value).forEach((option) => {
              const element = document.createElement("option");
              element.value = String(option.value);
              element.textContent = option.label;
              if (option.unsupported) element.dataset.unsupported = "true";
              select.appendChild(element);
            });
            if (select.querySelector('option[value="' + String(value) + '"]')) select.value = String(value);
          }

          function refreshScheduleChannelOptions() {
            currentMosfetSwitches = normalizeMosfetSwitches(collectMosfetSwitches());
            document.querySelectorAll("[data-schedule-channel]").forEach((select) => {
              setScheduleChannelOptions(select, Number(select.value || 1));
            });
          }

          function equipmentIcon(type) {
            const attributes = 'viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
            const icons = {
              pump: '<svg ' + attributes + '><path d="M12 46h40M18 46V26h9l5-8h11v28"/><circle cx="36" cy="32" r="7"/><path d="M43 26h9v-8M52 18h-6"/></svg>',
              valve: '<svg ' + attributes + '><path d="M8 32h15M41 32h15M23 24l9 8-9 8V24ZM41 24l-9 8 9 8V24Z"/><path d="M32 24V13M24 13h16"/></svg>',
              drip_line: '<svg ' + attributes + '><path d="M8 25h48M15 25v15M32 25v15M49 25v15"/><path d="M11 46c0-4 4-6 4-9 0 3 4 5 4 9a4 4 0 0 1-8 0ZM28 46c0-4 4-6 4-9 0 3 4 5 4 9a4 4 0 0 1-8 0ZM45 46c0-4 4-6 4-9 0 3 4 5 4 9a4 4 0 0 1-8 0Z"/></svg>',
              sprinkler: '<svg ' + attributes + '><path d="M32 50V32M23 50h18M22 32h20"/><path d="M15 24c4-6 9-9 17-9s13 3 17 9M8 18c6-8 14-12 24-12s18 4 24 12"/><path d="M19 28l-8 5M45 28l8 5"/></svg>',
              soil_sensor: '<svg ' + attributes + '><path d="M24 11h16v23H24zM28 34v20M36 34v20"/><path d="M15 50c8-5 26-5 34 0M29 21h6"/></svg>',
              light_sensor: '<svg ' + attributes + '><circle cx="32" cy="25" r="10"/><path d="M32 5v6M32 39v6M12 25h6M46 25h6M18 11l4 5M46 11l-4 5"/><path d="M18 53h28"/></svg>',
              sensor: '<svg ' + attributes + '><rect x="18" y="10" width="28" height="40" rx="6"/><path d="M25 19h14M25 27h14M25 35h8"/><circle cx="38" cy="41" r="3"/></svg>',
              other: '<svg ' + attributes + '><path d="M12 23h40v28H12zM21 23v-8h22v8M20 34h24M20 42h16"/></svg>',
            };
            return icons[type] || icons.other;
          }

          function equipmentOptions(sw) {
            const source = Array.isArray(sw.equipment_options) ? sw.equipment_options : [];
            return source.map((option) => typeof option === "string" ? {
              value: option,
              label: option,
              equipment_type: sw.equipment_type || "other",
              source: "設備の種類",
            } : option).filter((option) => option && option.value);
          }

          function equipmentTypeLabel(sw, type) {
            const match = (Array.isArray(sw.equipment_types) ? sw.equipment_types : []).find((item) => item.value === type);
            return match ? match.label : "接続する設備";
          }

          function updateEquipmentTypeNotes(notes, type) {
            const lines = String(notes || "").split(/\\r?\\n/).filter((line) => line && !line.startsWith("equipment_type="));
            const preservedNotes = lines.join("\\n");
            const typeToken = type && type !== "other" ? "equipment_type=" + type : "";
            const updatedNotes = [preservedNotes, typeToken].filter(Boolean).join("\\n");
            return updatedNotes.length <= 160 ? updatedNotes : preservedNotes;
          }

          function notifyBuilderChanged(row) {
            updateBuilderLane(row);
            refreshScheduleChannelOptions();
            renderMosfetFlow(collectMosfetSwitches());
            refreshRuntimeConfigPreview();
          }

          function renderEquipmentTargets(row) {
            const grid = row.querySelector("[data-equipment-target-grid]");
            const selectedType = row.querySelector("[data-mosfet-type]").value;
            const selectedValue = row.querySelector("[data-mosfet-load]").value;
            const enabled = row.querySelector("[data-mosfet-enabled]").checked;
            const options = row._equipmentOptions.filter((option) => option.equipment_type === selectedType || option.value === selectedValue);
            grid.innerHTML = "";
            const empty = document.createElement("button");
            empty.type = "button";
            empty.className = "equipment-card equipment-target-card";
            empty.dataset.equipmentTarget = "";
            empty.setAttribute("aria-pressed", String(!selectedValue));
            empty.disabled = !enabled;
            empty.innerHTML = equipmentIcon("other") + '<span><strong>あとで決める</strong><small>接続口だけ用意する</small></span>';
            grid.appendChild(empty);
            options.forEach((option) => {
              const card = document.createElement("button");
              card.type = "button";
              card.className = "equipment-card equipment-target-card";
              card.dataset.equipmentTarget = option.value;
              card.setAttribute("aria-pressed", String(option.value === selectedValue));
              card.disabled = !enabled;
              card.innerHTML = equipmentIcon(option.equipment_type || selectedType) + "<span></span>";
              const copy = card.querySelector("span");
              const title = document.createElement("strong");
              title.textContent = option.label || option.value;
              const source = document.createElement("small");
              source.textContent = option.source || "設備の候補";
              copy.append(title, source);
              grid.appendChild(card);
            });
            grid.querySelectorAll("[data-equipment-target]").forEach((card) => card.addEventListener("click", () => {
              row.querySelector("[data-mosfet-load]").value = card.dataset.equipmentTarget || "";
              renderEquipmentTargets(row);
              notifyBuilderChanged(row);
            }));
          }

          function updateBuilderLane(row) {
            const enabled = row.querySelector("[data-mosfet-enabled]").checked;
            const selectedType = row.querySelector("[data-mosfet-type]").value || "other";
            row.classList.toggle("connected", enabled);
            row.classList.toggle("disconnected", !enabled);
            row.querySelector("[data-builder-state]").textContent = enabled ? "つながっています" : "まだつながっていません";
            row.querySelector("[data-equipment-preview]").innerHTML = equipmentIcon(selectedType);
            row.querySelector("[data-equipment-preview-label]").textContent = equipmentTypeLabel(row._switch, selectedType);
            row.querySelectorAll("[data-equipment-type]").forEach((card) => {
              card.disabled = !enabled;
              card.setAttribute("aria-pressed", String(card.dataset.equipmentType === selectedType));
            });
            row.querySelectorAll("[data-equipment-target]").forEach((card) => { card.disabled = !enabled; });
          }

          function createMosfetSwitchRow(sw) {
            const row = document.createElement("div");
            row.className = "output-edit-row";
            row.dataset.outputId = sw.switch_id;
            row._switch = sw;
            row._equipmentOptions = equipmentOptions(sw);
            row.innerHTML = '<div class="builder-port-card"><span class="builder-port-symbol" aria-hidden="true">⌁</span><span><strong data-port-label></strong><small data-role-label></small></span><label class="builder-toggle"><input data-mosfet-enabled type="checkbox"><span class="builder-toggle-track" aria-hidden="true"></span><span>使う</span></label></div><div class="builder-wire" aria-hidden="true"></div><div class="builder-endpoint"><div class="builder-endpoint-head"><span class="builder-endpoint-preview" data-equipment-preview aria-hidden="true"></span><span><strong data-equipment-preview-label></strong><small data-builder-state></small></span></div><div><span class="builder-choice-label">1. 動かす設備を絵から選ぶ</span><div class="equipment-type-grid" data-equipment-type-grid></div></div><div><span class="builder-choice-label">2. どの設備につなぐか選ぶ</span><div class="equipment-target-grid" data-equipment-target-grid></div></div><details class="builder-name-details"><summary>画面に出す名前を整える</summary><div class="detail-body"><label>この水やりルートの名前</label><input data-mosfet-name type="text" maxlength="64" required></div></details><input data-mosfet-type type="hidden"><input data-mosfet-load type="hidden"></div>';
            row.querySelector("[data-port-label]").textContent = "接続口 " + String(sw.number);
            row.querySelector("[data-role-label]").textContent = String(sw.role_label || "設備") + "専用";
            row.querySelector("[data-mosfet-enabled]").checked = sw.enabled !== false;
            row.querySelector("[data-mosfet-name]").value = sw.name || "";
            row.querySelector("[data-mosfet-type]").value = sw.equipment_type || "other";
            row.querySelector("[data-mosfet-load]").value = sw.controlled_load || "";
            const typeGrid = row.querySelector("[data-equipment-type-grid]");
            (Array.isArray(sw.equipment_types) ? sw.equipment_types : []).forEach((type) => {
              const card = document.createElement("button");
              card.type = "button";
              card.className = "equipment-card";
              card.dataset.equipmentType = type.value;
              card.innerHTML = equipmentIcon(type.value) + "<strong></strong><small></small>";
              card.querySelector("strong").textContent = type.label;
              card.querySelector("small").textContent = type.description;
              card.addEventListener("click", () => {
                const previousType = row.querySelector("[data-mosfet-type]").value;
                row.querySelector("[data-mosfet-type]").value = type.value;
                const selectedOption = row._equipmentOptions.find((option) => option.value === row.querySelector("[data-mosfet-load]").value);
                if (previousType !== type.value && selectedOption && selectedOption.equipment_type !== type.value) row.querySelector("[data-mosfet-load]").value = "";
                renderEquipmentTargets(row);
                notifyBuilderChanged(row);
              });
              typeGrid.appendChild(card);
            });
            row.querySelector("[data-mosfet-enabled]").addEventListener("input", () => {
              renderEquipmentTargets(row);
              notifyBuilderChanged(row);
            });
            row.querySelector("[data-mosfet-name]").addEventListener("input", () => notifyBuilderChanged(row));
            renderEquipmentTargets(row);
            updateBuilderLane(row);
            return row;
          }

          function renderMosfetFlow(switches) {
            const map = document.getElementById("output-connection-map");
            if (!map) return;
            map.innerHTML = "";
            normalizeMosfetSwitches(switches).forEach((sw) => {
              const item = document.createElement("div");
              item.className = "switch-output " + (sw.enabled !== false ? "enabled" : "disabled");
              const dot = document.createElement("span");
              dot.className = "switch-output-dot";
              const icon = document.createElement("span");
              icon.className = "switch-output-icon";
              icon.setAttribute("aria-hidden", "true");
              icon.innerHTML = equipmentIcon(sw.equipment_type || "other");
              const copy = document.createElement("div");
              const title = document.createElement("strong");
              title.textContent = sw.name || "接続口 " + sw.number;
              const target = document.createElement("small");
              target.textContent = sw.controlled_load || "接続先未設定";
              copy.append(title, target);
              const terminal = document.createElement("span");
              terminal.className = "terminal";
              terminal.textContent = "接続口 " + String(sw.number);
              item.append(dot, icon, copy, terminal);
              map.appendChild(item);
            });
            if (!map.children.length) map.textContent = "この機種には編集できる接続口がありません。";
          }

          function renderMosfetSwitches(switches) {
            const editor = document.getElementById("mosfet-switch-editor");
            if (!editor) return;
            editor.innerHTML = "";
            currentMosfetSwitches = normalizeMosfetSwitches(switches);
            currentMosfetSwitches.forEach((sw) => editor.appendChild(createMosfetSwitchRow(sw)));
            renderMosfetFlow(currentMosfetSwitches);
          }

          function collectMosfetSwitches() {
            const editor = document.getElementById("mosfet-switch-editor");
            if (!editor) return [...currentMosfetSwitches, ...unsupportedOutputSettings];
            const capabilitiesById = new Map(deviceOutputCapabilities.map((item) => [String(item.switch_id), item]));
            const supported = Array.from(editor.querySelectorAll(".output-edit-row")).map((row) => {
              const capability = capabilitiesById.get(row.dataset.outputId);
              return {
                switch_id: capability.switch_id,
                name: row.querySelector("[data-mosfet-name]").value.trim() || capability.default_name,
                enabled: row.querySelector("[data-mosfet-enabled]").checked,
                role: capability.role,
                terminal: capability.terminal,
                channel_mask: capability.channel_mask,
                controlled_load: row.querySelector("[data-mosfet-load]").value,
                notes: updateEquipmentTypeNotes(row._switch.notes || capability.notes || "", row.querySelector("[data-mosfet-type]").value),
              };
            });
            return [...supported, ...unsupportedOutputSettings];
          }

          const outputSettingsDialog = document.getElementById("output-settings-dialog");
          const outputSettingsTrigger = document.getElementById("open-output-settings");
          let outputSettingsSnapshot = [];
          function openOutputSettings() {
            outputSettingsSnapshot = JSON.parse(JSON.stringify(collectMosfetSwitches()));
            openDialog(outputSettingsDialog);
          }
          outputSettingsTrigger?.addEventListener("click", openOutputSettings);
          outputSettingsTrigger?.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            openOutputSettings();
          });
          function cancelOutputSettings() {
            renderMosfetSwitches(outputSettingsSnapshot);
            refreshScheduleChannelOptions();
            closeDialog(outputSettingsDialog);
            outputSettingsTrigger?.focus();
          }
          document.querySelectorAll("[data-close-output-dialog], [data-cancel-output-dialog]").forEach((button) => {
            button.addEventListener("click", cancelOutputSettings);
          });
          document.querySelector("[data-apply-output-dialog]")?.addEventListener("click", () => {
            currentMosfetSwitches = normalizeMosfetSwitches(collectMosfetSwitches());
            renderMosfetFlow(currentMosfetSwitches);
            refreshScheduleChannelOptions();
            refreshRuntimeConfigPreview();
            document.getElementById("runtime-config-form")?.dispatchEvent(new Event("change", { bubbles: true }));
            closeDialog(outputSettingsDialog);
            outputSettingsTrigger?.focus();
          });

          function updateSoilCalibrationAction(mode) {
            const summary = document.getElementById("soil-calibration-action-summary");
            if (!summary) return;
            const labels = {
              capture_dry: "次回反映: 乾いた基準を記録",
              capture_wet: "次回反映: 湿った基準を記録",
              reset: "次回反映: 基準をリセット",
            };
            summary.textContent = labels[mode] || "";
            summary.hidden = !labels[mode];
          }

          const soilCalibrationGuide = document.getElementById("soil-calibration-guide");
          document.getElementById("open-soil-calibration-guide")?.addEventListener("click", () => openDialog(soilCalibrationGuide));
          document.querySelectorAll("[data-close-calibration-guide]").forEach((button) => {
            button.addEventListener("click", () => closeDialog(soilCalibrationGuide));
          });
          document.querySelectorAll("[data-calibration-mode]").forEach((button) => {
            button.addEventListener("click", () => {
              const mode = button.getAttribute("data-calibration-mode") || "normal";
              const select = document.getElementById("soil-calibration-mode");
              if (select) {
                select.value = mode;
                select.dispatchEvent(new Event("input", { bubbles: true }));
                select.dispatchEvent(new Event("change", { bubbles: true }));
              }
              updateSoilCalibrationAction(mode);
              refreshRuntimeConfigPreview();
              closeDialog(soilCalibrationGuide);
              document.getElementById("soil-moisture-reference")?.scrollIntoView({ behavior: "smooth", block: "center" });
            });
          });

          function createScheduleRow(schedule) {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.innerHTML = (isFertigationDevice ? [
              '<div><label>ポンプ運転を始める時刻</label><input data-schedule-time type="time" required></div>',
              '<label class="switch-row"><input data-schedule-enabled type="checkbox"> この予約を使う</label>',
              '<input data-schedule-duration type="hidden" value="1">',
              '<select data-schedule-channel hidden><option value="1">固定工程</option></select>',
              '<select data-schedule-frequency-mode hidden><option value="daily">毎日</option></select>',
              '<input data-schedule-interval-days type="hidden" value="1">',
              '<input data-schedule-start-date type="hidden">',
              '<select data-schedule-weekdays hidden multiple></select>',
              '<button type="button" class="icon-button" data-remove-schedule aria-label="予約を削除">－ <span>削除</span></button>',
            ] : [
              '<div><label>時刻</label><input data-schedule-time type="time" required></div>',
              '<div data-schedule-duration-field><label>灌水時間（秒）</label><input data-schedule-duration type="number" min="1" max="3600" step="1" required></div>',
              '<div><label>水を送る接続先</label><select data-schedule-channel></select></div>',
              '<div><label>頻度</label><select data-schedule-frequency-mode><option value="daily">毎日</option><option value="interval">日にちごと</option><option value="weekdays">曜日指定</option></select></div>',
              '<div data-frequency-panel="interval"><label>間隔</label><input data-schedule-interval-days type="number" min="1" max="31" step="1"></div>',
              '<div data-frequency-panel="interval"><label>開始日</label><input data-schedule-start-date type="date"></div>',
              '<div data-frequency-panel="weekdays"><label>曜日</label><select data-schedule-weekdays multiple size="4"><option value="0">日</option><option value="1">月</option><option value="2">火</option><option value="3">水</option><option value="4">木</option><option value="5">金</option><option value="6">土</option></select></div>',
              '<button type="button" class="icon-button" data-remove-schedule aria-label="予約を削除">－ <span>削除</span></button>',
            ]).join("");
            const spacingWarning = document.createElement("p");
            spacingWarning.className = "schedule-row-warning";
            spacingWarning.dataset.scheduleSpacingMessage = "";
            spacingWarning.hidden = true;
            row.appendChild(spacingWarning);
            const frequency = scheduleFrequency(schedule || {});
            row.querySelector("[data-schedule-time]").value = scheduleToTime(schedule || {});
            row.querySelector("[data-schedule-duration]").value = String((schedule || {}).duration_sec || 1);
            setScheduleChannelOptions(row.querySelector("[data-schedule-channel]"), Number((schedule || {}).channel_mask || 1));
            row.querySelector("[data-schedule-frequency-mode]").value = frequency.mode;
            const enabled = row.querySelector("[data-schedule-enabled]");
            if (enabled) enabled.checked = (schedule || {}).enabled !== false;
            row.querySelector("[data-schedule-interval-days]").value = String(frequency.interval_days || 2);
            row.querySelector("[data-schedule-start-date]").value = frequency.start_date || todayDateString();
            Array.from(row.querySelector("[data-schedule-weekdays]").options).forEach((option) => {
              option.selected = frequency.weekdays.includes(Number(option.value));
            });
            if (!isFertigationDevice) setFrequencyControlsVisible(row);
            row.querySelector("[data-remove-schedule]").addEventListener("click", () => {
              if (document.querySelectorAll("#schedule-editor .schedule-row").length <= 1) {
                showResult("予約は最低 1 件必要です", false);
                return;
              }
              row.remove();
              refreshRuntimeConfigPreview();
              document.getElementById("runtime-config-form")?.dispatchEvent(new Event("change", { bubbles: true }));
            });
            if (!isFertigationDevice) row.querySelector("[data-schedule-frequency-mode]").addEventListener("input", () => setFrequencyControlsVisible(row));
            row.querySelectorAll("input, select").forEach((input) => input.addEventListener("input", refreshRuntimeConfigPreview));
            return row;
          }

          function selectedIrrigationMode() {
            return document.querySelector('input[name="irrigation-mode"]:checked')?.value === "pulse" ? "pulse" : "standard";
          }

          function updateIrrigationModeUi(applyPulseDefaults = false) {
            const pulseMode = selectedIrrigationMode() === "pulse";
            const patternSettings = document.getElementById("irrigation-pattern-settings");
            if (patternSettings) patternSettings.hidden = !pulseMode;
            document.querySelectorAll("[data-schedule-duration-field]").forEach((field) => {
              field.hidden = pulseMode;
            });

            const onInput = document.getElementById("watering-pattern-on-sec");
            const offInput = document.getElementById("watering-pattern-off-sec");
            const repeatInput = document.getElementById("watering-pattern-repeat-count");
            if (pulseMode && applyPulseDefaults) {
              const hasSavedPattern = Number(onInput?.value) > 0 || Number(offInput?.value) > 0 || Number(repeatInput?.value) > 0;
              if (!hasSavedPattern) {
                onInput.value = "60";
                offInput.value = "60";
                repeatInput.value = "3";
              } else {
                if (Number(onInput?.value) <= 0) onInput.value = "60";
                if (Number(offInput?.value) < 0 || offInput?.value === "") offInput.value = "0";
                if (Number(repeatInput?.value) <= 0) repeatInput.value = "3";
              }
            }

            const summary = document.getElementById("irrigation-pattern-summary");
            if (summary) {
              const onSec = Math.max(0, Number(onInput?.value) || 0);
              const offSec = Math.max(0, Number(offInput?.value) || 0);
              const repeatCount = Math.max(0, Number(repeatInput?.value) || 0);
              const wateringSec = onSec * repeatCount;
              const elapsedSec = wateringSec + offSec * Math.max(0, repeatCount - 1);
              summary.textContent = `水を出す合計 ${formatDurationSeconds(wateringSec)} ／ 予約開始から終了まで ${formatDurationSeconds(elapsedSec)}`;
            }
          }

          const envCalibrationProfiles = {
            par_umol_m2_s: { label: "光の表示を合わせる", help: "基準となる光量計と同じ値へダイヤルを合わせます", unit: "µmol/m²/s", min: 0, max: 2500, step: 10, initial: 1000, sensor: "par" },
            soil_moisture_percent: { label: "土壌水分の表示を合わせる", help: "基準となる水分計や、決めた湿り具合へ合わせます", unit: "%", min: 0, max: 100, step: 1, initial: 50, sensor: "soil" },
            soil_temperature_c: { label: "地温の表示を合わせる", help: "土に挿した基準温度計と同じ値へ合わせます", unit: "℃", min: -20, max: 60, step: 0.5, initial: 20, sensor: "soil" },
            soil_ec_us_cm: { label: "土壌ECの表示を合わせる", help: "標準液または基準計の値へ合わせます", unit: "µS/cm", min: 0, max: 5000, step: 10, initial: 1000, sensor: "soil" },
            soil_ph: { label: "土壌pHの表示を合わせる", help: "標準液または基準計の値へ合わせます", unit: "pH", min: 0, max: 14, step: 0.1, initial: 7, sensor: "soil" },
            soil_n_mg_kg: { label: "窒素の表示を合わせる", help: "基準となる分析値へ合わせます", unit: "mg/kg", min: 0, max: 1000, step: 1, initial: 100, sensor: "soil" },
            soil_p_mg_kg: { label: "リンの表示を合わせる", help: "基準となる分析値へ合わせます", unit: "mg/kg", min: 0, max: 1000, step: 1, initial: 100, sensor: "soil" },
            soil_k_mg_kg: { label: "カリウムの表示を合わせる", help: "基準となる分析値へ合わせます", unit: "mg/kg", min: 0, max: 1000, step: 1, initial: 100, sensor: "soil" },
          };
          let envCalibrationState = {};

          function formatEnvCalibrationSummary(target, value) {
            const profile = envCalibrationProfiles[target];
            if (!profile || typeof value !== "number" || !Number.isFinite(value)) return "調整済み";
            const digits = profile.step < 1 ? 1 : 0;
            return "基準 " + value.toFixed(digits) + " " + profile.unit;
          }

          function refreshEnvCalibrationSummaries(envCalibration = {}) {
            for (const target of Object.keys(envCalibrationProfiles)) {
              const summary = document.querySelector('[data-env-calibration-summary="' + target + '"]');
              if (!summary) continue;
              const metricCalibration = envCalibration[target] || {};
              let label = metricCalibration.calibrated ? "調整済み" : "未調整";
              const isRecordedTarget = envCalibration.target === target
                && envCalibration.mode !== "reset"
                && (envCalibration.mode === "capture_reference" || Boolean(envCalibration.request_id));
              if (isRecordedTarget) label = formatEnvCalibrationSummary(target, Number(envCalibration.reference_value));
              summary.textContent = label;
              summary.classList.toggle("recorded", label !== "未調整");
            }
          }

          function envSensorEnabled(sensor) {
            const toggle = document.getElementById(sensor === "par" ? "env-par-enabled" : "env-soil-enabled");
            const card = document.querySelector('[data-env-sensor-card="' + sensor + '"]');
            return Boolean(toggle?.checked && card && !card.hidden);
          }

          function refreshEnvCalibrationDial() {
            const target = document.getElementById("env-calibration-target")?.value || "par_umol_m2_s";
            const profile = envCalibrationProfiles[target] || envCalibrationProfiles.par_umol_m2_s;
            const range = document.getElementById("env-calibration-reference-value");
            if (!range) return;
            const value = Number(range.value);
            const digits = profile.step < 1 ? 1 : 0;
            const displayValue = Number.isFinite(value) ? value.toFixed(digits) : String(profile.initial);
            const progress = Math.max(0, Math.min(1, (value - profile.min) / (profile.max - profile.min || 1)));
            document.getElementById("env-calibration-reference-display").textContent = displayValue;
            document.getElementById("env-calibration-dial-value").textContent = displayValue;
            document.getElementById("env-calibration-unit").textContent = profile.unit;
            document.getElementById("env-calibration-min").textContent = String(profile.min);
            document.getElementById("env-calibration-mid").textContent = String((profile.min + profile.max) / 2);
            document.getElementById("env-calibration-max").textContent = String(profile.max);
            document.getElementById("env-calibration-workbench")?.style.setProperty("--dial-progress", String(progress * 360) + "deg");
          }

          function selectEnvCalibrationTarget(target, options = {}) {
            const profile = envCalibrationProfiles[target];
            const targetSelect = document.getElementById("env-calibration-target");
            const range = document.getElementById("env-calibration-reference-value");
            const bench = document.getElementById("env-calibration-workbench");
            const dialog = document.getElementById("env-calibration-dialog");
            if (!profile || !targetSelect || !range || !bench) return;
            const changed = targetSelect.value !== target;
            targetSelect.value = target;
            range.min = String(profile.min);
            range.max = String(profile.max);
            range.step = String(profile.step);
            const desiredValue = typeof options.value === "number" ? options.value : changed ? profile.initial : Number(range.value);
            range.value = String(Math.max(profile.min, Math.min(profile.max, Number.isFinite(desiredValue) ? desiredValue : profile.initial)));
            document.getElementById("env-calibration-title").textContent = profile.label;
            document.getElementById("env-calibration-help").textContent = profile.help;
            document.querySelectorAll("[data-env-tune-target]").forEach((button) => {
              button.setAttribute("aria-pressed", String(button.dataset.envTuneTarget === target));
            });
            const canTune = envSensorEnabled(profile.sensor);
            refreshEnvCalibrationDial();
            if (options.reveal && canTune && dialog && !dialog.open) dialog.showModal();
          }

          function updateEnvSensorVisibility() {
            for (const sensor of ["par", "soil"]) {
              const enabled = envSensorEnabled(sensor);
              document.querySelector('[data-env-sensor-card="' + sensor + '"]')?.classList.toggle("active", enabled);
              document.querySelectorAll('[data-env-sensor-panel="' + sensor + '"]').forEach((panel) => { panel.hidden = !enabled; });
              document.querySelectorAll('[data-env-sensor-advanced="' + sensor + '"]').forEach((panel) => { panel.hidden = !enabled; });
              const state = document.querySelector('[data-env-sensor-state="' + sensor + '"]');
              if (state) state.textContent = enabled ? "使用中" : "使用しない";
            }
            const details = document.querySelector(".sensor-maintenance-details");
            if (details) details.hidden = !envSensorEnabled("par") && !envSensorEnabled("soil");
            const target = document.getElementById("env-calibration-target")?.value;
            const profile = envCalibrationProfiles[target];
            const calibrationDialog = document.getElementById("env-calibration-dialog");
            if (profile && !envSensorEnabled(profile.sensor) && calibrationDialog?.open) calibrationDialog.close();
            const settleRange = document.getElementById("env-power-settle-ms");
            const settleDisplay = document.getElementById("env-power-settle-display");
            if (settleRange && settleDisplay) settleDisplay.textContent = (Number(settleRange.value || 0) / 1000).toFixed(1) + "秒";
          }

          function bindEnvSensorWorkbench() {
            document.querySelectorAll("#env-par-enabled, #env-soil-enabled").forEach((toggle) => toggle.addEventListener("input", updateEnvSensorVisibility));
            document.querySelectorAll("[data-env-tune-target]").forEach((button) => button.addEventListener("click", () => {
              document.getElementById("env-calibration-mode").value = "normal";
              selectEnvCalibrationTarget(button.dataset.envTuneTarget, { reveal: true });
            }));
            document.querySelectorAll("[data-close-env-calibration]").forEach((button) => button.addEventListener("click", () => document.getElementById("env-calibration-dialog")?.close()));
            document.getElementById("env-calibration-reference-value")?.addEventListener("input", refreshEnvCalibrationDial);
            document.getElementById("env-power-settle-ms")?.addEventListener("input", updateEnvSensorVisibility);
            document.querySelectorAll("[data-env-calibration-action]").forEach((button) => button.addEventListener("click", () => {
              const mode = button.dataset.envCalibrationAction;
              document.getElementById("env-calibration-mode").value = mode;
              const target = document.getElementById("env-calibration-target").value;
              const referenceValue = Number(document.getElementById("env-calibration-reference-value").value);
              envCalibrationState = { ...envCalibrationState, mode, target, reference_value: referenceValue };
              refreshEnvCalibrationSummaries(envCalibrationState);
              const title = document.getElementById("env-calibration-title");
              if (title) title.textContent = mode === "reset" ? "未校正へ戻す予約をしました" : "この値を次回の基準として記録します";
              document.getElementById("runtime-config-form")?.dispatchEvent(new Event("change", { bubbles: true }));
              refreshRuntimeConfigPreview();
              document.getElementById("env-calibration-dialog")?.close();
            }));
          }

          function updateTimedOutputCard(card, { deriveToggle = false, toggleChanged = false } = {}) {
            const toggle = card.querySelector("[data-timed-output-enabled]");
            const settings = card.querySelector("[data-timed-output-settings]");
            const fields = Array.from(card.querySelectorAll("[data-timed-output-field]"));
            const onSec = card.querySelector("[data-timed-output-on-sec]");
            const repeatCount = card.querySelector("[data-timed-output-repeat-count]");
            if (!toggle || !settings || !onSec || !repeatCount) return;
            if (deriveToggle) toggle.checked = Number(repeatCount.value || 0) > 0;
            if (toggleChanged && toggle.checked) {
              const previousOnSec = Number(onSec.dataset.lastEnabledValue || 0);
              const previousRepeatCount = Number(repeatCount.dataset.lastEnabledValue || 0);
              if (Number(onSec.value || 0) <= 0) onSec.value = String(previousOnSec > 0 ? previousOnSec : 1);
              if (Number(repeatCount.value || 0) <= 0) repeatCount.value = String(previousRepeatCount >= 1 && previousRepeatCount <= 99 ? previousRepeatCount : 1);
            } else if (toggleChanged && !toggle.checked) {
              const currentOnSec = Number(onSec.value || 0);
              const currentRepeatCount = Number(repeatCount.value || 0);
              if (currentOnSec > 0) onSec.dataset.lastEnabledValue = String(currentOnSec);
              if (currentRepeatCount > 0) repeatCount.dataset.lastEnabledValue = String(currentRepeatCount);
              repeatCount.value = "0";
            }
            const enabled = toggle.checked;
            settings.hidden = !enabled;
            fields.forEach((field) => { field.disabled = !enabled; });
            toggle.setAttribute("aria-expanded", String(enabled));
            card.classList.toggle("enabled", enabled);
            card.classList.toggle("disabled", !enabled);
            const summary = card.querySelector("[data-timed-output-summary]");
            if (summary) {
              summary.textContent = enabled
                ? String(Number(onSec.value || 0)) + "秒 × " + String(Number(repeatCount.value || 0)) + "回"
                : "無効（時間設定は保持）";
            }
          }

          function syncTimedOutputControlsFromValues() {
            document.querySelectorAll("[data-timed-output-card]").forEach((card) => {
              const onSec = card.querySelector("[data-timed-output-on-sec]");
              const repeatCount = card.querySelector("[data-timed-output-repeat-count]");
              if (Number(onSec?.value || 0) > 0) onSec.dataset.lastEnabledValue = onSec.value;
              if (Number(repeatCount?.value || 0) > 0) repeatCount.dataset.lastEnabledValue = repeatCount.value;
              updateTimedOutputCard(card, { deriveToggle: true });
            });
          }

          function bindTimedOutputControls() {
            document.querySelectorAll("[data-timed-output-card]").forEach((card) => {
              card.querySelector("[data-timed-output-enabled]")?.addEventListener("input", () => updateTimedOutputCard(card, { toggleChanged: true }));
              card.querySelectorAll("[data-timed-output-field]").forEach((field) => field.addEventListener("input", () => updateTimedOutputCard(card)));
            });
          }

          function renderRuntimeConfigForm(config) {
            config = applyRuntimeConfigFixedValues(config || {});
            const threshold = Number.isInteger(config.moisture_threshold) ? config.moisture_threshold : 35;
            const thresholdRange = document.getElementById("moisture-threshold");
            const thresholdNumber = document.getElementById("moisture-threshold-number");
            if (thresholdRange) thresholdRange.value = String(threshold);
            if (thresholdNumber) thresholdNumber.value = String(threshold);

            const ntpServer = document.getElementById("ntp-server");
            if (ntpServer) ntpServer.value = config.ntp_server || "pool.ntp.org";
            const timezoneOffset = document.getElementById("timezone-offset");
            if (timezoneOffset) timezoneOffset.value = String(Number.isInteger(config.timezone_offset_sec) ? config.timezone_offset_sec : 32400);
            const forceWatering = document.getElementById("force-watering");
            if (forceWatering) forceWatering.checked = Boolean(config.force_watering);
            const startupWateringTest = config.startup_watering_test || {};
            const startupWateringTestEnabled = document.getElementById("startup-watering-test-enabled");
            if (startupWateringTestEnabled) startupWateringTestEnabled.checked = Boolean(startupWateringTest.enabled);
            const startupWateringTestDuration = document.getElementById("startup-watering-test-duration");
            if (startupWateringTestDuration) startupWateringTestDuration.value = String(Number.isInteger(startupWateringTest.duration_sec) ? startupWateringTest.duration_sec : 5);
            const startupWateringTestChannel = document.getElementById("startup-watering-test-channel");
            if (startupWateringTestChannel) startupWateringTestChannel.value = String(Number.isInteger(startupWateringTest.channel_mask) ? startupWateringTest.channel_mask : 1);
            const debugLogOnWake = document.getElementById("debug-log-on-wake");
            if (debugLogOnWake) debugLogOnWake.checked = Boolean(config.debug_log_on_wake);
            const otaCheckInterval = document.getElementById("ota-check-interval");
            if (otaCheckInterval) otaCheckInterval.value = String(Number.isInteger(config.ota_check_interval_sec) ? config.ota_check_interval_sec : 21600);

            const wateringPattern = config.watering_pattern || {};
            const irrigationMode = document.getElementById(wateringPattern.enabled ? "irrigation-mode-pulse" : "irrigation-mode-standard");
            if (irrigationMode) irrigationMode.checked = true;
            const wateringPatternOnSec = document.getElementById("watering-pattern-on-sec");
            if (wateringPatternOnSec) wateringPatternOnSec.value = String(Number.isInteger(wateringPattern.on_sec) ? wateringPattern.on_sec : 0);
            const wateringPatternOffSec = document.getElementById("watering-pattern-off-sec");
            if (wateringPatternOffSec) wateringPatternOffSec.value = String(Number.isInteger(wateringPattern.off_sec) ? wateringPattern.off_sec : 0);
            const wateringPatternRepeatCount = document.getElementById("watering-pattern-repeat-count");
            if (wateringPatternRepeatCount) wateringPatternRepeatCount.value = String(Number.isInteger(wateringPattern.repeat_count) ? wateringPattern.repeat_count : 0);

            const soilCalibration = config.soil_calibration || {};
            const soilCalibrationMode = document.getElementById("soil-calibration-mode");
            if (soilCalibrationMode) soilCalibrationMode.value = typeof soilCalibration.mode === "string" ? soilCalibration.mode : "normal";
            updateSoilCalibrationAction(soilCalibrationMode ? soilCalibrationMode.value : "normal");
            const soilCalibrationCalibrated = document.getElementById("soil-calibration-calibrated");
            if (soilCalibrationCalibrated) soilCalibrationCalibrated.checked = Boolean(soilCalibration.calibrated);
            const soilCalibrationAutoMode = document.getElementById("soil-calibration-auto-mode");
            if (soilCalibrationAutoMode) soilCalibrationAutoMode.checked = Boolean(soilCalibration.auto_mode_enabled);
            const soilCalibrationApplyAuto = document.getElementById("soil-calibration-apply-auto");
            if (soilCalibrationApplyAuto) soilCalibrationApplyAuto.checked = Boolean(soilCalibration.apply_auto_calibration);
            const soilCalibrationDriftCheck = document.getElementById("soil-calibration-drift-check");
            if (soilCalibrationDriftCheck) soilCalibrationDriftCheck.checked = Boolean(soilCalibration.drift_check_enabled);
            const soilCalibrationDryRaw = document.getElementById("soil-calibration-dry-raw");
            if (soilCalibrationDryRaw) soilCalibrationDryRaw.value = String(Number.isInteger(soilCalibration.dry_raw) ? soilCalibration.dry_raw : 1895);
            const soilCalibrationWetRaw = document.getElementById("soil-calibration-wet-raw");
            if (soilCalibrationWetRaw) soilCalibrationWetRaw.value = String(Number.isInteger(soilCalibration.wet_raw) ? soilCalibration.wet_raw : 1285);
            const soilCalibrationMinDeltaRaw = document.getElementById("soil-calibration-min-delta-raw");
            if (soilCalibrationMinDeltaRaw) soilCalibrationMinDeltaRaw.value = String(Number.isInteger(soilCalibration.min_delta_raw) ? soilCalibration.min_delta_raw : 80);
            const soilCalibrationDriftToleranceRaw = document.getElementById("soil-calibration-drift-tolerance-raw");
            if (soilCalibrationDriftToleranceRaw) soilCalibrationDriftToleranceRaw.value = String(Number.isInteger(soilCalibration.drift_tolerance_raw) ? soilCalibration.drift_tolerance_raw : 120);
            const soilCalibrationSampleCount = document.getElementById("soil-calibration-sample-count");
            if (soilCalibrationSampleCount) soilCalibrationSampleCount.value = String(Number.isInteger(soilCalibration.sample_count) ? soilCalibration.sample_count : 20);
            const soilCalibrationSampleIntervalMs = document.getElementById("soil-calibration-sample-interval-ms");
            if (soilCalibrationSampleIntervalMs) soilCalibrationSampleIntervalMs.value = String(Number.isInteger(soilCalibration.sample_interval_ms) ? soilCalibration.sample_interval_ms : 40);

            const envSensors = config.env_sensors || {};
            const envPar = envSensors.par || {};
            const envSoil = envSensors.soil || {};
            const envParEnabled = document.getElementById("env-par-enabled");
            if (envParEnabled) envParEnabled.checked = envPar.enabled !== false;
            const envSoilEnabled = document.getElementById("env-soil-enabled");
            if (envSoilEnabled) envSoilEnabled.checked = Boolean(envSoil.enabled);
            const envParSlave = document.getElementById("env-par-slave");
            if (envParSlave) envParSlave.value = String(Number.isInteger(envPar.modbus_slave_id) ? envPar.modbus_slave_id : 1);
            const envParFunction = document.getElementById("env-par-function");
            if (envParFunction) envParFunction.value = String(Number.isInteger(envPar.modbus_function) ? envPar.modbus_function : 3);
            const envParRegister = document.getElementById("env-par-register");
            if (envParRegister) envParRegister.value = String(Number.isInteger(envPar.register) ? envPar.register : 0);
            const envSoilSlave = document.getElementById("env-soil-slave");
            if (envSoilSlave) envSoilSlave.value = String(Number.isInteger(envSoil.modbus_slave_id) ? envSoil.modbus_slave_id : 2);
            const envSoilFunction = document.getElementById("env-soil-function");
            if (envSoilFunction) envSoilFunction.value = String(Number.isInteger(envSoil.modbus_function) ? envSoil.modbus_function : 4);
            const envSoilStartRegister = document.getElementById("env-soil-start-register");
            if (envSoilStartRegister) envSoilStartRegister.value = String(Number.isInteger(envSoil.start_register) ? envSoil.start_register : 0);
            const envPowerSettleMs = document.getElementById("env-power-settle-ms");
            if (envPowerSettleMs) envPowerSettleMs.value = String(Number.isInteger(envSensors.power_settle_ms) ? envSensors.power_settle_ms : 800);

            const envCalibration = config.env_calibration || {};
            envCalibrationState = { ...envCalibration };
            const envCalibrationMode = document.getElementById("env-calibration-mode");
            if (envCalibrationMode) envCalibrationMode.value = typeof envCalibration.mode === "string" ? envCalibration.mode : "normal";
            const envCalibrationTarget = document.getElementById("env-calibration-target");
            if (envCalibrationTarget) envCalibrationTarget.value = typeof envCalibration.target === "string" ? envCalibration.target : "par_umol_m2_s";
            const envCalibrationReferenceValue = document.getElementById("env-calibration-reference-value");
            if (envCalibrationReferenceValue) envCalibrationReferenceValue.value = String(typeof envCalibration.reference_value === "number" ? envCalibration.reference_value : 0);
            setEnvMetricCalibration("par_umol_m2_s", "env-cal-par", envCalibration);
            setEnvMetricCalibration("soil_moisture_percent", "env-cal-moisture", envCalibration);
            setEnvMetricCalibration("soil_temperature_c", "env-cal-temperature", envCalibration);
            setEnvMetricCalibration("soil_ec_us_cm", "env-cal-ec", envCalibration);
            setEnvMetricCalibration("soil_ph", "env-cal-ph", envCalibration);
            setEnvMetricCalibration("soil_n_mg_kg", "env-cal-n", envCalibration);
            setEnvMetricCalibration("soil_p_mg_kg", "env-cal-p", envCalibration);
            setEnvMetricCalibration("soil_k_mg_kg", "env-cal-k", envCalibration);
            refreshEnvCalibrationSummaries(envCalibrationState);
            updateEnvSensorVisibility();
            selectEnvCalibrationTarget(envCalibrationTarget ? envCalibrationTarget.value : "par_umol_m2_s", {
              value: typeof envCalibration.reference_value === "number" ? envCalibration.reference_value : 0,
              reveal: false,
            });

            renderMosfetSwitches(config.mosfet_switches);

            document.querySelectorAll("[data-definition-path]").forEach((input) => {
              const value = getNestedValue(config, input.dataset.definitionPath);
              if (input.dataset.definitionType === "boolean") input.checked = Boolean(value);
              else if (value !== undefined && value !== null) input.value = String(value);
            });
            syncTimedOutputControlsFromValues();

            const editor = document.getElementById("schedule-editor");
            if (editor) {
              editor.innerHTML = "";
              const schedules = Array.isArray(config.schedules) && config.schedules.length ? config.schedules : [{ hour: 6, minute: 30, duration_sec: 1, channel_mask: 1, frequency: { mode: "daily" } }];
              schedules.slice(0, 8).forEach((schedule) => editor.appendChild(createScheduleRow(schedule)));
            }
            updateIrrigationModeUi();
            refreshRuntimeConfigPreview();
          }

          function collectRuntimeConfigFromForm() {
            const threshold = Number(document.getElementById("moisture-threshold-number").value);
            const timezoneOffset = Number(document.getElementById("timezone-offset").value);
            const otaCheckInterval = Number(document.getElementById("ota-check-interval").value);
            const mosfetSwitches = collectMosfetSwitches();
            const schedules = Array.from(document.querySelectorAll("#schedule-editor .schedule-row")).map((row) => {
              const time = row.querySelector("[data-schedule-time]").value || "00:00";
              const parts = time.split(":");
              const mode = row.querySelector("[data-schedule-frequency-mode]").value || "daily";
              const frequency = { mode };
              if (mode === "interval") {
                frequency.interval_days = Number(row.querySelector("[data-schedule-interval-days]").value);
                frequency.start_date = row.querySelector("[data-schedule-start-date]").value || todayDateString();
              } else if (mode === "weekdays") {
                frequency.weekdays = Array.from(row.querySelector("[data-schedule-weekdays]").selectedOptions).map((option) => Number(option.value));
              }
              return {
                enabled: row.querySelector("[data-schedule-enabled]")?.checked !== false,
                hour: Number(parts[0]),
                minute: Number(parts[1]),
                duration_sec: Number(row.querySelector("[data-schedule-duration]").value),
                channel_mask: Number(row.querySelector("[data-schedule-channel]").value),
                frequency,
              };
            });
            if (schedules.length < 1 || schedules.length > 8) throw new Error("灌水予約は 1〜8 件にしてください");
            const wateringPattern = supportsWateringPattern ? {
              enabled: selectedIrrigationMode() === "pulse",
              on_sec: Number(document.getElementById("watering-pattern-on-sec").value),
              off_sec: Number(document.getElementById("watering-pattern-off-sec").value),
              repeat_count: Number(document.getElementById("watering-pattern-repeat-count").value),
            } : structuredClone(initialRuntimeConfig.watering_pattern || { enabled: false, on_sec: 0, off_sec: 0, repeat_count: 0 });
            if (wateringPattern.enabled && (wateringPattern.on_sec <= 0 || wateringPattern.repeat_count <= 0)) {
              throw new Error("分割灌水は、水を出す時間と繰り返し回数を 1 以上にしてください");
            }
            const soilCalibrationMode = document.getElementById("soil-calibration-mode").value;
            const soilCalibration = {
              mode: soilCalibrationMode,
              request_id: soilCalibrationMode === "normal" ? "" : String(Date.now()),
              calibrated: document.getElementById("soil-calibration-calibrated").checked,
              auto_mode_enabled: document.getElementById("soil-calibration-auto-mode").checked,
              apply_auto_calibration: document.getElementById("soil-calibration-apply-auto").checked,
              drift_check_enabled: document.getElementById("soil-calibration-drift-check").checked,
              dry_raw: Number(document.getElementById("soil-calibration-dry-raw").value),
              wet_raw: Number(document.getElementById("soil-calibration-wet-raw").value),
              min_delta_raw: Number(document.getElementById("soil-calibration-min-delta-raw").value),
              drift_tolerance_raw: Number(document.getElementById("soil-calibration-drift-tolerance-raw").value),
              sample_count: Number(document.getElementById("soil-calibration-sample-count").value),
              sample_interval_ms: Number(document.getElementById("soil-calibration-sample-interval-ms").value),
            };
            const envCalibrationMode = document.getElementById("env-calibration-mode").value;
            const envCalibration = {
              mode: envCalibrationMode,
              request_id: envCalibrationMode === "normal" ? "" : String(Date.now()),
              target: document.getElementById("env-calibration-target").value,
              reference_value: Number(document.getElementById("env-calibration-reference-value").value),
              par_umol_m2_s: collectEnvMetricCalibration("env-cal-par"),
              soil_moisture_percent: collectEnvMetricCalibration("env-cal-moisture"),
              soil_temperature_c: collectEnvMetricCalibration("env-cal-temperature"),
              soil_ec_us_cm: collectEnvMetricCalibration("env-cal-ec"),
              soil_ph: collectEnvMetricCalibration("env-cal-ph"),
              soil_n_mg_kg: collectEnvMetricCalibration("env-cal-n"),
              soil_p_mg_kg: collectEnvMetricCalibration("env-cal-p"),
              soil_k_mg_kg: collectEnvMetricCalibration("env-cal-k"),
            };
            const envSensors = {
              par: {
                enabled: document.getElementById("env-par-enabled").checked,
                modbus_slave_id: Number(document.getElementById("env-par-slave").value),
                modbus_function: Number(document.getElementById("env-par-function").value),
                register: Number(document.getElementById("env-par-register").value),
              },
              soil: {
                enabled: document.getElementById("env-soil-enabled").checked,
                modbus_slave_id: Number(document.getElementById("env-soil-slave").value),
                modbus_function: Number(document.getElementById("env-soil-function").value),
                start_register: Number(document.getElementById("env-soil-start-register").value),
              },
              power_settle_ms: Number(document.getElementById("env-power-settle-ms").value),
            };
            const config = {
              ntp_server: document.getElementById("ntp-server").value.trim() || "pool.ntp.org",
              timezone_offset_sec: timezoneOffset,
              moisture_threshold: threshold,
              force_watering: document.getElementById("force-watering").checked,
              startup_watering_test: document.getElementById("startup-watering-test-enabled") ? {
                enabled: document.getElementById("startup-watering-test-enabled").checked,
                duration_sec: Number(document.getElementById("startup-watering-test-duration").value),
                channel_mask: Number(document.getElementById("startup-watering-test-channel").value),
              } : (initialRuntimeConfig.startup_watering_test || { enabled: false, duration_sec: 5, channel_mask: 1 }),
              debug_log_on_wake: document.getElementById("debug-log-on-wake").checked,
              ota_check_interval_sec: otaCheckInterval,
              watering_pattern: wateringPattern,
              soil_calibration: soilCalibration,
              env_sensors: envSensors,
              env_calibration: envCalibration,
              mosfet_switches: mosfetSwitches,
              schedules,
            };
            document.querySelectorAll("[data-definition-path]").forEach((input) => {
              const value = input.dataset.definitionType === "boolean" ? input.checked : Number(input.value);
              setNestedValue(config, input.dataset.definitionPath, value);
            });
            Object.keys(initialRuntimeConfig || {}).forEach((key) => {
              if (!(key in config)) config[key] = structuredClone(initialRuntimeConfig[key]);
            });
            return applyRuntimeConfigFixedValues(config);
          }

          function getNestedValue(value, path) {
            return String(path || "").split(".").reduce((current, key) => current && current[key], value);
          }

          function setNestedValue(value, path, nextValue) {
            const keys = String(path || "").split(".").filter(Boolean);
            let current = value;
            keys.slice(0, -1).forEach((key) => {
              if (!current[key] || typeof current[key] !== "object") current[key] = {};
              current = current[key];
            });
            if (keys.length) current[keys[keys.length - 1]] = nextValue;
          }

          function applyRuntimeConfigFixedValues(config) {
            const result = structuredClone(config || {});
            Object.entries(runtimeConfigFixedValues).forEach(([path, value]) => setNestedValue(result, path, structuredClone(value)));
            return result;
          }

          function projectRuntimeConfig(config) {
            const effectiveConfig = applyRuntimeConfigFixedValues(config);
            if (!deviceRuntimeSendKeys.length) return effectiveConfig;
            return Object.fromEntries(deviceRuntimeSendKeys.filter((key) => key in effectiveConfig).map((key) => [key, structuredClone(effectiveConfig[key])]));
          }

          function irrigationOperationDuration(config, schedule) {
            if (isFertigationDevice) {
              const fgt = config?.fgt || {};
              const timedOutputs = fgt.timed_outputs || {};
              if (timedOutputs.enabled === true) {
                const durationSec = ["water_inlet", "nutrient_a", "nutrient_b", "mixer", "irrigation"].reduce((total, outputId) => {
                  const output = timedOutputs[outputId] || {};
                  const onSec = Math.max(0, Number(output.on_sec) || 0);
                  const offSec = Math.max(0, Number(output.off_sec) || 0);
                  const repeatCount = Math.max(0, Number(output.repeat_count) || 0);
                  return total + onSec * repeatCount + offSec * Math.max(0, repeatCount - 1);
                }, 0);
                return { durationSec, source: "fgt_timed_outputs", label: "ポンプ全工程" };
              }
              return {
                durationSec: Math.max(0, Number((fgt.limits || {}).max_batch_sec) || 1800),
                source: "fgt_max_batch",
                label: "最大工程時間",
              };
            }
            const pattern = config?.watering_pattern || {};
            if (pattern.enabled === true) {
              const onSec = Math.max(0, Number(pattern.on_sec) || 0);
              const offSec = Math.max(0, Number(pattern.off_sec) || 0);
              const repeatCount = Math.max(0, Number(pattern.repeat_count) || 0);
              return {
                durationSec: onSec * repeatCount + offSec * Math.max(0, repeatCount - 1),
                source: "watering_pattern",
                label: "分割灌水の開始から終了まで",
              };
            }
            return {
              durationSec: Math.max(0, Number(schedule?.duration_sec) || 0),
              source: "schedule",
              label: "灌水時間",
            };
          }

          function parseScheduleDate(value) {
            const match = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(String(value || ""));
            if (!match) return null;
            const timestamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
            const parsed = new Date(timestamp);
            if (
              parsed.getUTCFullYear() !== Number(match[1])
              || parsed.getUTCMonth() !== Number(match[2]) - 1
              || parsed.getUTCDate() !== Number(match[3])
            ) return null;
            return timestamp;
          }

          function scheduleOccursOnDay(schedule, dayTimestamp) {
            const frequency = schedule?.frequency || {};
            const mode = frequency.mode || "daily";
            if (mode === "daily") return true;
            if (mode === "weekdays") return (frequency.weekdays || []).map(Number).includes(new Date(dayTimestamp).getUTCDay());
            if (mode === "interval") {
              const startTimestamp = parseScheduleDate(frequency.start_date);
              const intervalDays = Number(frequency.interval_days);
              if (startTimestamp === null || !Number.isInteger(intervalDays) || intervalDays <= 0 || dayTimestamp < startTimestamp) return false;
              return Math.round((dayTimestamp - startTimestamp) / 86400000) % intervalDays === 0;
            }
            return false;
          }

          function scheduleClock(schedule) {
            return `${String(Number(schedule?.hour) || 0).padStart(2, "0")}:${String(Number(schedule?.minute) || 0).padStart(2, "0")}`;
          }

          function clockWithDayOffset(clock, dayOffset) {
            if (dayOffset === 0) return clock;
            if (dayOffset === 1) return `翌日 ${clock}`;
            return `${dayOffset}日後 ${clock}`;
          }

          function formatScheduleSpacingDuration(seconds) {
            seconds = Math.max(0, Math.round(Number(seconds) || 0));
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const remainingSeconds = seconds % 60;
            return [
              hours ? `${hours}時間` : "",
              minutes ? `${minutes}分` : "",
              remainingSeconds ? `${remainingSeconds}秒` : "",
            ].filter(Boolean).join("") || "0秒";
          }

          function irrigationScheduleSpacingConflicts(config) {
            if (!isIrrigationScheduleDevice || !Array.isArray(config?.schedules)) return [];
            const schedules = config.schedules;
            const enabledSchedules = schedules.map((schedule, index) => ({ schedule, index })).filter(({ schedule }) => schedule && schedule.enabled !== false);
            if (!enabledSchedules.length) return [];

            const intervalStarts = enabledSchedules
              .filter(({ schedule }) => (schedule.frequency || {}).mode === "interval")
              .map(({ schedule }) => parseScheduleDate((schedule.frequency || {}).start_date))
              .filter((timestamp) => timestamp !== null);
            const defaultCycleStart = Date.UTC(2024, 0, 7);
            const cycleStart = intervalStarts.length ? Math.max(...intervalStarts) : defaultCycleStart;
            const cycleDays = 1000;
            const occurrences = [];
            for (let dayOffset = 0; dayOffset <= cycleDays + 32; dayOffset += 1) {
              const dayTimestamp = cycleStart + dayOffset * 86400000;
              enabledSchedules.forEach(({ schedule, index }) => {
                if (!scheduleOccursOnDay(schedule, dayTimestamp)) return;
                occurrences.push({
                  scheduleIndex: index,
                  timestampSec: dayOffset * 86400 + (Number(schedule.hour) || 0) * 3600 + (Number(schedule.minute) || 0) * 60,
                  dayOffset,
                });
              });
            }
            occurrences.sort((left, right) => left.timestampSec - right.timestampSec || left.scheduleIndex - right.scheduleIndex);

            const conflictsByPair = new Map();
            for (let index = 0; index < occurrences.length - 1; index += 1) {
              const current = occurrences[index];
              const following = occurrences[index + 1];
              if (current.timestampSec >= cycleDays * 86400) break;
              const duration = irrigationOperationDuration(config, schedules[current.scheduleIndex]);
              const requiredGapSec = duration.durationSec + scheduleSafetyBufferSec;
              const gapSec = following.timestampSec - current.timestampSec;
              if (!Number.isFinite(requiredGapSec) || gapSec >= requiredGapSec) continue;
              const suggestedTimestampSec = Math.ceil((current.timestampSec + requiredGapSec) / 60) * 60;
              const suggestedClockSec = ((suggestedTimestampSec % 86400) + 86400) % 86400;
              const suggestedDayOffset = Math.floor(suggestedTimestampSec / 86400) - Math.floor(current.timestampSec / 86400);
              const conflict = {
                sourceIndex: current.scheduleIndex,
                nextIndex: following.scheduleIndex,
                sourceTime: scheduleClock(schedules[current.scheduleIndex]),
                nextTime: scheduleClock(schedules[following.scheduleIndex]),
                nextDayOffset: following.dayOffset - current.dayOffset,
                gapSec,
                operationDurationSec: duration.durationSec,
                durationSource: duration.source,
                durationLabel: duration.label,
                requiredGapSec,
                shortageSec: requiredGapSec - gapSec,
                suggestedTime: `${String(Math.floor(suggestedClockSec / 3600)).padStart(2, "0")}:${String(Math.floor((suggestedClockSec % 3600) / 60)).padStart(2, "0")}`,
                suggestedDayOffset,
                maximumOperationDurationSec: Math.max(0, gapSec - scheduleSafetyBufferSec),
              };
              const pairKey = `${conflict.sourceIndex}:${conflict.nextIndex}`;
              const previous = conflictsByPair.get(pairKey);
              if (!previous || conflict.gapSec < previous.gapSec) conflictsByPair.set(pairKey, conflict);
            }
            return Array.from(conflictsByPair.values()).sort((left, right) => left.sourceIndex - right.sourceIndex || left.nextIndex - right.nextIndex);
          }

          function scheduleSpacingInstruction(conflict) {
            const nextLabel = clockWithDayOffset(conflict.nextTime, conflict.nextDayOffset);
            const suggestedLabel = clockWithDayOffset(conflict.suggestedTime, conflict.suggestedDayOffset);
            const shortage = formatScheduleSpacingDuration(conflict.shortageSec);
            let correction = `次の予約を ${suggestedLabel} 以降に変更してください。`;
            if (conflict.maximumOperationDurationSec > 0) {
              const settingName = conflict.durationSource === "schedule" ? "直前の灌水時間" : conflict.durationSource === "watering_pattern" ? "分割灌水のON・OFF時間や回数" : conflict.durationSource === "fgt_max_batch" ? "最大工程時間" : "各ポンプのON・OFF時間や回数";
              correction = `次の予約を ${suggestedLabel} 以降にするか、${settingName}を ${formatScheduleSpacingDuration(conflict.maximumOperationDurationSec)} 以下にしてください。`;
            }
            return `${conflict.sourceTime} の${conflict.durationLabel}は ${formatScheduleSpacingDuration(conflict.operationDurationSec)}。次の ${nextLabel} までは ${formatScheduleSpacingDuration(conflict.gapSec)} しかなく、あと ${shortage} 足りません。${correction}`;
          }

          function refreshScheduleSpacingValidation(config) {
            const panel = document.getElementById("schedule-spacing-warning");
            if (!panel) return [];
            const rows = Array.from(document.querySelectorAll("#schedule-editor .schedule-row"));
            rows.forEach((row) => {
              row.classList.remove("has-spacing-conflict", "is-spacing-target");
              const input = row.querySelector("[data-schedule-time]");
              input?.removeAttribute("aria-invalid");
              input?.removeAttribute("aria-describedby");
              const message = row.querySelector("[data-schedule-spacing-message]");
              if (message) {
                message.hidden = true;
                message.textContent = "";
                message.removeAttribute("id");
              }
            });

            const conflicts = irrigationScheduleSpacingConflicts(config);
            panel.hidden = conflicts.length === 0;
            const summary = document.getElementById("schedule-spacing-warning-summary");
            const list = document.getElementById("schedule-spacing-warning-list");
            if (!conflicts.length) {
              if (summary) summary.textContent = "";
              if (list) list.replaceChildren();
              return conflicts;
            }

            if (summary) summary.textContent = `${conflicts.length}組の予約で、「運転時間＋5分」の間隔を確保できません。このままでは保存・機器送信できません。`;
            if (list) {
              list.replaceChildren(...conflicts.map((conflict) => {
                const item = document.createElement("li");
                item.textContent = scheduleSpacingInstruction(conflict);
                return item;
              }));
            }
            const targetMessages = new Map();
            conflicts.forEach((conflict) => {
              rows[conflict.sourceIndex]?.classList.add("has-spacing-conflict");
              rows[conflict.nextIndex]?.classList.add("has-spacing-conflict", "is-spacing-target");
              const messages = targetMessages.get(conflict.nextIndex) || [];
              messages.push(`開始時刻を ${clockWithDayOffset(conflict.suggestedTime, conflict.suggestedDayOffset)} 以降へ変更してください（あと ${formatScheduleSpacingDuration(conflict.shortageSec)} 必要です）。`);
              targetMessages.set(conflict.nextIndex, messages);
            });
            targetMessages.forEach((messages, rowIndex) => {
              const row = rows[rowIndex];
              const message = row?.querySelector("[data-schedule-spacing-message]");
              const input = row?.querySelector("[data-schedule-time]");
              if (!message || !input) return;
              message.id = `schedule-spacing-row-${rowIndex}`;
              message.textContent = messages.join(" ");
              message.hidden = false;
              input.setAttribute("aria-invalid", "true");
              input.setAttribute("aria-describedby", message.id);
            });
            return conflicts;
          }

          function guideToScheduleSpacingConflict(config) {
            const conflicts = refreshScheduleSpacingValidation(config);
            if (!conflicts.length) return false;
            activateDetailTab("tab-config");
            const firstConflict = conflicts[0];
            const rows = Array.from(document.querySelectorAll("#schedule-editor .schedule-row"));
            const targetInput = rows[firstConflict.nextIndex]?.querySelector("[data-schedule-time]");
            const panel = document.getElementById("schedule-spacing-warning");
            panel?.scrollIntoView({ behavior: "smooth", block: "center" });
            window.setTimeout(() => (targetInput || panel)?.focus(), 250);
            showResult("予約間隔が不足しているため保存できません。橙色の予約時刻または運転時間を直してください。", false);
            return true;
          }

          function scheduledOperationWarnings(config) {
            const spec = scheduledOperationDefinition;
            if (!spec) return [];
            const effectiveConfig = applyRuntimeConfigFixedValues(config);
            const schedules = getNestedValue(effectiveConfig, spec.schedules_path || "schedules");
            const enabledSchedules = Array.isArray(schedules) ? schedules.filter((schedule) => schedule && schedule.enabled !== false) : [];
            if (!enabledSchedules.length) return [];
            const warnings = [];
            if (getNestedValue(effectiveConfig, spec.enabled_path) !== true) {
              warnings.push(spec.disabled_warning || "予約運転が停止中のため、予約は実行されません。");
            }
            const programs = getNestedValue(effectiveConfig, spec.program_outputs_path) || {};
            const programRequirementsApply = spec.program_required_when_path ? getNestedValue(effectiveConfig, spec.program_required_when_path) === true : true;
            const missingOutput = programRequirementsApply && (spec.required_output_ids || []).some((outputId) => {
              const output = programs[outputId] || {};
              return Number(output.on_sec || 0) <= 0 || Number(output.repeat_count || 0) <= 0;
            });
            if (missingOutput) warnings.push(spec.missing_output_warning || "必要な出力時間が設定されていないため、予約は実行されません。");
            return warnings;
          }

          function refreshScheduledOperationWarning(config) {
            const warning = document.getElementById("scheduled-operation-inline-warning");
            if (!warning) return;
            const warnings = scheduledOperationWarnings(config);
            warning.textContent = warnings.join(" ");
            warning.hidden = warnings.length === 0;
          }

          function confirmScheduledOperationWarnings(config, push) {
            const warnings = scheduledOperationWarnings(config);
            const dialog = document.getElementById("scheduled-operation-warning-dialog");
            if (!warnings.length || !dialog) return Promise.resolve(applyRuntimeConfigFixedValues(config));
            const list = document.getElementById("scheduled-operation-warning-list");
            if (list) {
              list.replaceChildren(...warnings.map((warning) => {
                const item = document.createElement("li");
                item.textContent = warning;
                return item;
              }));
            }
            const enableCheckbox = document.getElementById("scheduled-operation-enable-before-save");
            if (enableCheckbox) enableCheckbox.checked = getNestedValue(config, scheduledOperationDefinition.enabled_path) === true;
            const continueButton = document.getElementById("scheduled-operation-warning-continue");
            if (continueButton) continueButton.textContent = push ? "警告を確認して機器へ送る" : "警告を確認して下書きを保存";
            openDialog(dialog);
            return new Promise((resolve) => {
              let settled = false;
              const finish = (nextConfig) => {
                if (settled) return;
                settled = true;
                closeDialog(dialog);
                resolve(nextConfig);
              };
              document.querySelectorAll("[data-cancel-scheduled-operation-warning]").forEach((button) => {
                button.onclick = () => finish(null);
              });
              dialog.oncancel = (event) => {
                event.preventDefault();
                finish(null);
              };
              if (continueButton) {
                continueButton.onclick = () => {
                  const nextConfig = structuredClone(config);
                  if (enableCheckbox?.checked) setNestedValue(nextConfig, scheduledOperationDefinition.enabled_path, true);
                  finish(applyRuntimeConfigFixedValues(nextConfig));
                };
              }
            });
          }

          function setEnvMetricCalibration(metric, prefix, envCalibration) {
            const metricConfig = envCalibration[metric] || {};
            const calibrated = document.getElementById(prefix + "-calibrated");
            if (calibrated) calibrated.checked = Boolean(metricConfig.calibrated);
            const scale = document.getElementById(prefix + "-scale");
            if (scale) scale.value = String(typeof metricConfig.scale === "number" ? metricConfig.scale : 1);
            const offset = document.getElementById(prefix + "-offset");
            if (offset) offset.value = String(typeof metricConfig.offset === "number" ? metricConfig.offset : 0);
          }

          function collectEnvMetricCalibration(prefix) {
            return {
              calibrated: document.getElementById(prefix + "-calibrated").checked,
              scale: Number(document.getElementById(prefix + "-scale").value),
              offset: Number(document.getElementById(prefix + "-offset").value),
            };
          }

          function refreshRuntimeConfigPreview() {
            let config;
            try {
              config = collectRuntimeConfigFromForm();
            } catch (error) {
              return;
            }
            const textarea = document.getElementById("runtime-config-json");
            if (textarea) textarea.value = JSON.stringify(projectRuntimeConfig(config), null, 2);
            const thresholdDisplay = document.getElementById("threshold-display");
            if (thresholdDisplay) thresholdDisplay.textContent = config.moisture_threshold + "%";
            const forceDisplay = document.getElementById("force-display");
            if (forceDisplay) forceDisplay.textContent = config.force_watering ? "はい" : "いいえ";
            const scheduleCountDisplay = document.getElementById("schedule-count-display");
            if (scheduleCountDisplay) scheduleCountDisplay.textContent = config.schedules.length + "件";
            const debugLogDisplay = document.getElementById("debug-log-display");
            if (debugLogDisplay) debugLogDisplay.textContent = config.debug_log_on_wake ? "はい" : "いいえ";
            const otaIntervalDisplay = document.getElementById("ota-interval-display");
            if (otaIntervalDisplay) otaIntervalDisplay.textContent = formatDurationSeconds(config.ota_check_interval_sec);
            refreshScheduledOperationWarning(config);
            refreshScheduleSpacingValidation(config);
          }

          async function saveRuntimeConfig(push, source) {
            let config;
            if (source === "json") {
              const textarea = document.getElementById("runtime-config-json");
              try {
                config = applyRuntimeConfigFixedValues({ ...structuredClone(initialRuntimeConfig), ...JSON.parse(textarea.value) });
              } catch (error) {
                showResult("水やり設定 JSON が正しくありません", false);
                return;
              }
            } else {
              try {
                config = collectRuntimeConfigFromForm();
              } catch (error) {
                showResult(error.message, false);
                return;
              }
            }
            if (source === "json") renderRuntimeConfigForm(config);
            if (guideToScheduleSpacingConflict(config)) return;
            config = await confirmScheduledOperationWarnings(config, push);
            if (!config) return;
            if (guideToScheduleSpacingConflict(config)) return;
            renderRuntimeConfigForm(config);
            const textarea = document.getElementById("runtime-config-json");
            if (textarea) textarea.value = JSON.stringify(projectRuntimeConfig(config), null, 2);
            try {
              await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/runtime-config?push=" + String(Boolean(push)), {
                method: "PUT",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(config),
              }, push ? "水やり設定を保存して device に送信しています..." : "水やり設定を保存しています...");
              showResult(push ? "水やり設定を保存して device に送信しました" : "水やり設定を保存しました", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          }

          const runtimeConfigForm = document.getElementById("runtime-config-form");
          if (runtimeConfigForm) {
            bindEnvSensorWorkbench();
            bindTimedOutputControls();
            renderRuntimeConfigForm(initialRuntimeConfig);
            runtimeConfigForm.dispatchEvent(new CustomEvent("stateful-form-reset"));
            runtimeConfigForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              await saveRuntimeConfig(false);
            });
            runtimeConfigForm.querySelectorAll("input, select").forEach((input) => input.addEventListener("input", refreshRuntimeConfigPreview));
          }
          document.querySelectorAll('input[name="irrigation-mode"]').forEach((input) => {
            input.addEventListener("input", () => {
              updateIrrigationModeUi(true);
              refreshRuntimeConfigPreview();
            });
          });
          ["watering-pattern-on-sec", "watering-pattern-off-sec", "watering-pattern-repeat-count"].forEach((id) => {
            document.getElementById(id)?.addEventListener("input", () => updateIrrigationModeUi());
          });
          const thresholdRange = document.getElementById("moisture-threshold");
          const thresholdNumber = document.getElementById("moisture-threshold-number");
          if (thresholdRange && thresholdNumber) {
            thresholdRange.addEventListener("input", () => {
              thresholdNumber.value = thresholdRange.value;
              refreshRuntimeConfigPreview();
            });
            thresholdNumber.addEventListener("input", () => {
              thresholdRange.value = thresholdNumber.value;
              refreshRuntimeConfigPreview();
            });
          }
          const addScheduleButton = document.getElementById("add-schedule");
          if (addScheduleButton) {
            addScheduleButton.addEventListener("click", () => {
              const editor = document.getElementById("schedule-editor");
              if (!editor) return;
              if (editor.querySelectorAll(".schedule-row").length >= 8) {
                showResult("灌水予約は最大 8 件です", false);
                return;
              }
              editor.appendChild(createScheduleRow({ hour: 6, minute: 30, duration_sec: 1, channel_mask: 1, frequency: { mode: "daily" } }));
              refreshRuntimeConfigPreview();
              runtimeConfigForm?.dispatchEvent(new Event("change", { bubbles: true }));
            });
          }
          const applyRuntimeJsonButton = document.getElementById("apply-runtime-json");
          if (applyRuntimeJsonButton) {
            applyRuntimeJsonButton.addEventListener("click", () => {
              try {
                renderRuntimeConfigForm(JSON.parse(document.getElementById("runtime-config-json").value));
                runtimeConfigForm?.dispatchEvent(new Event("change", { bubbles: true }));
                showResult("JSON をフォームに反映しました", true);
              } catch (error) {
                showResult("水やり設定 JSON が正しくありません", false);
              }
            });
          }
          const saveRuntimeJsonButton = document.getElementById("save-runtime-json");
          if (saveRuntimeJsonButton) saveRuntimeJsonButton.addEventListener("click", () => saveRuntimeConfig(false, "json"));
          const savePushRuntimeJsonButton = document.getElementById("save-push-runtime-json");
          if (savePushRuntimeJsonButton) savePushRuntimeJsonButton.addEventListener("click", () => saveRuntimeConfig(true, "json"));
          const savePushConfigButton = document.getElementById("save-push-runtime-config");
          if (savePushConfigButton) savePushConfigButton.addEventListener("click", () => saveRuntimeConfig(true));
          const pushConfigButton = document.getElementById("push-runtime-config");
          if (pushConfigButton) {
            pushConfigButton.addEventListener("click", async () => {
              try {
                await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/runtime-config/push", { method: "POST" }, "保存済み設定を device に送信しています...");
                showResult("保存済み設定を device に送信しました", true);
              } catch (error) {
                showResult(error.message, false);
              }
            });
          }

          const firmwareTargetForm = document.getElementById("firmware-target-form");
          if (firmwareTargetForm) {
            firmwareTargetForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              await setFirmwareTarget(document.getElementById("target-firmware-version").value || null);
            });
          }
          const clearTargetButton = document.getElementById("clear-firmware-target");
          if (clearTargetButton) clearTargetButton.addEventListener("click", () => setFirmwareTarget(null));

          async function setFirmwareTarget(version) {
            try {
              await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/firmware-target", {
                method: "PUT",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ target_firmware_version: version }),
              }, "OTA 更新対象を更新しています...");
              showResult("更新対象バージョンを更新しました", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          }

          const firmwareUploadForm = document.getElementById("firmware-upload-form");
          if (firmwareUploadForm) {
            let inspectedFirmwareManifest = null;
            let inspectedFirmwareFileKey = "";
            const firmwareFileInput = document.getElementById("firmware-file");
            const firmwareManifestSummary = document.getElementById("firmware-manifest-summary");
            const inspectFirmwareManifestButton = document.getElementById("inspect-firmware-manifest");
            const firmwareDropzone = document.getElementById("firmware-dropzone");
            const firmwareArtifactDetails = document.getElementById("firmware-artifact-details");
            const firmwareArtifactRows = document.getElementById("firmware-artifact-rows");
            const firmwareArtifactCount = document.getElementById("firmware-artifact-count");
            const firmwareTargetSelect = document.getElementById("target-firmware-version");

            function firmwareFileKey(file) {
              return file ? [file.name, file.size, file.lastModified].join(":") : "";
            }

            function setFirmwareManifestSummary(message, ok) {
              if (!firmwareManifestSummary) return;
              firmwareManifestSummary.textContent = message;
              firmwareManifestSummary.classList.toggle("ok", Boolean(ok));
              firmwareManifestSummary.classList.toggle("error", ok === false);
            }

            function setFirmwareFileValidity(message = "") {
              if (!firmwareFileInput) return;
              firmwareFileInput.setCustomValidity(message);
              firmwareFileInput.dispatchEvent(new Event("input", { bubbles: true }));
            }

            function firmwareManifestLabel(metadata) {
              const details = ["project", "target", "framework"]
                .filter((key) => metadata && metadata[key])
                .map((key) => key + "=" + metadata[key]);
              return details.join(" / ") || (metadata ? "取得済み" : "未取得");
            }

            function firmwareArtifactOptionLabel(artifact) {
              let label = artifact.version || "version未設定";
              if (artifact.build_id) label += " / build " + artifact.build_id;
              if (artifact.rollout_state) label += " / " + artifact.rollout_state;
              return label;
            }

            function formatFirmwareArtifactDate(value) {
              const parsed = value ? new Date(value) : null;
              return parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString("ja-JP") : (value || "-");
            }

            function addFirmwareArtifactCell(row, value) {
              const cell = document.createElement("td");
              cell.textContent = value === null || value === undefined || value === "" ? "-" : String(value);
              row.appendChild(cell);
              return cell;
            }

            function showRegisteredFirmwareArtifact(artifact) {
              if (!firmwareArtifactRows || !artifact) return;
              const key = (artifact.device_kind || "-") + ":" + (artifact.version || "-");
              const existing = Array.from(firmwareArtifactRows.querySelectorAll("tr[data-firmware-artifact-key]"))
                .find((row) => row.dataset.firmwareArtifactKey === key);
              const row = document.createElement("tr");
              row.dataset.firmwareArtifactKey = key;
              addFirmwareArtifactCell(row, key);
              addFirmwareArtifactCell(row, artifact.version);
              addFirmwareArtifactCell(row, artifact.device_kind);
              addFirmwareArtifactCell(row, artifact.build_id || "未取得");
              addFirmwareArtifactCell(row, firmwareManifestLabel(artifact.firmware_metadata));
              addFirmwareArtifactCell(row, artifact.rollout_state);
              addFirmwareArtifactCell(row, artifact.size);
              addFirmwareArtifactCell(row, artifact.sha256);
              const linkCell = document.createElement("td");
              const link = document.createElement("a");
              link.href = artifact.url;
              link.target = "_blank";
              link.rel = "noopener";
              link.setAttribute("aria-label", "更新ファイルを新しいタブで開く");
              link.textContent = "配信ファイルを開く ↗";
              linkCell.appendChild(link);
              row.appendChild(linkCell);
              addFirmwareArtifactCell(row, formatFirmwareArtifactDate(artifact.updated_at));
              firmwareArtifactRows.querySelector("[data-firmware-artifact-empty]")?.remove();
              if (existing) existing.replaceWith(row);
              else firmwareArtifactRows.prepend(row);
              if (firmwareArtifactCount) {
                firmwareArtifactCount.textContent = String(firmwareArtifactRows.querySelectorAll("tr[data-firmware-artifact-key]").length);
              }
              if (firmwareArtifactDetails) firmwareArtifactDetails.open = true;

              const currentDeviceKind = firmwareUploadForm.dataset.currentDeviceKind || "";
              if (firmwareTargetSelect && artifact.device_kind === currentDeviceKind && artifact.version) {
                let option = Array.from(firmwareTargetSelect.options).find((candidate) => candidate.value === artifact.version);
                if (!option) {
                  option = document.createElement("option");
                  option.value = artifact.version;
                  firmwareTargetSelect.appendChild(option);
                }
                option.textContent = firmwareArtifactOptionLabel(artifact);
              }
            }

            async function inspectSelectedFirmware() {
              const file = firmwareFileInput.files[0];
              if (!file) {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                setFirmwareFileValidity("");
                setFirmwareManifestSummary(".inasfw ファイルを選択してください", false);
                return null;
              }
              if (!file.name.toLocaleLowerCase().endsWith(".inasfw")) {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                const message = "選択できる更新ファイルは .inasfw 形式です";
                setFirmwareFileValidity(message);
                setFirmwareManifestSummary(message, false);
                return null;
              }
              const currentKey = firmwareFileKey(file);
              if (inspectedFirmwareManifest && inspectedFirmwareFileKey === currentKey) {
                setFirmwareFileValidity("");
                return inspectedFirmwareManifest;
              }
              const formData = new FormData();
              formData.append("firmware", file);
              setFirmwareFileValidity(".inasfw ファイルを読み取っています");
              setFirmwareManifestSummary(".inasfw ファイルを読み取っています...", null);
              try {
                const manifest = await requestJson(
                  "/local/api/firmware-artifacts/inspect",
                  { method: "POST", body: formData },
                  "F/Wファイルの情報を読み取っています...",
                );
                if (manifest.upload_format !== "inasfw") throw new Error("選択できる更新ファイルは .inasfw 形式です");
                inspectedFirmwareManifest = manifest;
                inspectedFirmwareFileKey = currentKey;
                document.getElementById("firmware-device-kind").value = manifest.device_kind || "";
                document.getElementById("firmware-version").value = manifest.version || "";
                document.getElementById("firmware-build-id").value = manifest.build_id || "";
                document.getElementById("firmware-device-kind-display").textContent = manifest.device_kind || "-";
                document.getElementById("firmware-version-display").textContent = manifest.version || "-";
                document.getElementById("firmware-build-id-display").textContent = manifest.build_id || "-";
                setFirmwareManifestSummary(
                  "INAS更新ファイルを読み取り済み: " +
                    "device_kind=" + (manifest.device_kind || "-") +
                    " / version=" + (manifest.version || "-") +
                    " / build_id=" + (manifest.build_id || "-") +
                    " / target=" + (manifest.target || "-") +
                    " / project=" + (manifest.project || "-"),
                  true,
                );
                setFirmwareFileValidity("");
                return manifest;
              } catch (error) {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                document.getElementById("firmware-version").value = "";
                document.getElementById("firmware-build-id").value = "";
                document.getElementById("firmware-device-kind-display").textContent = "-";
                document.getElementById("firmware-version-display").textContent = "-";
                document.getElementById("firmware-build-id-display").textContent = "-";
                setFirmwareManifestSummary(error.message, false);
                setFirmwareFileValidity(error.message);
                throw error;
              }
            }

            if (firmwareFileInput) {
              firmwareFileInput.addEventListener("click", () => {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                firmwareFileInput.value = "";
                setFirmwareFileValidity("");
              });
              firmwareFileInput.addEventListener("change", () => {
                inspectSelectedFirmware().catch((error) => showResult(error.message, false));
              });
            }
            if (firmwareDropzone && firmwareFileInput) {
              ["dragenter", "dragover"].forEach((eventName) => firmwareDropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                firmwareDropzone.classList.add("dragover");
              }));
              ["dragleave", "drop"].forEach((eventName) => firmwareDropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                firmwareDropzone.classList.remove("dragover");
              }));
              firmwareDropzone.addEventListener("drop", (event) => {
                const file = event.dataTransfer?.files?.[0];
                if (!file) return;
                const transfer = new DataTransfer();
                transfer.items.add(file);
                firmwareFileInput.files = transfer.files;
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                firmwareFileInput.dispatchEvent(new Event("change", { bubbles: true }));
              });
            }
            if (inspectFirmwareManifestButton) {
              inspectFirmwareManifestButton.addEventListener("click", () => {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                inspectSelectedFirmware().catch((error) => showResult(error.message, false));
              });
            }

            firmwareUploadForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              const file = document.getElementById("firmware-file").files[0];
              if (!file) {
                showResult(".inasfw ファイルを選択してください", false);
                return;
              }
              let manifest;
              try {
                manifest = await inspectSelectedFirmware();
              } catch (error) {
                showResult(error.message, false);
                return;
              }
              const deviceKind = (manifest && manifest.device_kind ? manifest.device_kind : "").trim();
              const version = (manifest && manifest.version ? manifest.version : "").trim();
              if (!deviceKind || !version) {
                showResult("F/Wファイルからデバイス種別とバージョンを読み取れません", false);
                return;
              }
              const formData = new FormData();
              formData.append("firmware", file);
              const buildId = manifest.build_id || "";
              if (buildId) formData.append("build_id", buildId);
              formData.append("rollout_state", document.getElementById("firmware-rollout-state").value);
              formData.append("force", document.getElementById("firmware-force").checked ? "true" : "false");
              formData.append("allow_downgrade", document.getElementById("firmware-allow-downgrade").checked ? "true" : "false");
              firmwareUploadForm.dispatchEvent(new CustomEvent("stateful-form-busy", { detail: true }));
              try {
                const artifact = await requestJson(
                  "/local/api/firmware-artifacts/" + encodeURIComponent(deviceKind) + "/" + encodeURIComponent(version) + "/upload",
                  { method: "POST", body: formData },
                  "F/Wファイルをアップロードしています...",
                );
                showRegisteredFirmwareArtifact(artifact);
                firmwareUploadForm.reset();
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                document.getElementById("firmware-device-kind-display").textContent = "-";
                document.getElementById("firmware-version-display").textContent = "-";
                document.getElementById("firmware-build-id-display").textContent = "-";
                setFirmwareFileValidity("");
                const successMessage = ".inasfw を登録しました。一覧と更新候補へ反映済みです";
                setFirmwareManifestSummary(deviceKind + " / " + version + " を登録しました", true);
                firmwareUploadForm.dispatchEvent(new CustomEvent("stateful-form-reset", { detail: { message: successMessage, kind: "ok" } }));
                showResult(successMessage, true);
                firmwareArtifactDetails?.scrollIntoView({ behavior: "smooth", block: "nearest" });
              } catch (error) {
                firmwareUploadForm.dispatchEvent(new CustomEvent("stateful-form-busy", { detail: false }));
                showResult(error.message, false);
              }
            });
          }
        </script>
      </body>
    </html>
    """

    return render_template_string(
        template,
        devices=devices,
        selected_device_id=selected_device_id,
        selected_device=selected_device,
        selected_statuses=selected_statuses,
        selected_ota_statuses=selected_ota_statuses,
        firmware_artifacts=_format_firmware_artifacts_for_ui(firmware_artifacts),
        firmware_target_options=_build_firmware_target_options(firmware_artifacts, selected_device),
        connection_events=connection_events,
        recent_events=recent_events,
        admin_view=admin_view,
        format_json=_format_json,
        format_datetime=_format_datetime,
        render_events=_render_event_table,
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
            try:
                datetime.strptime(post_schedule_start, "%H:%M")
            except ValueError:
                return "post_schedule_start must use HH:MM", 400
            camera_id = request.form.get("camera_id", "").strip()
            camera_ids = {item["id"] for item in _instagram_camera_options(current_instagram.get("camera_id", ""))}
            if camera_id and camera_id not in camera_ids:
                return "camera_id must identify a registered camera", 400
            setting().set(
                "instagram",
                {
                    "posting_paused": request.form.get("posting_paused") == "on",
                    "post_schedule_start": post_schedule_start,
                    "camera_id": camera_id,
                    "plant_position_prompt": request.form.get("plant_position_prompt", "").strip(),
                },
            )
            reload_instagram_post_task_settings()
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
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _post_watering_sensor_trend(sensor_device_id: str, *, now: datetime | None = None):
    range_end = now or datetime.now(UTC)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=UTC)
    range_end = range_end.astimezone(UTC)
    range_start = range_end - timedelta(days=3)
    try:
        measurements = sensor_measurement_repository().between_for_devices(
            [sensor_device_id],
            range_start.isoformat(),
            range_end.isoformat(),
            limit=5000,
        )
    except Exception:  # noqa: BLE001
        app.logger.exception("Unable to load post-watering moisture trend for sensor_device_id=%s", sensor_device_id)
        return {
            "sensor_device_id": sensor_device_id,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "points": [],
            "latest": None,
            "minimum": None,
            "maximum": None,
            "error": "直近3日分の測定値を読み込めませんでした。時間をおいて再読み込みしてください。",
        }

    points = []
    for measurement in measurements:
        if measurement.get("metric") != "soil_moisture_percent":
            continue
        measured_at = _parse_datetime(measurement.get("measured_at"))
        value = measurement.get("value")
        if measured_at is None or isinstance(value, bool) or not isinstance(value, int | float):
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
    response = jsonify(_post_watering_sensor_trend(sensor_device_id))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/settings/post-watering-moisture", methods=["GET", "POST"])
def post_watering_moisture_settings_page():
    user = current_user_from_request(request)
    if user.role != "admin":
        return render_template("settings_forbidden.html", user=user), 403

    records = device_config_service().get_all_records()
    watering_devices = post_watering_device_options(records)
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
            requested_watering_device_id = request.form.get("watering_device_id", "").strip()
            try:
                service.delete_rule(requested_watering_device_id)
            except PostWateringMoistureValidationError as exc:
                error_message = str(exc)
                status_code = 400
            else:
                if field_id:
                    return redirect(return_url)
                return redirect("/settings/post-watering-moisture?deleted=1")
        else:
            submitted = {
                "watering_device_id": request.form.get("watering_device_id", "").strip(),
                "sensor_device_id": request.form.get("sensor_device_id", "").strip(),
                "minimum_percent": request.form.get("minimum_percent", ""),
                "enabled": request.form.get("enabled") == "on",
            }
            try:
                saved_rule = service.save_rule(submitted, records)
            except PostWateringMoistureValidationError as exc:
                error_message = str(exc)
                status_code = 400
            else:
                query = urlencode(
                    {
                        "watering_device_id": saved_rule["watering_device_id"],
                        "saved": "1",
                        **({"field_id": field_id} if field_id else {}),
                    }
                )
                return redirect(f"/settings/post-watering-moisture?{query}")

    rules = service.list_rules()
    requested_watering_device_id = str(
        (submitted or {}).get("watering_device_id")
        or request.form.get("watering_device_id")
        or request.args.get("watering_device_id")
        or (watering_devices[0]["id"] if watering_devices else "")
    )
    existing_rule = next((rule for rule in rules if rule.get("watering_device_id") == requested_watering_device_id), None)
    selected_rule = submitted or existing_rule or {}
    sensor_ids = {item["id"] for item in soil_sensors}
    selected_sensor_id = str(selected_rule.get("sensor_device_id") or "")
    if selected_sensor_id not in sensor_ids:
        selected_sensor_id = requested_watering_device_id if requested_watering_device_id in sensor_ids else (soil_sensors[0]["id"] if soil_sensors else "")
    try:
        minimum_percent = float(selected_rule.get("minimum_percent", DEFAULT_MINIMUM_PERCENT))
    except (TypeError, ValueError):
        minimum_percent = DEFAULT_MINIMUM_PERCENT
    selected_values = {
        "watering_device_id": requested_watering_device_id,
        "sensor_device_id": selected_sensor_id,
        "minimum_percent": minimum_percent,
        "enabled": selected_rule.get("enabled") is not False,
    }
    response = app.make_response(
        (
            render_template(
                "post_watering_moisture_wizard.html",
                watering_devices=watering_devices,
                soil_sensors=soil_sensors,
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
    all_device_records = dict(device_config_service().get_all_records() or {})
    all_device_records.update(field_device_records or {})
    rules = [
        rule
        for rule in post_watering_moisture_service().list_rules()
        if isinstance(rule, dict) and rule.get("watering_device_id")
    ]
    placement_by_device = {}
    for row in placement_rows or []:
        device_id = row.get("device_id")
        if device_id:
            placement_by_device.setdefault(device_id, row)

    field_device_ids = set(field_device_records or {})
    field_watering_records = {
        device_id: record
        for device_id, record in (field_device_records or {}).items()
        if str(record.get("device_kind") or (record.get("last_status") or {}).get("device_kind") or "").upper() in WATERING_DEVICE_KINDS
    }

    discord = setting().get("discord") or {}
    discord_ready = bool(
        discord.get("webhook_url")
        and discord.get("enabled", True)
        and discord.get("notify_post_watering_moisture_low", True)
    )
    if not discord.get("webhook_url"):
        discord_status_label = "Discord Webhook未設定"
    elif not discord.get("enabled", True):
        discord_status_label = "すべてのDiscord通知が停止中"
    elif not discord.get("notify_post_watering_moisture_low", True):
        discord_status_label = "潅水後通知が停止中"
    else:
        discord_status_label = "Discord通知準備済み"

    def build_card(watering_device_id, watering_record, rule=None, placement=None, *, linked_via_sensor=False):
        device_kind = str(watering_record.get("device_kind") or (watering_record.get("last_status") or {}).get("device_kind") or "").upper()
        sensor_record = all_device_records.get((rule or {}).get("sensor_device_id")) or {}
        latest_percent = soil_moisture_value(sensor_record.get("last_status") or {}) if rule else None
        placement = placement or {}
        if not rule:
            state = "unconfigured"
            state_label = "未設定"
        elif rule.get("enabled") is not True:
            state = "paused"
            state_label = "停止中"
        elif watering_record.get("state") != "active":
            state = "warning"
            state_label = "潅水機確認"
        elif sensor_record.get("state") != "active":
            state = "warning"
            state_label = "センサー確認"
        elif not discord_ready:
            state = "warning"
            state_label = "通知準備待ち"
        else:
            state = "active"
            state_label = "監視中"
        return {
            "watering_device_id": watering_device_id,
            "watering_device_name": watering_record.get("name") or watering_device_id,
            "device_kind": device_kind or "不明",
            "scope_label": placement.get("scope_label") or watering_record.get("location") or "圃場全体",
            "configured": bool(rule),
            "enabled": bool(rule and rule.get("enabled") is True),
            "wizard_available": bool(rule) or watering_record.get("state") == "active",
            "state": state,
            "state_label": state_label,
            "linked_via_sensor": linked_via_sensor,
            "sensor_device_id": (rule or {}).get("sensor_device_id") or "",
            "sensor_device_name": sensor_record.get("name") or (rule or {}).get("sensor_device_id") or "未選択",
            "sensor_state_label": "利用中" if sensor_record.get("state") == "active" else "停止・未確認",
            "latest_percent": latest_percent,
            "minimum_percent": (rule or {}).get("minimum_percent"),
            "wizard_url": f"/settings/post-watering-moisture?{urlencode({'watering_device_id': watering_device_id, 'field_id': field_id})}",
            "device_settings_url": f"/mqtt-devices/{watering_device_id}?tab=settings",
        }

    cards = []
    linked_field_watering_ids = set()
    for rule in rules:
        watering_device_id = str(rule.get("watering_device_id") or "")
        sensor_device_id = str(rule.get("sensor_device_id") or "")
        if watering_device_id not in field_device_ids and sensor_device_id not in field_device_ids:
            continue
        watering_record = all_device_records.get(watering_device_id) or {}
        linked_via_sensor = watering_device_id not in field_device_ids and sensor_device_id in field_device_ids
        placement = placement_by_device.get(watering_device_id) or placement_by_device.get(sensor_device_id) or {}
        cards.append(build_card(watering_device_id, watering_record, rule, placement, linked_via_sensor=linked_via_sensor))
        linked_field_watering_ids.update({watering_device_id, sensor_device_id} & set(field_watering_records))

    for watering_device_id, watering_record in field_watering_records.items():
        if watering_device_id in linked_field_watering_ids:
            continue
        cards.append(build_card(watering_device_id, watering_record, placement=placement_by_device.get(watering_device_id) or {}))

    cards.sort(key=lambda item: (item["scope_label"].casefold(), item["watering_device_name"].casefold(), item["watering_device_id"]))
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
    record = device_config_service().get_record(device_id)
    if record is None:
        return jsonify({"error": "device not found"}), 404
    statuses = device_config_service().list_statuses(device_id, limit=MQTT_ADMIN_STATUS_HISTORY_LIMIT)
    return jsonify(_build_mqtt_device_chart_payload(statuses, record.get("device_kind")))


@app.route("/demo/local/api/mqtt-devices/<device_id>/charts", methods=["GET"])
def get_demo_mqtt_device_charts(device_id):
    demo_data = _demo_mqtt_admin_page_data(device_id)
    if demo_data["selected_device_id"] != device_id:
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
