import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import plotly
from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, send_file, stream_template
from plotly import graph_objs as go
from plotly.io import to_html

from ina_device_hub.agri_action_service import METRIC_LABELS, build_action_candidates
from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.device_config_repository import DeviceConfigValidationError, DeviceRecordValidationError
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.device_event_log import list_device_events
from ina_device_hub.field_calendar_view import build_calendar_todo_items as _build_calendar_todo_items
from ina_device_hub.field_layout_repository import (
    FieldLayoutConflictError,
    FieldLayoutValidationError,
    field_layout_repository,
)
from ina_device_hub.field_record_calendar import (
    build_field_record_calendar as _build_field_record_calendar,
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
from ina_device_hub.location_repository import location_repository
from ina_device_hub.ota_update_service import FirmwareArtifactValidationError, extract_firmware_manifest, ota_update_service
from ina_device_hub.plant_management_repository import (
    PlantManagementNotFoundError,
    PlantManagementValidationError,
    plant_management_repository,
)
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.sensor_measurement_repository import extract_measurements_from_status, sensor_measurement_repository
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.timelapse_media_service import timelapse_media_service
from ina_device_hub.utils import Utils

app = Flask(__name__)
MQTT_ADMIN_STATUS_HISTORY_LIMIT = 2000
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
    "irrigation_line": "ホース・配管（任意）",
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
    return datetime.now().astimezone().tzinfo


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
      <body>
        <h1>INA Device Hub</h1>
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
      <body>
        <h1>INA Device Hub</h1>
        <h2>Edit Device Info</h2>
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
      <body>
        <h1>INA Device Hub</h1>
        <h2>Locations</h2>
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
      <body>
        <h1>INA Device Hub</h1>
        <h2>Add Location</h2>
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


@app.route("/camera/<device_id>/preview", methods=["GET"])
def preview_camera(device_id):
    # シンプルな HTML を生成して、device_id の見出しとレスポンシブな動画を表示
    html = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Camera Stream - {{ device_id }}</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            h1 { text-align: center; margin-bottom: 20px; }
            .video-container { display: flex; justify-content: center; }
            .video-container img { width: 100%; max-width: 800px; height: auto; }
        </style>
    </head>
    <body>
        <h1>Device: {{ device_id }}</h1>
        <div class="video-container">
            <img src="/local/api/camera/{{ device_id }}/video_feed" alt="Camera Stream">
        </div>
    </body>
    </html>
    """
    return render_template_string(html, device_id=device_id)


@app.route("/camera/<device_id>/images", methods=["GET"])
def camera_images(device_id):
    date_value = request.args.get("date", "").strip()
    limit = _request_limit(default=48, maximum=500)
    start_at, end_at, date_error = _camera_image_date_range(date_value)
    if date_error:
        return jsonify({"error": date_error}), 400

    images = timelapse_media_service().list_frame_records(
        device_id,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
    )
    camera = camera_connector().camera_device_repository.get(device_id) or {}
    html = """
    <!doctype html>
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Camera Images</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 0; background: #f7f8fa; color: #20242a; }
          header { padding: 16px 20px; background: #ffffff; border-bottom: 1px solid #dfe3e8; }
          main { padding: 16px 20px 28px; }
          form { display: flex; flex-wrap: wrap; gap: 8px; align-items: end; margin-bottom: 16px; }
          label { display: grid; gap: 4px; font-size: 13px; color: #4d5662; }
          input, button { font-size: 15px; padding: 8px 10px; border: 1px solid #c8ced6; border-radius: 6px; background: #fff; }
          button { cursor: pointer; background: #1f6feb; border-color: #1f6feb; color: #fff; }
          .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
          .image-card { background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; overflow: hidden; }
          .image-card img { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; display: block; background: #e9edf2; }
          .meta { padding: 8px 10px; font-size: 13px; color: #4d5662; }
          .empty { padding: 28px; background: #fff; border: 1px solid #dfe3e8; border-radius: 8px; color: #4d5662; }
          a { color: #1f6feb; text-decoration: none; }
        </style>
      </head>
      <body>
        <header>
          <h1>Camera Images</h1>
          <div>{{ camera_name }} / {{ device_id }}</div>
        </header>
        <main>
          <form method="get">
            <label>
              Date
              <input type="date" name="date" value="{{ date_value }}">
            </label>
            <label>
              Limit
              <input type="number" name="limit" min="1" max="500" value="{{ limit }}">
            </label>
            <button type="submit">表示</button>
            <a href="/camera/{{ device_id }}/images">直近</a>
            <a href="/camera/{{ device_id }}/preview">ライブ</a>
          </form>
          {% if images %}
          <div class="grid">
            {% for image in images %}
            <a class="image-card" href="{{ image.url }}" target="_blank" rel="noreferrer">
              <img src="{{ image.url }}" alt="{{ image.captured_at }}">
              <div class="meta">{{ image.captured_at }}</div>
            </a>
            {% endfor %}
          </div>
          {% else %}
          <div class="empty">画像がありません。</div>
          {% endif %}
        </main>
      </body>
    </html>
    """
    return render_template_string(
        html,
        device_id=device_id,
        camera_name=camera.get("name") or device_id,
        date_value=date_value,
        limit=limit,
        images=images,
    )


def _build_mqtt_admin_view(devices, selected_device_id, selected_device, selected_statuses, selected_ota_statuses):
    now = datetime.now(UTC)
    device_summaries = [
        _build_device_summary(device_id, record, now) for device_id, record in sorted(devices.items(), key=lambda item: _device_sort_key(item[0], item[1]))
    ]
    return {
        "devices": device_summaries,
        "field_zones": _build_field_zones(device_summaries, selected_device_id),
        "selected": _build_selected_device_view(selected_device_id, selected_device, selected_statuses, selected_ota_statuses, now)
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
                    "watering": device["watering_label"],
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
    }


def _build_selected_device_view(device_id, record, statuses, ota_statuses, now):
    payload = _latest_status_payload(record)
    config = record.get("config") or {}
    device_kind = record.get("device_kind") or payload.get("device_kind") or ""
    watering = _watering_state(payload)
    return {
        "id": device_id,
        "title": record.get("name") or device_id,
        "location": record.get("location") or "場所未設定",
        "memo": record.get("memo") or "",
        "device_kind": device_kind,
        "kind_label": _device_kind_label(device_kind),
        "supports_irrigation": device_kind in {"WTR", "WRS"},
        "state_label": _device_state_label(record.get("state")),
        "state_class": _device_state_class(record.get("state")),
        "watering": watering,
        "soil_moisture": _format_percent(payload.get("last_soil_moisture")),
        "threshold": _format_percent(payload.get("threshold") if payload.get("threshold") is not None else config.get("moisture_threshold")),
        "last_seen": _format_datetime(record.get("last_seen_at") or record.get("last_status_at")),
        "last_seen_age": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
        "next_wake": _format_next_wake(record.get("last_status_at"), payload.get("next_sleep_sec")),
        "next_wake_detail": _format_duration(payload.get("next_sleep_sec")),
        "firmware": record.get("firmware_version") or "未取得",
        "target_firmware": record.get("target_firmware_version") or "設定なし",
        "ota_state": _ota_state_label(record.get("ota_state")),
        "ota_class": _ota_state_class(record.get("ota_state")),
        "ota_error": record.get("ota_error") or "",
        "summary_metrics": _build_device_summary_metrics(record, payload, now, watering),
        "monitoring_charts": _build_device_monitoring_charts(device_kind, statuses),
        "schedules": _format_schedules_for_ui(config.get("schedules") or [], config),
        "config_summary": _format_config_summary(config),
        "installation": _build_device_installation_view(config, payload),
        "watering_history": _build_watering_history(statuses),
        "wake_history": _build_wake_history(statuses),
        "ota_history": _build_ota_history(ota_statuses),
    }


def _build_device_summary_metrics(record, payload, now, watering):
    device_kind = record.get("device_kind") or payload.get("device_kind") or ""
    metrics = []

    if device_kind in {"WTR", "WRS"}:
        metrics.append(
            {
                "label": "潅水",
                "value": watering["label"],
                "class": watering["class"],
                "hint": "最後のstatusから判断",
            }
        )

    metric_specs = {
        "WTR": (("土壌水分", ("last_soil_moisture", "soil_moisture_percent"), "%", 1),),
        "WRS": (
            ("土壌水分", ("soil_moisture_percent", "last_soil_moisture"), "%", 1),
            ("土壌EC", ("soil_ec_us_cm",), "uS/cm", 0),
            ("土壌pH", ("soil_ph",), "", 1),
            ("PAR", ("par_umol_m2_s",), "umol/m2/s", 0),
        ),
        "ENV": (
            ("気温", ("air_temperature_c",), "℃", 1),
            ("湿度", ("air_humidity_percent",), "%", 1),
            ("PAR", ("par_umol_m2_s",), "umol/m2/s", 0),
        ),
        "SOI": (
            ("土壌水分", ("soil_moisture_percent", "last_soil_moisture"), "%", 1),
            ("地温", ("soil_temperature_c",), "℃", 1),
            ("土壌EC", ("soil_ec_us_cm",), "uS/cm", 0),
            ("土壌pH", ("soil_ph",), "", 1),
        ),
        "PAR": (("PAR", ("par_umol_m2_s",), "umol/m2/s", 0),),
    }
    for label, aliases, unit, digits in metric_specs.get(device_kind, ()):
        value = _first_numeric_value(payload, aliases)
        metrics.append(
            {
                "label": label,
                "value": _format_measurement_value(value, unit, digits),
                "class": "",
                "hint": "直近の計測値",
            }
        )

    metrics.extend(
        [
            {
                "label": "最終通信",
                "value": _format_age(record.get("last_seen_at") or record.get("last_status_at"), now),
                "class": "",
                "hint": _format_datetime(record.get("last_seen_at") or record.get("last_status_at")),
            },
            {
                "label": "ファームウェア",
                "value": record.get("firmware_version") or "未取得",
                "class": "",
                "hint": f"更新目標 {record.get('target_firmware_version') or '設定なし'}",
            },
            {
                "label": "更新状態",
                "value": _ota_state_label(record.get("ota_state")),
                "class": _ota_state_class(record.get("ota_state")),
                "hint": record.get("ota_error") or "問題なし",
            },
        ]
    )
    return metrics


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


def _build_device_monitoring_charts(device_kind, statuses):
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
    specs = chart_specs.get(device_kind)
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
            "dom_id": dom_ids[kind],
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


def _build_device_installation_view(config, payload):
    config = config if isinstance(config, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    active_mask = payload.get("channel_mask") if payload.get("watering_started") is True and isinstance(payload.get("channel_mask"), int) else 0
    lines = []
    auxiliaries = []

    for index, switch in enumerate(config.get("mosfet_switches") or []):
        if not isinstance(switch, dict) or switch.get("enabled") is False:
            continue
        channel_mask = switch.get("channel_mask")
        if not isinstance(channel_mask, int):
            channel_mask = 0
        name = switch.get("name") if isinstance(switch.get("name"), str) and switch.get("name").strip() else switch.get("switch_id") or f"SW {index + 1}"
        item = {
            "name": name,
            "role": _mosfet_role_label(switch.get("role")),
            "terminal": switch.get("terminal") or "端子未設定",
            "controlled_load": switch.get("controlled_load") or "制御対象未設定",
            "channel_mask": channel_mask,
            "mask_label": f"mask {channel_mask}" if channel_mask > 0 else "予約対象外",
            "class": "good" if channel_mask > 0 and active_mask & channel_mask else "ok",
        }
        if channel_mask > 0 and switch.get("role") != "sensor_power":
            lines.append(item)
        else:
            item["class"] = "muted" if channel_mask == 0 else item["class"]
            auxiliaries.append(item)

    if not lines:
        seen_masks = []
        for schedule in config.get("schedules") or []:
            if not isinstance(schedule, dict):
                continue
            channel_mask = schedule.get("channel_mask")
            if isinstance(channel_mask, int) and channel_mask > 0 and channel_mask not in seen_masks:
                seen_masks.append(channel_mask)
        for channel_mask in seen_masks:
            lines.append(
                {
                    "name": _format_channel_mask_for_config(channel_mask, config),
                    "role": "灌水",
                    "terminal": "端子未設定",
                    "controlled_load": "制御対象未設定",
                    "channel_mask": channel_mask,
                    "mask_label": f"mask {channel_mask}",
                    "class": "good" if active_mask & channel_mask else "ok",
                }
            )

    return {
        "lines": lines,
        "auxiliaries": auxiliaries,
        "line_count": len(lines),
        "auxiliary_count": len(auxiliaries),
        "active_mask": active_mask,
    }


def _mosfet_role_label(role):
    return {
        "irrigation": "灌水",
        "sensor_power": "センサー電源",
        "other": "その他",
    }.get(role, str(role or "未分類"))


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


def _build_watering_history(statuses, limit=8):
    history = []
    for entry in reversed(statuses or []):
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict) or not _has_watering_information(payload):
            continue
        watering = _watering_state(payload)
        history.append(
            {
                "time": _format_datetime(entry.get("received_at")),
                "label": watering["label"],
                "class": watering["class"],
                "duration": _format_duration(payload.get("watering_duration_sec")),
                "channel": _format_channel_mask(payload.get("channel_mask")),
                "soil": _format_percent(payload.get("last_soil_moisture")),
                "threshold": _format_percent(payload.get("threshold")),
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
    points = _soil_moisture_points(statuses)
    if not points:
        return None

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


def _build_metric_trend_chart(statuses, *, aliases, title, unit, color, div_id, include_plotlyjs=False, y_range=None):
    points = _metric_trend_points(statuses, aliases)
    if not points:
        return None

    unit_suffix = f" {unit}" if unit else ""
    fig = go.Figure()
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
        showlegend=False,
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
        duration_sec = payload.get("watering_duration_sec")
        duration_minutes = round(float(duration_sec) / 60, 2) if isinstance(duration_sec, int | float) else 0
        watering = _watering_state(payload)
        points.append(
            {
                "time": received_at,
                "duration_minutes": duration_minutes,
                "duration_label": _format_duration(duration_sec),
                "state": watering["label"],
                "channel": _format_channel_mask(payload.get("channel_mask")),
                "soil": _format_percent(payload.get("last_soil_moisture")),
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
    return any(
        key in payload
        for key in (
            "watering_due",
            "watering_started",
            "watering_duration_sec",
            "channel_mask",
            "last_soil_moisture",
            "threshold",
        )
    )


def _watering_state(payload):
    if not payload:
        return {"label": "未取得", "class": "muted"}
    if payload.get("watering_started") is True:
        return {"label": "灌水中", "class": "good"}
    if payload.get("watering_due") is True:
        return {"label": "灌水予定", "class": "warn"}
    if "watering_started" in payload or "watering_due" in payload or "last_soil_moisture" in payload:
        return {"label": "待機中", "class": "ok"}
    return {"label": "未取得", "class": "muted"}


def _device_kind_label(device_kind):
    labels = {
        "WTR": "水やり機",
        "WRS": "RS485全部入り水やり機",
        "ENV": "環境センサー",
        "SOI": "土壌センサー",
        "PAR": "日射・PARセンサー",
        "CAM": "カメラ",
    }
    if device_kind in labels:
        return labels[device_kind]
    if device_kind:
        return f"{device_kind} デバイス"
    return "種別未取得"


def _device_state_label(state):
    return {
        "active": "稼働中",
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


def _format_schedules_for_ui(schedules, config=None):
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
    return "・".join(channels) if channels else f"系統 mask={channel_mask}"


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
            "occurred_at": ago(12),
            "event_type": "connect",
            "direction": "in",
            "topic": f"ina/devices/{selected_device_id}/connection",
            "payload": {"client_id": selected_device_id, "result": "accepted"},
        },
        {
            "occurred_at": ago(10),
            "event_type": "disconnect",
            "direction": "in",
            "topic": f"ina/devices/{selected_device_id}/connection",
            "payload": {"client_id": selected_device_id, "reason": "deep_sleep"},
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


def _mqtt_devices_page_response(demo_mode=False, device_id=None, page_mode="list"):
    is_detail_page = page_mode == "detail"
    if demo_mode:
        demo_data = _demo_mqtt_admin_page_data(device_id)
        devices = demo_data["devices"]
        selected_device_id = demo_data["selected_device_id"] if is_detail_page else None
        selected_statuses = demo_data["selected_statuses"] if is_detail_page else []
        selected_ota_statuses = demo_data["selected_ota_statuses"] if is_detail_page else []
        firmware_artifacts = demo_data["firmware_artifacts"]
        recent_events = demo_data["recent_events"] if is_detail_page else []
        connection_events = demo_data["connection_events"] if is_detail_page else []
    else:
        devices = device_config_service().get_all_records()
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
    selected_device = devices.get(selected_device_id) if selected_device_id else None
    if is_detail_page and selected_device is None:
        return jsonify({"error": "device not found"}), 404
    admin_view = _build_mqtt_admin_view(devices, selected_device_id, selected_device, selected_statuses, selected_ota_statuses)
    device_link_prefix = "/demo/mqtt-devices/" if demo_mode else "/mqtt-devices/"
    list_path = "/demo/mqtt-devices" if demo_mode else "/mqtt-devices"
    template = """
    <!doctype html>
    <html lang="ja">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Hub 管理パネル</title>
        <style>
          :root {
            --bg: #f6f7f9;
            --panel: #ffffff;
            --line: #d8dee7;
            --text: #1f2933;
            --muted: #64748b;
            --blue: #1d4ed8;
            --green: #166534;
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
          a { color: var(--blue); text-decoration: none; }
          a:hover { text-decoration: underline; }
          .page { max-width: 1440px; margin: 0 auto; padding: 24px; }
          .topbar {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
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
          button:disabled { opacity: .65; cursor: wait; }
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
          .device-field {
            position: relative;
            overflow: hidden;
            border: 1px solid #adc7ad;
            border-radius: 8px;
            background: linear-gradient(180deg, #edf7ee 0%, #f8fafc 100%);
            padding: 16px;
          }
          .device-field::before {
            content: "";
            position: absolute;
            inset: 76px 16px 16px;
            border-radius: 6px;
            background: repeating-linear-gradient(90deg, rgba(22, 101, 52, .10) 0 2px, transparent 2px 24px);
            pointer-events: none;
          }
          .device-field > * { position: relative; }
          .device-field-grid {
            display: grid;
            grid-template-columns: minmax(220px, .75fr) minmax(0, 1.25fr);
            gap: 14px;
            align-items: stretch;
          }
          .controller-node, .line-node {
            border: 1px solid rgba(148, 163, 184, .55);
            border-radius: 8px;
            background: rgba(255, 255, 255, .94);
            padding: 12px;
          }
          .controller-node {
            display: grid;
            align-content: center;
            min-height: 150px;
            border-color: #64748b;
          }
          .line-stack { display: grid; gap: 10px; }
          .line-node {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 8px;
            border-left: 5px solid #0284c7;
          }
          .line-node.good { border-left-color: var(--green); }
          .line-node.ok { border-left-color: #0284c7; }
          .line-node.warn { border-left-color: #d97706; }
          .line-node.muted { border-left-color: #94a3b8; color: var(--muted); }
          .line-title { font-weight: 700; font-size: 15px; }
          .line-sub { color: var(--muted); font-size: 12px; margin-top: 3px; }
          .line-mask { color: var(--muted); font-size: 12px; white-space: nowrap; }
          .compact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
          .device-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 12px;
          }
          .device-tile {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 10px;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px;
            background: #fff;
          }
          .device-tile[aria-current="true"] { border-color: var(--blue); box-shadow: inset 3px 0 0 var(--blue); }
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
          .config-form { display: grid; gap: 14px; }
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
          .mosfet-switch-row {
            display: grid;
            grid-template-columns: 92px minmax(120px, .8fr) minmax(150px, 1fr) minmax(120px, .8fr) minmax(110px, .7fr) minmax(180px, 1fr) auto;
            gap: 10px;
            align-items: end;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px;
            background: #fff;
          }
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
            display: inline-grid;
            place-items: center;
            width: 36px;
            height: 36px;
            flex: 0 0 36px;
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            color: var(--text);
            font-size: 19px;
            text-decoration: none;
          }
          .chart-settings-link:hover, .chart-settings-link:focus-visible { border-color: var(--blue); color: var(--blue); }
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
            .device-field-grid { grid-template-columns: 1fr; }
            .line-node { grid-template-columns: 1fr; }
            .section-grid { grid-template-columns: 1fr; }
            .tile-metrics { grid-template-columns: 1fr; }
            .list-row { grid-template-columns: 1fr; }
            .ridge-row { grid-template-columns: 1fr; }
            .ridge-meta { justify-content: flex-start; }
            .schedule-row, .mosfet-switch-row { grid-template-columns: 1fr; }
            .tab-list { margin-inline: -16px; border-radius: 0; padding-inline: 16px; }
          }
        </style>
      </head>
      <body>
        <div class="page">
          <div id="global-progress" class="progress-banner" role="status" aria-live="polite">
            <span class="progress-dot" aria-hidden="true"></span>
            <span id="global-progress-message">処理中...</span>
          </div>
          <div class="topbar">
            <div>
              <h1>機器管理</h1>
              <p class="lead">設置場所、計測値、稼働状態、設定、F/Wを機器ごとに確認します。</p>
            </div>
            <nav class="nav" aria-label="ページ移動">
              <a href="{{ list_path }}">機器一覧</a>
              {% if demo_mode %}
              <a href="/mqtt-devices">実データ</a>
              {% else %}
              <a href="/demo/mqtt-devices">UI デモ</a>
              {% endif %}
              <a href="/">ホーム</a>
            </nav>
          </div>
          {% if demo_mode %}
          <div class="notice"><strong>デモデータ表示中</strong> 操作は保存されません。UI/UX 確認専用です。</div>
          {% endif %}
          {% if is_detail_page %}
          <div id="action-result" class="result">{{ "デモモードです。操作しても保存されません。" if demo_mode else "操作結果がここに表示されます。" }}</div>
          <div class="back-link"><a href="{{ list_path }}">機器一覧へ戻る</a></div>
          {% endif %}

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
            <h2>水やり機一覧</h2>
            <p class="lead">カードを選ぶと、水やり機ごとの詳しい履歴と設定を確認できます。</p>
            {% if admin_view.devices %}
            <div class="device-grid">
              {% for device in admin_view.devices %}
              <a class="device-tile" href="{{ device_link_prefix }}{{ device.id }}" aria-current="{{ 'true' if device.id == selected_device_id else 'false' }}">
                <div>
                  <div class="device-title">{{ device.name }}</div>
                  <div class="device-sub">{{ device.kind_label }} / {{ device.location }}</div>
                  <div class="device-sub">{{ device.id }}</div>
                </div>
                <div>
                  <span class="badge {{ device.state_class }}">{{ device.state_label }}</span>
                </div>
                <div class="tile-metrics">
                  <div class="mini"><span>灌水</span><strong>{{ device.watering_label }}</strong></div>
                  <div class="mini"><span>土壌水分</span><strong>{{ device.soil_moisture }}</strong></div>
                  <div class="mini"><span>次回起床</span><strong>{{ device.next_wake }}</strong></div>
                </div>
              </a>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty">まだ MQTT device が登録されていません。</div>
            {% endif %}
          </section>
          {% endif %}

          {% if is_detail_page and admin_view.selected %}
          {% set selected = admin_view.selected %}
          <section class="panel">
            <div class="detail-header">
              <div>
                <h2>{{ selected.title }}</h2>
                <p class="lead">{{ selected.kind_label }} / {{ selected.location }} / {{ selected.id }}</p>
                {% if selected.memo %}<p>{{ selected.memo }}</p>{% endif %}
              </div>
              <span class="badge {{ selected.state_class }}">{{ selected.state_label }}</span>
            </div>
            <div class="metrics">
              {% for metric in selected.summary_metrics %}
              <div class="metric">
                <span class="label">{{ metric.label }}</span>
                <span class="value">{% if metric.class %}<span class="badge {{ metric.class }}">{{ metric.value }}</span>{% else %}{{ metric.value }}{% endif %}</span>
                <div class="hint">{{ metric.hint }}</div>
              </div>
              {% endfor %}
            </div>
          </section>

          <div class="detail-tabs">
            <div class="tab-list" role="tablist" aria-label="機器詳細メニュー">
              <button type="button" class="tab-button" data-tab-key="overview" data-tab-target="tab-overview" role="tab" aria-controls="tab-overview" aria-selected="true" tabindex="0">概要</button>
              <button type="button" class="tab-button" data-tab-key="monitoring" data-tab-target="tab-monitoring" role="tab" aria-controls="tab-monitoring" aria-selected="false" tabindex="-1">計測・稼働</button>
              <button type="button" class="tab-button" data-tab-key="settings" data-tab-target="tab-config" role="tab" aria-controls="tab-config" aria-selected="false" tabindex="-1">動作設定</button>
              <button type="button" class="tab-button" data-tab-key="firmware" data-tab-target="tab-firmware" role="tab" aria-controls="tab-firmware" aria-selected="false" tabindex="-1">F/W更新</button>
              <button type="button" class="tab-button" data-tab-key="diagnostics" data-tab-target="tab-diagnostics" role="tab" aria-controls="tab-diagnostics" aria-selected="false" tabindex="-1">履歴・診断</button>
            </div>

            <section id="tab-overview" class="tab-panel" role="tabpanel">
              {% if selected.supports_irrigation %}
              <section class="device-field" aria-label="選択デバイス設置ビュー">
                <div class="field-head">
                  <div>
                    <h2>設置ビュー</h2>
                    <p class="lead">{{ selected.location }} の中で、このデバイスが制御する灌水ラインと設備だけを表示します。</p>
                  </div>
                  <span class="badge muted">{{ selected.installation.line_count }} 灌水系</span>
                </div>
                <div class="device-field-grid">
                  <div class="controller-node">
                    <h3>{{ selected.title }}</h3>
                    <div class="line-sub">{{ selected.kind_label }}</div>
                    <div class="line-sub">最終通信: {{ selected.last_seen_age }}</div>
                    <div class="line-sub">更新状態: {{ selected.ota_state }}</div>
                  </div>
                  <div class="line-stack">
                    {% if selected.installation.lines %}
                    {% for line in selected.installation.lines %}
                    <div class="line-node {{ line.class }}">
                      <div>
                        <div class="line-title">{{ line.name }}</div>
                        <div class="line-sub">{{ line.role }} / {{ line.terminal }} / {{ line.controlled_load }}</div>
                      </div>
                      <div class="line-mask">{{ line.mask_label }}</div>
                    </div>
                    {% endfor %}
                    {% else %}
                    <div class="empty">灌水ラインがまだ設定されていません。</div>
                    {% endif %}
                    {% if selected.installation.auxiliaries %}
                    {% for item in selected.installation.auxiliaries %}
                    <div class="line-node {{ item.class }}">
                      <div>
                        <div class="line-title">{{ item.name }}</div>
                        <div class="line-sub">{{ item.role }} / {{ item.terminal }} / {{ item.controlled_load }}</div>
                      </div>
                      <div class="line-mask">{{ item.mask_label }}</div>
                    </div>
                    {% endfor %}
                    {% endif %}
                  </div>
                </div>
              </section>
              {% else %}
              <section class="panel">
                <h2>設置情報</h2>
                <div class="compact-grid">
                  <div class="mini"><span>機器名</span><strong>{{ selected.title }}</strong></div>
                  <div class="mini"><span>機器種別</span><strong>{{ selected.kind_label }}</strong></div>
                  <div class="mini"><span>設置場所</span><strong>{{ selected.location }}</strong></div>
                  <div class="mini"><span>機器ID</span><strong>{{ selected.id }}</strong></div>
                </div>
              </section>
              {% endif %}

              <div class="section-grid">
                {% if selected.supports_irrigation %}
                <section class="panel">
                  <h2>灌水予約</h2>
                  {% if selected.schedules %}
                  <div class="schedule-grid">
                    {% for schedule in selected.schedules %}
                    <div class="schedule">
                      <strong>{{ schedule.time }}</strong>
                      <div class="line-sub">{{ schedule.duration }} / {{ schedule.channel }}</div>
                    </div>
                    {% endfor %}
                  </div>
                  {% else %}
                  <div class="empty">灌水予約はまだありません。</div>
                  {% endif %}
                </section>
                {% endif %}

                <section class="panel">
                  <h2>通信・F/W状態</h2>
                  <div class="compact-grid">
                    <div class="mini"><span>最終通信</span><strong>{{ selected.last_seen_age }}</strong></div>
                    <div class="mini"><span>次回起動</span><strong>{{ selected.next_wake }}</strong></div>
                    <div class="mini"><span>F/W</span><strong>{{ selected.firmware }}</strong></div>
                    <div class="mini"><span>更新状態</span><strong>{{ selected.ota_state }}</strong></div>
                  </div>
                </section>
              </div>
            </section>

            <section id="tab-config" class="tab-panel" role="tabpanel" hidden>
          <section class="panel">
            <h2>機器情報</h2>
            <form id="metadata-form">
              <div class="form-grid">
                <div><label for="metadata-name">表示名</label><input id="metadata-name" name="name" type="text" value="{{ selected_device.name or '' }}"></div>
                <div><label for="metadata-location">場所</label><input id="metadata-location" name="location" type="text" value="{{ selected_device.location or '' }}"></div>
                <div><label for="metadata-memo">メモ</label><input id="metadata-memo" name="memo" type="text" value="{{ selected_device.memo or '' }}"></div>
              </div>
              <div class="actions"><button type="submit" class="primary">表示情報を保存</button></div>
            </form>
          </section>
          <section class="panel">
            <h2>動作設定</h2>
            <form id="runtime-config-form" class="config-form">
              <div class="metrics">
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
                <div class="metric">
                  <span class="label">デバッグログ</span>
                  <span class="value"><span id="debug-log-display">{{ selected.config_summary.debug_log }}</span></span>
                  <div class="hint">次回起床時にMQTTへ転送します</div>
                </div>
                <div class="metric">
                  <span class="label">OTA確認間隔</span>
                  <span class="value"><span id="ota-interval-display">{{ selected.config_summary.ota_interval }}</span></span>
                  <div class="hint">最大sleep時間の上限です</div>
                </div>
              </div>

              <div class="config-toolbar">
                <div class="config-field"{% if not selected.supports_irrigation %} hidden{% endif %}>
                  <label for="moisture-threshold">灌水しきい値</label>
                  <div class="threshold-control">
                    <input id="moisture-threshold" type="range" min="0" max="100" step="1">
                    <input id="moisture-threshold-number" type="number" min="0" max="100" step="1">
                  </div>
                </div>
                <div class="config-field">
                  <label for="timezone-offset">時刻基準</label>
                  <select id="timezone-offset">
                    <option value="32400">JST UTC+09:00</option>
                    <option value="0">UTC</option>
                  </select>
                </div>
                <div class="config-field">
                  <label for="ntp-server">NTP サーバー</label>
                  <input id="ntp-server" type="text" autocomplete="off">
                </div>
                <label class="switch-row" for="force-watering"{% if not selected.supports_irrigation %} hidden{% endif %}>
                  <input id="force-watering" type="checkbox">
                  強制灌水
                </label>
                <label class="switch-row" for="debug-log-on-wake">
                  <input id="debug-log-on-wake" type="checkbox">
                  デバッグログ転送
                </label>
                <div class="config-field">
                  <label for="ota-check-interval">OTA確認間隔</label>
                  <select id="ota-check-interval">
                    <option value="3600">1時間</option>
                    <option value="10800">3時間</option>
                    <option value="21600">6時間</option>
                    <option value="43200">12時間</option>
                    <option value="86400">24時間</option>
                  </select>
                </div>
              </div>

              <div{% if not selected.supports_irrigation %} hidden{% endif %}>
                <h3>MOSFET SW 管理</h3>
                <div id="mosfet-switch-editor" class="mosfet-switch-editor"></div>
                <div class="actions">
                  <button type="button" id="add-mosfet-switch">＋ SW を追加</button>
                </div>
              </div>

              <div{% if not selected.supports_irrigation %} hidden{% endif %}>
                <h3>灌水予約</h3>
                <div id="schedule-editor" class="schedule-editor"></div>
                <div class="actions">
                  <button type="button" id="add-schedule">＋ 予約を追加</button>
                </div>
              </div>

              <div{% if not selected.supports_irrigation %} hidden{% endif %}>
                <h3>分割灌水</h3>
                <div class="config-toolbar">
                  <label class="switch-row" for="watering-pattern-enabled">
                    <input id="watering-pattern-enabled" type="checkbox">
                    分割灌水を使う
                  </label>
                  <div class="config-field">
                    <label for="watering-pattern-on-sec">ON 秒数</label>
                    <input id="watering-pattern-on-sec" type="number" min="0" max="3600" step="1">
                  </div>
                  <div class="config-field">
                    <label for="watering-pattern-off-sec">休止 秒数</label>
                    <input id="watering-pattern-off-sec" type="number" min="0" max="3600" step="1">
                  </div>
                  <div class="config-field">
                    <label for="watering-pattern-repeat-count">繰り返し回数</label>
                    <input id="watering-pattern-repeat-count" type="number" min="0" max="20" step="1">
                  </div>
                </div>
              </div>

              <div{% if selected.device_kind != "WTR" %} hidden{% endif %}>
                <h3>土壌水分計 校正</h3>
                <div class="config-toolbar">
                  <div class="config-field">
                    <label for="soil-calibration-mode">校正モード</label>
                    <select id="soil-calibration-mode">
                      <option value="normal">通常</option>
                      <option value="capture_dry">乾いた状態を記録</option>
                      <option value="capture_wet">湿った状態を記録</option>
                      <option value="reset">未校正に戻す</option>
                    </select>
                  </div>
                  <label class="switch-row" for="soil-calibration-calibrated">
                    <input id="soil-calibration-calibrated" type="checkbox">
                    手動校正値を使用
                  </label>
                  <label class="switch-row" for="soil-calibration-auto-mode">
                    <input id="soil-calibration-auto-mode" type="checkbox">
                    WTR 自動校正
                  </label>
                  <label class="switch-row" for="soil-calibration-apply-auto">
                    <input id="soil-calibration-apply-auto" type="checkbox">
                    WTR 自動反映
                  </label>
                  <label class="switch-row" for="soil-calibration-drift-check">
                    <input id="soil-calibration-drift-check" type="checkbox">
                    WTR ズレ検知
                  </label>
                  <div class="config-field">
                    <label for="soil-calibration-dry-raw">乾燥 raw</label>
                    <input id="soil-calibration-dry-raw" type="number" min="1" max="4095" step="1">
                  </div>
                  <div class="config-field">
                    <label for="soil-calibration-wet-raw">湿潤 raw</label>
                    <input id="soil-calibration-wet-raw" type="number" min="0" max="4094" step="1">
                  </div>
                  <div class="config-field">
                    <label for="soil-calibration-min-delta-raw">校正差分 raw</label>
                    <input id="soil-calibration-min-delta-raw" type="number" min="10" max="2000" step="1">
                  </div>
                  <div class="config-field">
                    <label for="soil-calibration-drift-tolerance-raw">ズレ検知 raw</label>
                    <input id="soil-calibration-drift-tolerance-raw" type="number" min="10" max="2000" step="1">
                  </div>
                  <div class="config-field">
                    <label for="soil-calibration-sample-count">平均回数</label>
                    <input id="soil-calibration-sample-count" type="number" min="1" max="100" step="1">
                  </div>
                  <div class="config-field">
                    <label for="soil-calibration-sample-interval-ms">平均間隔 ms</label>
                    <input id="soil-calibration-sample-interval-ms" type="number" min="0" max="1000" step="1">
                  </div>
                </div>
              </div>

              <div{% if selected.device_kind not in ["WRS", "ENV", "SOI", "PAR"] %} hidden{% endif %}>
                <h3>環境センサー 校正</h3>
                <div class="config-toolbar">
                  <label class="switch-row" for="env-par-enabled">
                    <input id="env-par-enabled" type="checkbox">
                    光量センサーを使う
                  </label>
                  <label class="switch-row" for="env-soil-enabled">
                    <input id="env-soil-enabled" type="checkbox">
                    土壌EC/pH/NPKセンサーを使う
                  </label>
                  <div class="config-field">
                    <label for="env-calibration-mode">校正モード</label>
                    <select id="env-calibration-mode">
                      <option value="normal">通常</option>
                      <option value="capture_reference">基準値を記録</option>
                      <option value="reset">未校正に戻す</option>
                    </select>
                  </div>
                  <div class="config-field">
                    <label for="env-calibration-target">記録する項目</label>
                    <select id="env-calibration-target">
                      <option value="par_umol_m2_s">光合成に使える光</option>
                      <option value="soil_moisture_percent">土壌水分</option>
                      <option value="soil_temperature_c">地温</option>
                      <option value="soil_ec_us_cm">土壌EC</option>
                      <option value="soil_ph">土壌pH</option>
                      <option value="soil_n_mg_kg">窒素</option>
                      <option value="soil_p_mg_kg">リン</option>
                      <option value="soil_k_mg_kg">カリウム</option>
                    </select>
                  </div>
                  <div class="config-field">
                    <label for="env-calibration-reference-value">基準値</label>
                    <input id="env-calibration-reference-value" type="number" step="0.01">
                  </div>
                </div>

                <details class="config-details">
                  <summary>環境センサー 詳細設定</summary>
                  <div class="config-toolbar">
                    <div class="config-field">
                      <label for="env-par-slave">光量センサー ID</label>
                      <input id="env-par-slave" type="number" min="1" max="247" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-par-function">光量 Function</label>
                      <input id="env-par-function" type="number" min="3" max="4" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-par-register">光量 Register</label>
                      <input id="env-par-register" type="number" min="0" max="65535" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-soil-slave">土壌センサー ID</label>
                      <input id="env-soil-slave" type="number" min="1" max="247" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-soil-function">土壌 Function</label>
                      <input id="env-soil-function" type="number" min="3" max="4" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-soil-start-register">土壌 Start Register</label>
                      <input id="env-soil-start-register" type="number" min="0" max="65535" step="1">
                    </div>
                    <div class="config-field">
                      <label for="env-power-settle-ms">12V 電源待ち ms</label>
                      <input id="env-power-settle-ms" type="number" min="0" max="30000" step="100">
                    </div>
                  </div>
                  <div class="config-toolbar">
                    <label class="switch-row" for="env-cal-par-calibrated"><input id="env-cal-par-calibrated" type="checkbox"> 光 校正済み</label>
                    <div class="config-field"><label for="env-cal-par-scale">光 scale</label><input id="env-cal-par-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-par-offset">光 offset</label><input id="env-cal-par-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-moisture-calibrated"><input id="env-cal-moisture-calibrated" type="checkbox"> 水分 校正済み</label>
                    <div class="config-field"><label for="env-cal-moisture-scale">水分 scale</label><input id="env-cal-moisture-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-moisture-offset">水分 offset</label><input id="env-cal-moisture-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-temperature-calibrated"><input id="env-cal-temperature-calibrated" type="checkbox"> 地温 校正済み</label>
                    <div class="config-field"><label for="env-cal-temperature-scale">地温 scale</label><input id="env-cal-temperature-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-temperature-offset">地温 offset</label><input id="env-cal-temperature-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-ec-calibrated"><input id="env-cal-ec-calibrated" type="checkbox"> EC 校正済み</label>
                    <div class="config-field"><label for="env-cal-ec-scale">EC scale</label><input id="env-cal-ec-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-ec-offset">EC offset</label><input id="env-cal-ec-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-ph-calibrated"><input id="env-cal-ph-calibrated" type="checkbox"> pH 校正済み</label>
                    <div class="config-field"><label for="env-cal-ph-scale">pH scale</label><input id="env-cal-ph-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-ph-offset">pH offset</label><input id="env-cal-ph-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-n-calibrated"><input id="env-cal-n-calibrated" type="checkbox"> 窒素 校正済み</label>
                    <div class="config-field"><label for="env-cal-n-scale">窒素 scale</label><input id="env-cal-n-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-n-offset">窒素 offset</label><input id="env-cal-n-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-p-calibrated"><input id="env-cal-p-calibrated" type="checkbox"> リン 校正済み</label>
                    <div class="config-field"><label for="env-cal-p-scale">リン scale</label><input id="env-cal-p-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-p-offset">リン offset</label><input id="env-cal-p-offset" type="number" step="0.01"></div>
                    <label class="switch-row" for="env-cal-k-calibrated"><input id="env-cal-k-calibrated" type="checkbox"> カリウム 校正済み</label>
                    <div class="config-field"><label for="env-cal-k-scale">カリウム scale</label><input id="env-cal-k-scale" type="number" step="0.0001"></div>
                    <div class="config-field"><label for="env-cal-k-offset">カリウム offset</label><input id="env-cal-k-offset" type="number" step="0.01"></div>
                  </div>
                </details>
              </div>

              <div class="actions">
                <button type="submit">設定を保存</button>
                <button type="button" id="save-push-runtime-config" class="primary">保存して device に送信</button>
                <button type="button" id="push-runtime-config">保存済み設定を送信</button>
              </div>
            </form>
          </section>
            </section>

            <section id="tab-monitoring" class="tab-panel" role="tabpanel" hidden>
          {% if selected.monitoring_charts %}
          <div class="section-grid">
            {% for chart in selected.monitoring_charts %}
            <section class="panel">
              <div class="device-chart-heading">
                <h2>{{ selected.title }} / {{ chart.title }}</h2>
                <a class="chart-settings-link" href="{{ device_link_prefix }}{{ selected.id }}?tab=settings" title="{{ selected.title }}の動作設定" aria-label="{{ selected.title }}の動作設定">&#9881;</a>
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
                  </div>
                </div>
                {% endfor %}
              </div>
            </div>
          </details>
          {% endif %}

          <section class="panel">
              <h2>起動・通信履歴</h2>
              {% if selected.wake_history %}
              <div class="list">
                {% for item in selected.wake_history %}
                <div class="list-row">
                  <div class="list-time">{{ item.time }}</div>
                  <div class="list-main">
                    <span>seq: {{ item.seq }}</span>
                    <span>次回起床: {{ item.next_wake }}</span>
                    <span>設定受信: {{ item.config_received }}</span>
                    <span>時刻同期: {{ item.time_synced }}</span>
                    <span>RSSI: {{ item.rssi }}</span>
                  </div>
                </div>
                {% endfor %}
              </div>
              {% else %}
              <div class="empty">起動・通信履歴はまだありません。</div>
              {% endif %}
          </section>
            </section>

            <section id="tab-firmware" class="tab-panel" role="tabpanel" hidden>
          <section id="ota-target" class="panel">
            <h2>F/W更新</h2>
            <div class="metrics">
              <div class="metric"><span class="label">現在のF/W</span><span class="value">{{ selected.firmware }}</span><div class="hint">機器から取得</div></div>
              <div class="metric"><span class="label">更新目標</span><span class="value">{{ selected.target_firmware }}</span><div class="hint">次回OTA確認時に適用</div></div>
              <div class="metric"><span class="label">更新状態</span><span class="value"><span class="badge {{ selected.ota_class }}">{{ selected.ota_state }}</span></span><div class="hint">{{ selected.ota_error or "問題なし" }}</div></div>
            </div>
            <form id="firmware-target-form">
              <label for="target-firmware-version">更新するF/Wバージョン</label>
              <select id="target-firmware-version">
                <option value="">設定なし</option>
                {% for artifact in firmware_target_options %}
                <option value="{{ artifact.version }}" {% if selected_device.target_firmware_version == artifact.version %}selected{% endif %}>{{ artifact.label }}</option>
                {% endfor %}
              </select>
              <div class="actions">
                <button type="submit" class="primary">更新対象に設定</button>
                <button type="button" id="clear-firmware-target">更新対象を解除</button>
              </div>
            </form>
          </section>

          <section class="panel">
            <h2>F/W更新履歴</h2>
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
            <h2>F/Wファイル管理</h2>
            <details open>
              <summary>firmware.bin を登録する</summary>
              <div class="detail-body">
                <form id="firmware-upload-form" enctype="multipart/form-data">
                  <div class="form-grid">
                    <div>
                      <label for="firmware-device-kind">デバイス種別</label>
                      <input id="firmware-device-kind" name="device_kind" type="text" value="{{ selected_device.device_kind if selected_device and selected_device.device_kind else 'WTR' }}" maxlength="3" readonly>
                    </div>
                    <div>
                      <label for="firmware-version">バージョン</label>
                      <input id="firmware-version" name="version" type="text" value="" readonly>
                    </div>
                    <div>
                      <label for="firmware-build-id">ビルド ID</label>
                      <input id="firmware-build-id" name="build_id" type="text" readonly>
                    </div>
                    <div>
                      <label for="firmware-rollout-state">配信状態</label>
                      <select id="firmware-rollout-state" name="rollout_state">
                        <option value="active">配信中</option>
                        <option value="paused">一時停止</option>
                        <option value="revoked">取り消し</option>
                      </select>
                    </div>
                  </div>
                  <label for="firmware-file">firmware.bin</label>
                  <input id="firmware-file" name="firmware" type="file" required>
                  <div id="firmware-manifest-summary" class="empty">firmware.bin を選択すると、埋め込みmanifestからデバイス種別・バージョン・ビルドIDを読み取ります。</div>
                  <div class="actions">
                    <button type="button" id="inspect-firmware-manifest">manifest再読み取り</button>
                    <label><input id="firmware-force" name="force" type="checkbox">強制更新</label>
                    <label><input id="firmware-allow-downgrade" name="allow_downgrade" type="checkbox">古いバージョンへの更新を許可</label>
                    <button type="submit" class="primary">アップロードして登録</button>
                  </div>
                </form>
              </div>
            </details>
            <details>
              <summary>登録済みファームウェア</summary>
              <div class="detail-body">
                <table>
                  <thead><tr><th>キー</th><th>バージョン</th><th>種別</th><th>ビルドID</th><th>Manifest</th><th>状態</th><th>サイズ</th><th>SHA-256</th><th>URL</th><th>更新日時</th></tr></thead>
                  <tbody>
                    {% for key, artifact in firmware_artifacts.items() %}
                    <tr>
                      <td>{{ key }}</td>
                      <td>{{ artifact.version }}</td>
                      <td>{{ artifact.device_kind }}</td>
                      <td>{{ artifact.build_id or '未取得' }}</td>
                      <td>{{ artifact.manifest_label }}</td>
                      <td>{{ artifact.rollout_state }}</td>
                      <td>{{ artifact.size }}</td>
                      <td>{{ artifact.sha256 }}</td>
                      <td><a href="{{ artifact.url }}">{{ artifact.url }}</a></td>
                      <td>{{ artifact.updated_at }}</td>
                    </tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>
            </details>
          </section>
            </section>

            <section id="tab-diagnostics" class="tab-panel" role="tabpanel" hidden>
          <section class="panel">
            <h2>履歴・診断</h2>
            <details open>
              <summary>機器状態の管理</summary>
              <div class="detail-body">
                <p>現在: <span class="badge {{ selected.state_class }}">{{ selected.state_label }}</span></p>
                <label for="approved-by">承認者</label>
                <input id="approved-by" type="text" value="operator">
                <div class="actions">
                  <button type="button" data-state-action="approve">承認する</button>
                  <button type="button" data-state-action="disable">停止する</button>
                  <button type="button" data-state-action="retire">廃止する</button>
                </div>
              </div>
            </details>

            <details>
              <summary>動作設定 JSON</summary>
              <div class="detail-body">
                <textarea id="runtime-config-json">{{ format_json(selected_device.config) }}</textarea>
                <div class="actions">
                  <button type="button" id="apply-runtime-json">JSON をフォームに反映</button>
                  <button type="button" id="save-runtime-json">JSON で保存</button>
                  <button type="button" id="save-push-runtime-json" class="primary">JSON で保存して device に送信</button>
                </div>
              </div>
            </details>

            <details>
              <summary>Status / OTA / MQTT raw履歴</summary>
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
          </div>
          {% endif %}
        </div>

        <script>
          const selectedDeviceId = {{ selected_device_id | tojson }};
          const demoMode = {{ demo_mode | tojson }};
          const chartEndpoint = selectedDeviceId ? ((demoMode ? "/demo/local/api/mqtt-devices/" : "/local/api/mqtt-devices/") + encodeURIComponent(selectedDeviceId) + "/charts") : null;
          const initialRuntimeConfig = {{ (selected_device.config if selected_device else {}) | tojson }};
          let plotlyLoadPromise = null;
          let pendingWorkCount = 0;
          let lastActionButton = null;
          let currentMosfetSwitches = [];

          document.addEventListener("click", (event) => {
            const button = event.target.closest("button");
            if (button) lastActionButton = button;
          }, true);

          function resultBox() {
            return document.getElementById("action-result");
          }

          function showResult(message, ok) {
            const box = resultBox();
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
          const tabAliases = { irrigation: "monitoring", config: "settings", maintenance: "diagnostics" };
          const requestedKey = tabAliases[requestedTab] || requestedTab || "overview";
          const requestedButton = detailTabButtons.find((button) => button.getAttribute("data-tab-key") === requestedKey);
          if (requestedButton) activateDetailTab(requestedButton.getAttribute("data-tab-target"), false);

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
                location: document.getElementById("metadata-location").value || null,
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

          function defaultMosfetSwitches() {
            return [
              { switch_id: "irr1", name: "灌水1系", enabled: true, role: "irrigation", terminal: "IRR1", channel_mask: 1, controlled_load: "", notes: "" },
              { switch_id: "irr2", name: "灌水2系", enabled: true, role: "irrigation", terminal: "IRR2", channel_mask: 2, controlled_load: "", notes: "" },
              { switch_id: "sensor_power", name: "RS485センサー電源", enabled: true, role: "sensor_power", terminal: "SENSOR_12V_SW", channel_mask: 0, controlled_load: "RS485 sensor 12V branch", notes: "" },
            ];
          }

          function normalizeMosfetSwitches(switches) {
            const source = Array.isArray(switches) ? switches : defaultMosfetSwitches();
            return source.slice(0, 16).map((sw, index) => ({
              switch_id: String(sw.switch_id || "sw" + (index + 1)).trim(),
              name: String(sw.name || sw.switch_id || "SW " + (index + 1)).trim(),
              enabled: sw.enabled !== false,
              role: String(sw.role || "").trim(),
              terminal: String(sw.terminal || "").trim(),
              channel_mask: Number.isInteger(sw.channel_mask) ? sw.channel_mask : 0,
              controlled_load: String(sw.controlled_load || "").trim(),
              notes: String(sw.notes || "").trim(),
            }));
          }

          function channelLabel(channelMask) {
            const names = currentMosfetSwitches
              .filter((sw) => sw.enabled !== false && Number.isInteger(sw.channel_mask) && sw.channel_mask > 0 && (channelMask & sw.channel_mask))
              .map((sw) => sw.name || sw.switch_id);
            if (names.length) return names.join("・");
            if (channelMask === 1) return "系統1";
            if (channelMask === 2) return "系統2";
            if (channelMask === 3) return "系統1・系統2";
            return "mask " + String(channelMask);
          }

          function scheduleChannelOptions(selectedValue) {
            const masks = [1, 2, 3];
            currentMosfetSwitches.forEach((sw) => {
              if (sw.enabled !== false && Number.isInteger(sw.channel_mask) && sw.channel_mask > 0 && !masks.includes(sw.channel_mask)) {
                masks.push(sw.channel_mask);
              }
            });
            if (Number.isInteger(selectedValue) && selectedValue > 0 && !masks.includes(selectedValue)) {
              masks.push(selectedValue);
            }
            return masks.map((mask) => ({ value: mask, label: channelLabel(mask) }));
          }

          function setScheduleChannelOptions(select, selectedValue) {
            if (!select) return;
            const value = Number.isInteger(selectedValue) && selectedValue > 0 ? selectedValue : Number(select.value || 1);
            select.innerHTML = "";
            scheduleChannelOptions(value).forEach((option) => {
              const element = document.createElement("option");
              element.value = String(option.value);
              element.textContent = option.label;
              select.appendChild(element);
            });
            select.value = String(value);
          }

          function refreshScheduleChannelOptions() {
            currentMosfetSwitches = collectMosfetSwitches();
            document.querySelectorAll("[data-schedule-channel]").forEach((select) => {
              setScheduleChannelOptions(select, Number(select.value || 1));
            });
          }

          function createMosfetSwitchRow(sw) {
            const row = document.createElement("div");
            row.className = "mosfet-switch-row";
            row.innerHTML = [
              '<label class="switch-row"><input data-mosfet-enabled type="checkbox">有効</label>',
              '<div><label>SW ID</label><input data-mosfet-id type="text" maxlength="32" required></div>',
              '<div><label>表示名</label><input data-mosfet-name type="text" maxlength="64" required></div>',
              '<div><label>役割</label><select data-mosfet-role><option value="irrigation">灌水</option><option value="sensor_power">センサー電源</option><option value="other">その他</option></select></div>',
              '<div><label>端子</label><input data-mosfet-terminal type="text" maxlength="32"></div>',
              '<div><label>制御対象</label><input data-mosfet-load type="text" maxlength="96"></div>',
              '<div><label>mask</label><input data-mosfet-mask type="number" min="0" max="4294967295" step="1"></div>',
              '<button type="button" class="icon-button" data-remove-mosfet-switch aria-label="SW を削除">－</button>',
            ].join("");
            row.querySelector("[data-mosfet-enabled]").checked = sw.enabled !== false;
            row.querySelector("[data-mosfet-id]").value = sw.switch_id || "";
            row.querySelector("[data-mosfet-name]").value = sw.name || "";
            row.querySelector("[data-mosfet-role]").value = ["irrigation", "sensor_power", "other"].includes(sw.role) ? sw.role : "other";
            row.querySelector("[data-mosfet-terminal]").value = sw.terminal || "";
            row.querySelector("[data-mosfet-load]").value = sw.controlled_load || "";
            row.querySelector("[data-mosfet-mask]").value = String(Number.isInteger(sw.channel_mask) ? sw.channel_mask : 0);
            row.querySelector("[data-remove-mosfet-switch]").addEventListener("click", () => {
              row.remove();
              refreshScheduleChannelOptions();
              refreshRuntimeConfigPreview();
            });
            row.querySelectorAll("input, select").forEach((input) => input.addEventListener("input", () => {
              refreshScheduleChannelOptions();
              refreshRuntimeConfigPreview();
            }));
            return row;
          }

          function renderMosfetSwitches(switches) {
            const editor = document.getElementById("mosfet-switch-editor");
            if (!editor) return;
            editor.innerHTML = "";
            currentMosfetSwitches = normalizeMosfetSwitches(switches);
            currentMosfetSwitches.forEach((sw) => editor.appendChild(createMosfetSwitchRow(sw)));
          }

          function collectMosfetSwitches() {
            const editor = document.getElementById("mosfet-switch-editor");
            if (!editor) return currentMosfetSwitches;
            return Array.from(editor.querySelectorAll(".mosfet-switch-row")).map((row) => ({
              switch_id: row.querySelector("[data-mosfet-id]").value.trim(),
              name: row.querySelector("[data-mosfet-name]").value.trim(),
              enabled: row.querySelector("[data-mosfet-enabled]").checked,
              role: row.querySelector("[data-mosfet-role]").value,
              terminal: row.querySelector("[data-mosfet-terminal]").value.trim(),
              channel_mask: Number(row.querySelector("[data-mosfet-mask]").value),
              controlled_load: row.querySelector("[data-mosfet-load]").value.trim(),
              notes: "",
            }));
          }

          function createScheduleRow(schedule) {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.innerHTML = [
              '<div><label>時刻</label><input data-schedule-time type="time" required></div>',
              '<div><label>灌水時間（秒）</label><input data-schedule-duration type="number" min="1" max="3600" step="1" required></div>',
              '<div><label>系統</label><select data-schedule-channel></select></div>',
              '<div><label>頻度</label><select data-schedule-frequency-mode><option value="daily">毎日</option><option value="interval">日にちごと</option><option value="weekdays">曜日指定</option></select></div>',
              '<div data-frequency-panel="interval"><label>間隔</label><input data-schedule-interval-days type="number" min="1" max="31" step="1"></div>',
              '<div data-frequency-panel="interval"><label>開始日</label><input data-schedule-start-date type="date"></div>',
              '<div data-frequency-panel="weekdays"><label>曜日</label><select data-schedule-weekdays multiple size="4"><option value="0">日</option><option value="1">月</option><option value="2">火</option><option value="3">水</option><option value="4">木</option><option value="5">金</option><option value="6">土</option></select></div>',
              '<button type="button" class="icon-button" data-remove-schedule aria-label="予約を削除">－</button>',
            ].join("");
            const frequency = scheduleFrequency(schedule || {});
            row.querySelector("[data-schedule-time]").value = scheduleToTime(schedule || {});
            row.querySelector("[data-schedule-duration]").value = String((schedule || {}).duration_sec || 1);
            setScheduleChannelOptions(row.querySelector("[data-schedule-channel]"), Number((schedule || {}).channel_mask || 1));
            row.querySelector("[data-schedule-frequency-mode]").value = frequency.mode;
            row.querySelector("[data-schedule-interval-days]").value = String(frequency.interval_days || 2);
            row.querySelector("[data-schedule-start-date]").value = frequency.start_date || todayDateString();
            Array.from(row.querySelector("[data-schedule-weekdays]").options).forEach((option) => {
              option.selected = frequency.weekdays.includes(Number(option.value));
            });
            setFrequencyControlsVisible(row);
            row.querySelector("[data-remove-schedule]").addEventListener("click", () => {
              if (document.querySelectorAll("#schedule-editor .schedule-row").length <= 1) {
                showResult("灌水予約は最低 1 件必要です", false);
                return;
              }
              row.remove();
              refreshRuntimeConfigPreview();
            });
            row.querySelector("[data-schedule-frequency-mode]").addEventListener("input", () => setFrequencyControlsVisible(row));
            row.querySelectorAll("input, select").forEach((input) => input.addEventListener("input", refreshRuntimeConfigPreview));
            return row;
          }

          function renderRuntimeConfigForm(config) {
            config = config || {};
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
            const debugLogOnWake = document.getElementById("debug-log-on-wake");
            if (debugLogOnWake) debugLogOnWake.checked = Boolean(config.debug_log_on_wake);
            const otaCheckInterval = document.getElementById("ota-check-interval");
            if (otaCheckInterval) otaCheckInterval.value = String(Number.isInteger(config.ota_check_interval_sec) ? config.ota_check_interval_sec : 21600);

            const wateringPattern = config.watering_pattern || {};
            const wateringPatternEnabled = document.getElementById("watering-pattern-enabled");
            if (wateringPatternEnabled) wateringPatternEnabled.checked = Boolean(wateringPattern.enabled);
            const wateringPatternOnSec = document.getElementById("watering-pattern-on-sec");
            if (wateringPatternOnSec) wateringPatternOnSec.value = String(Number.isInteger(wateringPattern.on_sec) ? wateringPattern.on_sec : 0);
            const wateringPatternOffSec = document.getElementById("watering-pattern-off-sec");
            if (wateringPatternOffSec) wateringPatternOffSec.value = String(Number.isInteger(wateringPattern.off_sec) ? wateringPattern.off_sec : 0);
            const wateringPatternRepeatCount = document.getElementById("watering-pattern-repeat-count");
            if (wateringPatternRepeatCount) wateringPatternRepeatCount.value = String(Number.isInteger(wateringPattern.repeat_count) ? wateringPattern.repeat_count : 0);

            const soilCalibration = config.soil_calibration || {};
            const soilCalibrationMode = document.getElementById("soil-calibration-mode");
            if (soilCalibrationMode) soilCalibrationMode.value = typeof soilCalibration.mode === "string" ? soilCalibration.mode : "normal";
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

            renderMosfetSwitches(config.mosfet_switches);

            const editor = document.getElementById("schedule-editor");
            if (editor) {
              editor.innerHTML = "";
              const schedules = Array.isArray(config.schedules) && config.schedules.length ? config.schedules : [{ hour: 6, minute: 30, duration_sec: 1, channel_mask: 1, frequency: { mode: "daily" } }];
              schedules.slice(0, 8).forEach((schedule) => editor.appendChild(createScheduleRow(schedule)));
            }
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
                hour: Number(parts[0]),
                minute: Number(parts[1]),
                duration_sec: Number(row.querySelector("[data-schedule-duration]").value),
                channel_mask: Number(row.querySelector("[data-schedule-channel]").value),
                frequency,
              };
            });
            if (schedules.length < 1 || schedules.length > 8) throw new Error("灌水予約は 1〜8 件にしてください");
            const wateringPattern = {
              enabled: document.getElementById("watering-pattern-enabled").checked,
              on_sec: Number(document.getElementById("watering-pattern-on-sec").value),
              off_sec: Number(document.getElementById("watering-pattern-off-sec").value),
              repeat_count: Number(document.getElementById("watering-pattern-repeat-count").value),
            };
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
            return {
              ntp_server: document.getElementById("ntp-server").value.trim() || "pool.ntp.org",
              timezone_offset_sec: timezoneOffset,
              moisture_threshold: threshold,
              force_watering: document.getElementById("force-watering").checked,
              debug_log_on_wake: document.getElementById("debug-log-on-wake").checked,
              ota_check_interval_sec: otaCheckInterval,
              watering_pattern: wateringPattern,
              soil_calibration: soilCalibration,
              env_sensors: envSensors,
              env_calibration: envCalibration,
              mosfet_switches: mosfetSwitches,
              schedules,
            };
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
            if (textarea) textarea.value = JSON.stringify(config, null, 2);
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
          }

          async function saveRuntimeConfig(push, source) {
            let config;
            if (source === "json") {
              const textarea = document.getElementById("runtime-config-json");
              try {
                config = JSON.parse(textarea.value);
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
            renderRuntimeConfigForm(config);
            const textarea = document.getElementById("runtime-config-json");
            if (textarea) textarea.value = JSON.stringify(config, null, 2);
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
            renderRuntimeConfigForm(initialRuntimeConfig);
            runtimeConfigForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              await saveRuntimeConfig(false);
            });
            runtimeConfigForm.querySelectorAll("input, select").forEach((input) => input.addEventListener("input", refreshRuntimeConfigPreview));
          }
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
            });
          }
          const addMosfetSwitchButton = document.getElementById("add-mosfet-switch");
          if (addMosfetSwitchButton) {
            addMosfetSwitchButton.addEventListener("click", () => {
              const editor = document.getElementById("mosfet-switch-editor");
              if (!editor) return;
              if (editor.querySelectorAll(".mosfet-switch-row").length >= 16) {
                showResult("MOSFET SW は最大 16 件です", false);
                return;
              }
              const nextIndex = editor.querySelectorAll(".mosfet-switch-row").length + 1;
              editor.appendChild(createMosfetSwitchRow({
                switch_id: "sw" + nextIndex,
                name: "SW " + nextIndex,
                enabled: true,
                role: "other",
                terminal: "",
                channel_mask: 0,
                controlled_load: "",
                notes: "",
              }));
              refreshScheduleChannelOptions();
              refreshRuntimeConfigPreview();
            });
          }
          const applyRuntimeJsonButton = document.getElementById("apply-runtime-json");
          if (applyRuntimeJsonButton) {
            applyRuntimeJsonButton.addEventListener("click", () => {
              try {
                renderRuntimeConfigForm(JSON.parse(document.getElementById("runtime-config-json").value));
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

            function firmwareFileKey(file) {
              return file ? [file.name, file.size, file.lastModified].join(":") : "";
            }

            function setFirmwareManifestSummary(message, ok) {
              if (!firmwareManifestSummary) return;
              firmwareManifestSummary.textContent = message;
              firmwareManifestSummary.classList.toggle("ok", Boolean(ok));
              firmwareManifestSummary.classList.toggle("error", ok === false);
            }

            async function inspectSelectedFirmware() {
              const file = firmwareFileInput.files[0];
              if (!file) {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                setFirmwareManifestSummary("firmware.bin を選択してください", false);
                return null;
              }
              const currentKey = firmwareFileKey(file);
              if (inspectedFirmwareManifest && inspectedFirmwareFileKey === currentKey) {
                return inspectedFirmwareManifest;
              }
              const formData = new FormData();
              formData.append("firmware", file);
              try {
                const manifest = await requestJson(
                  "/local/api/firmware-artifacts/inspect",
                  { method: "POST", body: formData },
                  "firmware.bin のmanifestを読み取っています...",
                );
                inspectedFirmwareManifest = manifest;
                inspectedFirmwareFileKey = currentKey;
                document.getElementById("firmware-device-kind").value = manifest.device_kind || "";
                document.getElementById("firmware-version").value = manifest.version || "";
                document.getElementById("firmware-build-id").value = manifest.build_id || "";
                setFirmwareManifestSummary(
                  "読み取り済み: " +
                    "device_kind=" + (manifest.device_kind || "-") +
                    " / version=" + (manifest.version || "-") +
                    " / build_id=" + (manifest.build_id || "-") +
                    " / target=" + (manifest.target || "-") +
                    " / project=" + (manifest.project || "-"),
                  true,
                );
                return manifest;
              } catch (error) {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                document.getElementById("firmware-version").value = "";
                document.getElementById("firmware-build-id").value = "";
                setFirmwareManifestSummary(error.message, false);
                throw error;
              }
            }

            if (firmwareFileInput) {
              firmwareFileInput.addEventListener("click", () => {
                inspectedFirmwareManifest = null;
                inspectedFirmwareFileKey = "";
                firmwareFileInput.value = "";
              });
              firmwareFileInput.addEventListener("change", () => {
                inspectSelectedFirmware().catch((error) => showResult(error.message, false));
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
                showResult("firmware.bin を選択してください", false);
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
                showResult("firmware.bin のmanifestからデバイス種別とバージョンを読み取れません", false);
                return;
              }
              const formData = new FormData();
              formData.append("firmware", file);
              const buildId = manifest.build_id || "";
              if (buildId) formData.append("build_id", buildId);
              formData.append("rollout_state", document.getElementById("firmware-rollout-state").value);
              formData.append("force", document.getElementById("firmware-force").checked ? "true" : "false");
              formData.append("allow_downgrade", document.getElementById("firmware-allow-downgrade").checked ? "true" : "false");
              try {
                await requestJson(
                  "/local/api/firmware-artifacts/" + encodeURIComponent(deviceKind) + "/" + encodeURIComponent(version) + "/upload",
                  { method: "POST", body: formData },
                  "firmware.bin をアップロードしています...",
                );
                showResult("firmware.bin を登録しました", true);
                reloadSoon();
              } catch (error) {
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
    )


# ==========================================
# Field pages
# ==========================================
@app.route("/settings", methods=["GET", "POST"])
@app.route("/settings/ai", methods=["GET", "POST"])
def hub_settings_page():
    current = dict(setting().get("ai") or {})
    saved = False
    if request.method == "POST":
        next_settings = {
            **current,
            "enabled": request.form.get("enabled") == "on",
            "text_analyze_base_url": request.form.get("text_analyze_base_url", "").strip(),
            "text_analyze_model": request.form.get("text_analyze_model", "").strip(),
            "image_analyze_base_url": request.form.get("image_analyze_base_url", "").strip(),
            "image_analyze_model": request.form.get("image_analyze_model", "").strip(),
        }
        for key in ("text_analyze_api_key", "image_analyze_api_key"):
            supplied = request.form.get(key, "").strip()
            if supplied:
                next_settings[key] = supplied
        setting().set("ai", next_settings)
        ai_content_service().reload_settings()
        current = next_settings
        saved = True
    visible = {
        **current,
        "text_analyze_api_key": "",
        "image_analyze_api_key": "",
        "text_key_configured": bool(current.get("text_analyze_api_key")),
        "image_key_configured": bool(current.get("image_analyze_api_key")),
    }
    return render_template("hub_settings.html", ai=visible, saved=saved)


@app.route("/local/api/settings/ai/test", methods=["POST"])
def test_hub_ai_settings_api():
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    channel = str(request_body.get("channel") or "text")
    if channel not in {"text", "image"}:
        return jsonify({"error": "channel must be text or image"}), 400
    try:
        result = ai_content_service().test_connection(
            channel,
            {
                "api_key": str(request_body.get("api_key") or "").strip(),
                "base_url": str(request_body.get("base_url") or "").strip(),
                "model": str(request_body.get("model") or "").strip(),
            },
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result)


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
    return render_template("field_layout.html", field=field)


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
        layout = field_layout_repository().upsert(field_id, request_body, field_name=field.get("name", ""))
    except FieldLayoutConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except FieldLayoutValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(layout)


@app.route("/local/api/fields/<field_id>/layout/devices", methods=["GET"])
def list_field_layout_devices_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404

    records = device_config_service().get_all_records()
    assignments = _layout_device_assignments()
    field_device_ids = set(field.get("device_ids") or []) | set(field.get("camera_device_ids") or [])
    device_ids = sorted(set(records) | field_device_ids)
    devices = []
    for device_id in device_ids:
        assigned_field_id = assignments.get(device_id, "")
        if assigned_field_id and assigned_field_id != field_id:
            continue
        record = records.get(device_id) or {}
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        last_status = record.get("last_status") if isinstance(record.get("last_status"), dict) else {}
        resources = [
            {
                "resource_type": "mosfet_switch",
                "resource_id": switch.get("switch_id", ""),
                "name": switch.get("name") or switch.get("switch_id") or "MOSFET SW",
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
            }
        )
    return jsonify(devices)


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
    if device_kind in {"WTR", "WRS"}:
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


@app.route("/local/api/fields/<field_id>/plantings", methods=["GET"])
def list_field_plantings_api(field_id):
    field = field_repository().get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404
    today = request.args.get("today", "").strip() or None
    try:
        return jsonify(plant_management_repository().field_bundle(field_id, today=today))
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
        "cultivation_method": request_body.get("cultivation_method") or (field.get("cultivation_context") or {}).get("cultivation_method", ""),
    }
    planting_data["conditions"] = {
        **(request_body.get("conditions") if isinstance(request_body.get("conditions"), dict) else {}),
        "region": "",
    }
    try:
        planting = repository.create_planting(field_id, planting_data)
        context = _build_plant_generation_context(field, layout, space, placement, planting)
        context["planning"] = {
            "start_date": planting["planted_on"],
            "horizon_months": 12,
            "notes": str(request_body.get("planning_notes") or "")[:2000],
        }
        guidance = repository.guidance_examples(planting["crop_name"])
        generated = ai_content_service().generate_plant_calendar(context, guidance_examples=guidance)
        planting = repository.update_planting(planting["id"], {"growth_targets": generated.get("growth_targets") or {}})
        calendar = repository.create_calendar(
            planting["id"],
            generated["actions"],
            generated.get("generation"),
            care_profile=generated.get("care_profile"),
            task_rules=generated.get("task_rules"),
        )
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"planting": repository.get_planting(planting["id"]), "calendar": calendar}), 201


@app.route("/local/api/plantings/<planting_id>", methods=["PATCH"])
def update_planting_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        planting = plant_management_repository().update_planting(planting_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(planting)


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
    context = _build_plant_generation_context(field, layout, space, placement, planting)
    context["planning"] = {
        "start_date": str(request_body.get("start_date") or date.today().isoformat()),
        "horizon_months": 12,
        "notes": str(request_body.get("planning_notes") or "")[:2000],
    }
    try:
        guidance = repository.guidance_examples(planting["crop_name"])
        generated = ai_content_service().generate_plant_calendar(context, guidance_examples=guidance)
        repository.update_planting(planting_id, {"growth_targets": generated.get("growth_targets") or planting.get("growth_targets") or {}})
        calendar = repository.replace_calendar(
            planting_id,
            generated["actions"],
            generated.get("generation"),
            care_profile=generated.get("care_profile"),
            task_rules=generated.get("task_rules"),
        )
    except (PlantManagementNotFoundError, PlantManagementValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"planting": repository.get_planting(planting_id), "calendar": calendar})


@app.route("/local/api/plantings/<planting_id>/calendar/actions", methods=["POST"])
def add_plant_calendar_action_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        action = plant_management_repository().add_action(planting_id, request_body)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(action), 201


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>", methods=["DELETE"])
def delete_plant_calendar_action_api(planting_id, action_id):
    try:
        plant_management_repository().delete_action(planting_id, action_id)
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return "", 204


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>", methods=["PATCH"])
def update_plant_calendar_action_api(planting_id, action_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    use_as_guidance = bool(request_body.pop("use_as_guidance", False))
    try:
        action = plant_management_repository().update_action(
            planting_id,
            action_id,
            request_body,
            use_as_guidance=use_as_guidance,
        )
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except PlantManagementValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(action)


@app.route("/local/api/plantings/<planting_id>/calendar/actions/<action_id>/complete", methods=["POST"])
def complete_plant_calendar_action_api(planting_id, action_id):  # noqa: PLR0911
    request_body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be an object"}), 400
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    if planting is None:
        return jsonify({"error": "planting not found"}), 404
    calendar_record = repository.get_calendar(planting_id)
    completed_action = next((action for action in (calendar_record or {}).get("actions", []) if action.get("id") == action_id), None)
    if not calendar_record or completed_action is None:
        return jsonify({"error": "calendar action not found"}), 404
    try:
        rating = _record_rating(request_body.get("rating"))
        performed_on = date.fromisoformat(str(request_body.get("performed_on") or "")).isoformat()
        attachments = field_record_media_service().upload_images(
            planting["field_id"],
            performed_on,
            request.files.getlist("images"),
        )
        work_log = repository.complete_action(
            planting_id,
            action_id,
            performed_on,
            request_body.get("note", ""),
            rating=rating,
            attachments=attachments,
        )
        field_repository().add_event(
            work_log["field_id"],
            {
                "event_type": _plant_action_event_type(work_log["action_type"]),
                "occurred_at": work_log["performed_on"],
                "title": work_log["title"],
                "description": work_log["note"],
                "rating": work_log["rating"],
                "attachments": work_log["attachments"],
                "source_work_log_id": work_log["id"],
                "tags": ["plant-calendar", work_log["action_type"], work_log["crop_name"]],
            },
        )
    except ValueError as exc:
        return jsonify({"error": str(exc) or "performed_on must be YYYY-MM-DD"}), 400
    except PlantManagementNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except (PlantManagementValidationError, FieldValidationError, FieldRecordMediaValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except FieldRecordMediaStorageError as exc:
        return jsonify({"error": str(exc)}), 502

    follow_up = {"actions": [], "decision_summary": "次回を自動生成しない作業です。", "source": "rule"}
    appended_actions = []
    task_rule = next(
        (rule for rule in calendar_record.get("task_rules", []) if rule.get("rule_id") == completed_action.get("rule_id")),
        None,
    )
    if task_rule:
        current_calendar = repository.get_calendar(planting_id) or {}
        follow_up_field = field_repository().get(planting["field_id"]) or {}
        follow_up_context = {
            "planting": repository.get_planting(planting_id) or planting,
            "field": {
                "id": follow_up_field.get("id"),
                "location": follow_up_field.get("location", {}),
            },
            "care_profile": current_calendar.get("care_profile", {}),
            "growth_targets": planting.get("growth_targets", {}),
            "task_rule": task_rule,
            "completed_action": completed_action,
            "completion_event": work_log,
            "planned_actions": [action for action in current_calendar.get("actions", []) if action.get("status") == "planned"],
            "recent_work_logs": repository.recent_work_logs(planting_id, limit=12),
        }
        follow_up = ai_content_service().generate_follow_up_tasks(follow_up_context)
        try:
            appended_actions = repository.append_generated_actions(planting_id, follow_up.get("actions") or [])
        except PlantManagementValidationError:
            app.logger.exception("Failed to append generated follow-up tasks")
    return jsonify({**work_log, "follow_up": {**follow_up, "actions": appended_actions}}), 201


@app.route("/local/api/plantings/<planting_id>/questions", methods=["POST"])
def ask_plant_question_api(planting_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    question = str(request_body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    repository = plant_management_repository()
    planting = repository.get_planting(planting_id)
    if planting is None:
        return jsonify({"error": "planting not found"}), 404
    calendar = repository.get_calendar(planting_id)
    field = field_repository().get(planting["field_id"])
    context = {
        "field": field or {},
        "planting": planting,
        "calendar": calendar or {},
        "suggestions": repository.list_suggestions(planting["field_id"]),
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
        if request.form.get("event_type") == "daily_record" and not any((record_values, request.form.get("description", "").strip(), rating, attachments)):
            raise FieldValidationError("記録項目、メモ、評価、画像のいずれかを入力してください")
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
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
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
            "soil_moisture_percent": _field_range_from_form(form, "target_soil_moisture"),
            "soil_ec_us_cm": _field_range_from_form(form, "target_soil_ec"),
            "soil_ph": _field_range_from_form(form, "target_soil_ph"),
            "air_humidity_percent": _field_range_from_form(form, "target_air_humidity"),
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


def _build_plant_generation_context(field, layout, space, placement, planting):
    return {
        "planting": planting,
        "placement": {
            "id": placement.get("id"),
            "name": placement.get("name"),
            "preset": placement.get("preset"),
            "space_id": space.get("id"),
            "space_name": space.get("name"),
            "space_type": space.get("space_type"),
            "grid_cell_size_m": (space.get("grid") or {}).get("cell_size_m"),
        },
        "field": {
            "id": field.get("id"),
            "name": field.get("name"),
            "location": field.get("location") or {},
            "crop_profile": field.get("crop_profile") or {},
            "cultivation_context": field.get("cultivation_context") or {},
            "growth_targets": field.get("growth_targets") or {},
            "control_policy": field.get("control_policy") or {},
        },
        "layout": {
            "space_type": space.get("space_type"),
            "root_space_id": layout.get("root_space_id"),
        },
    }


def _plant_action_event_type(action_type):
    return {
        "fertilization": "fertilizer",
        "pest_control": "pest",
        "harvest": "harvest",
        "watering": "watering",
    }.get(action_type, "other")


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
    item["list_summary"] = {
        "crop_labels": crop_labels,
        "placement_count": len(placements),
        "planting_count": len(active_plantings),
        "device_count": len({(placement.get("binding") or {}).get("device_id") for placement in placements} - {None, ""}),
        "record_count": len(field.get("events") or []) + len(plant_bundle.get("work_logs") or []),
    }
    return item


def _build_field_context(
    field: dict,
    compare_date: str = "",
    record_month: str = "",
    *,
    include_automatic_measurements: bool = True,
):  # noqa: PLR0915
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
        _field_automatic_record_measurements(active_measurement_devices, placement_rows, record_month)
        if include_automatic_measurements
        else []
    )
    active_plantings = _build_active_planting_views(active_plantings, plant_bundle, automatic_record_measurements, layout)

    recent_status_events = sorted(recent_status_events, key=lambda item: item.get("received_at") or "", reverse=True)[:40]
    field_events = sorted(list(field.get("events") or []), key=lambda item: item.get("occurred_at") or item.get("created_at") or "", reverse=True)
    timeline = _build_field_timeline(recent_status_events, field_events, field.get("notes") or [])
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
        "timeline": timeline[:80],
        "recent_notes": list(field.get("notes") or [])[-20:],
        "recent_images": recent_images[:12],
        "compare_date": compare_day.strftime("%Y-%m-%d"),
        "image_compare": recent_images[:2],
        "image_compare_groups": image_compare_groups,
        "soil_moisture_chart": (
            _build_field_soil_moisture_chart(statuses_for_chart, field_events, include_plotlyjs=False, deferred=True)
            if statuses_for_chart
            else ""
        ),
        "watering_chart": (
            _build_watering_trend_chart(statuses_for_chart, include_plotlyjs=False, deferred=True)
            if statuses_for_chart
            else ""
        ),
        "monitoring_scopes": _build_monitoring_scopes(placement_rows, latest_sensor_values),
        "layout": layout,
        "layout_preview": _build_layout_preview(layout, active_plantings),
        "installation_tree": _build_installation_tree(layout, device_records, active_plantings),
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
        for device_id in {
            row.get("device_id")
            for row in placement_rows
            if row.get("device_role") != "camera"
        }
        - {None, ""}
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
    return {device_id: record for device_id in relevant_device_ids - {None, ""} if (record := config_service.find_record(device_id)) is not None}


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


def _build_installation_tree(layout: dict, device_records: dict, active_plantings: list):
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
            if device_id:
                record = device_records.get(device_id) or {}
                detail_parts.append(record.get("name") or device_id)
            target_labels = [placement_names[target_id] for target_id in binding.get("target_placement_ids", []) if target_id in placement_names]
            watering_source_names = watering_sources_by_target.get(placement.get("id"), [])
            if preset in LAYOUT_CULTIVATION_PRESETS:
                relation = f"潅水: {'、'.join(watering_source_names)}" if watering_source_names else "手動潅水"
                relation_kind = "watering" if watering_source_names else "manual"
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
                }
            )

            resource_type = binding.get("resource_type") or "device"
            if device_id and resource_type != "device":
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
                return switch.get("name") or resource_id or "MOSFET SW"
        return resource_id or "MOSFET SW"
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


def _build_layout_preview(layout: dict, active_plantings: list):
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
    preset_by_placement = {
        placement.get("id"): placement.get("preset")
        for space in layout.get("spaces", [])
        for placement in space.get("placements", [])
    }
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
            if log.get("planting_id") != planting.get("id"):
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
    if device_kind in {"WTR", "WRS"}:
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
        "air_humidity_percent",
        "par_umol_m2_s",
        "solar_radiation_w_m2",
        "battery_v",
        "rssi",
        "threshold",
    ):
        if payload.get(key) is not None:
            values[key] = payload.get(key)
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
        "scope_label": (placement or {}).get("scope_label"),
        "target_placement_ids": (placement or {}).get("target_placement_ids") or [],
        "crop_name": (placement or {}).get("crop_name"),
        "area": (placement or {}).get("area"),
        "received_at": (record or {}).get("last_status_at"),
        "values": values,
    }


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
        parts.append("status受信")
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
    except DeviceConfigValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(result)


@app.route("/local/api/device-configs/<device_id>/push", methods=["POST"])
def push_device_config(device_id):
    try:
        published = device_config_service().publish_push(device_id)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(published)


@app.route("/local/api/mqtt-devices", methods=["GET"])
def list_mqtt_devices():
    return jsonify(device_config_service().get_all_records())


@app.route("/local/api/mqtt-devices/<device_id>", methods=["GET"])
def get_mqtt_device(device_id):
    record = device_config_service().get_record(device_id)
    if record is None:
        return jsonify({"error": "device not found"}), 404
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>", methods=["PATCH"])
def update_mqtt_device_metadata(device_id):
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    try:
        record = device_config_service().update_metadata(device_id, request_body)
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>/approve", methods=["POST"])
def approve_mqtt_device(device_id):
    request_body = request.get_json(silent=True) or {}
    try:
        record = device_config_service().set_state(device_id, "active", approved_by=request_body.get("approved_by"))
    except DeviceRecordValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(record)


@app.route("/local/api/mqtt-devices/<device_id>/disable", methods=["POST"])
def disable_mqtt_device(device_id):
    return jsonify(device_config_service().set_state(device_id, "disabled"))


@app.route("/local/api/mqtt-devices/<device_id>/retire", methods=["POST"])
def retire_mqtt_device(device_id):
    return jsonify(device_config_service().set_state(device_id, "retired"))


@app.route("/local/api/mqtt-devices/<device_id>/runtime-config", methods=["GET"])
def get_mqtt_device_runtime_config(device_id):
    return jsonify(device_config_service().get_config(device_id))


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
    if device_config_service().get_record(device_id) is None:
        return jsonify({"error": "device not found"}), 404
    statuses = device_config_service().list_statuses(device_id, limit=MQTT_ADMIN_STATUS_HISTORY_LIMIT)
    return jsonify(_build_mqtt_device_chart_payload(statuses))


@app.route("/demo/local/api/mqtt-devices/<device_id>/charts", methods=["GET"])
def get_demo_mqtt_device_charts(device_id):
    demo_data = _demo_mqtt_admin_page_data(device_id)
    if demo_data["selected_device_id"] != device_id:
        return jsonify({"error": "device not found"}), 404
    return jsonify(_build_mqtt_device_chart_payload(demo_data["selected_statuses"]))


def _build_mqtt_device_chart_payload(statuses):
    watering_chart = _build_watering_trend_chart(statuses, include_plotlyjs=False)
    return {
        "watering": watering_chart,
        "soil_moisture": _build_soil_moisture_chart(statuses, include_plotlyjs=False),
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
        ),
        "soil_ec": _build_metric_trend_chart(
            statuses,
            aliases=("soil_ec_us_cm",),
            title="土壌EC推移",
            unit="uS/cm",
            color="#7c3aed",
            div_id="soil-ec-chart",
        ),
        "soil_ph": _build_metric_trend_chart(
            statuses,
            aliases=("soil_ph",),
            title="土壌pH推移",
            unit="",
            color="#0f766e",
            div_id="soil-ph-chart",
            y_range=(0, 14),
        ),
        "par": _build_metric_trend_chart(
            statuses,
            aliases=("par_umol_m2_s",),
            title="PAR推移",
            unit="umol/m2/s",
            color="#ca8a04",
            div_id="par-chart",
        ),
    }


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
    uploaded_file = request.files.get("firmware") or request.files.get("file")
    firmware_binary = uploaded_file.read() if uploaded_file is not None else request.get_data()
    if not firmware_binary:
        return jsonify({"error": "firmware binary must not be empty"}), 400

    try:
        metadata = extract_firmware_manifest(firmware_binary)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(metadata)


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
    uploaded_file = request.files.get("firmware") or request.files.get("file")
    firmware_binary = uploaded_file.read() if uploaded_file is not None else request.get_data()
    if not firmware_binary:
        return jsonify({"error": "firmware binary must not be empty"}), 400

    try:
        metadata = _firmware_upload_metadata()
        artifact = ota_update_service().upsert_firmware_binary(device_kind, version, firmware_binary, metadata=metadata)
    except FirmwareArtifactValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(artifact), 201


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
    limit = _request_limit(default=48, maximum=500)
    start_at, end_at, date_error = _camera_image_date_range(date_value)
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


@app.route("/local/api/camera-images/<path:image_path>", methods=["GET"])
def get_camera_image(image_path):
    frame_path = timelapse_media_service().resolve_frame_path(image_path)
    if frame_path is None:
        return jsonify({"error": "no image"}), 404
    return send_file(frame_path, mimetype="image/jpeg")


def initialize_web_server():
    """Prepare the local Turso replica before accepting HTTP requests."""
    sensor_measurement_repository()


def flask_run():
    initialize_web_server()
    http_settings = setting().get("http") or {}
    app.run(host=http_settings.get("host", "0.0.0.0"), port=int(http_settings.get("port", 39151)))


def _request_limit(default: int = 100, maximum: int = 1000):
    try:
        limit = int(request.args.get("limit", str(default)))
    except ValueError:
        return default
    return max(1, min(limit, maximum))


def _camera_image_date_range(date_value: str):
    if not date_value:
        return None, None, None
    try:
        target_date = datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return None, None, "date must be YYYY-MM-DD"
    start_at = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_at = start_at + timedelta(days=1) - timedelta(microseconds=1)
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
