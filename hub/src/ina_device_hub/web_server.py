import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from html import escape
from pathlib import Path

import plotly
from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, send_file
from plotly import graph_objs as go
from plotly.io import to_html

from ina_device_hub.agri_action_service import METRIC_LABELS, build_action_candidates
from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.device_config_repository import DeviceConfigValidationError, DeviceRecordValidationError
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.device_event_log import list_device_events
from ina_device_hub.field_repository import FieldValidationError, field_repository
from ina_device_hub.location_repository import location_repository
from ina_device_hub.ota_update_service import FirmwareArtifactValidationError, extract_firmware_manifest, ota_update_service
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.sensor_measurement_repository import sensor_measurement_repository
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
    devices = sensor_device_repository().get_all()
    locations = location_repository().get_all()
    cameras = camera_connector().camera_device_repository.get_all()
    template = """
    <html>
      <body>
        <h1>INA Device Hub</h1>
        <h2>Devices</h2>
        <p><a href="/mqtt-devices">MQTT Devices</a></p>
        <p><a href="/fields">Fields</a></p>
        <ul>
          {% for device_id, info in devices.items() %}
          <li>
            <a href="/devices/{{ info.id }}">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
        <h2>Cameras</h2>
        <ul>
          {% for device_id, info in cameras.items() %}
          <li>
            <a href="/camera/{{ info.id }}/preview">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
        <h2>Locations</h2>
        <button type="button" onclick="location.href='/locations'">List</button>
        <button type="button" onclick="location.href='/locations/add'">Add</button>
        <ul>
          {% for location, info in locations.items() %}
          <li>
            <a href="/locations/{{ info.id }}">{{ info.name }}</a>
          </li>
          {% endfor %}
        </ul>
      </body>
    </html>
    """

    return render_template_string(template, devices=devices, locations=locations, cameras=cameras)


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
    return {
        "devices": [
            _build_device_summary(device_id, record, now) for device_id, record in sorted(devices.items(), key=lambda item: _device_sort_key(item[0], item[1]))
        ],
        "selected": _build_selected_device_view(selected_device_id, selected_device, selected_statuses, selected_ota_statuses, now)
        if selected_device
        else None,
    }


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
    return {
        "id": device_id,
        "title": record.get("name") or device_id,
        "location": record.get("location") or "場所未設定",
        "memo": record.get("memo") or "",
        "kind_label": _device_kind_label(record.get("device_kind")),
        "state_label": _device_state_label(record.get("state")),
        "state_class": _device_state_class(record.get("state")),
        "watering": _watering_state(payload),
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
        "schedules": _format_schedules_for_ui(config.get("schedules") or []),
        "config_summary": _format_config_summary(config),
        "watering_history": _build_watering_history(statuses),
        "wake_history": _build_wake_history(statuses),
        "ota_history": _build_ota_history(ota_statuses),
    }


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


def _build_watering_trend_chart(statuses, include_plotlyjs=False):
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
    return _plotly_div(fig, "watering-trend-chart", include_plotlyjs=include_plotlyjs)


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
        soil_moisture = payload.get("last_soil_moisture")
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


def _plotly_div(fig, div_id, include_plotlyjs=False):
    return to_html(
        fig,
        full_html=False,
        include_plotlyjs=include_plotlyjs,
        div_id=div_id,
        config={"displaylogo": False, "responsive": True},
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
    if device_kind == "WTR":
        return "水やり機"
    if device_kind == "WRS":
        return "RS485全部入り水やり機"
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


def _format_schedules_for_ui(schedules):
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
                "channel": _format_channel_mask(schedule.get("channel_mask")),
            }
        )
    return formatted


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
          .schedule-editor { display: grid; gap: 10px; }
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
          .icon-button { min-width: 38px; }
          .chart-card { display: grid; gap: 10px; }
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
            .section-grid { grid-template-columns: 1fr; }
            .tile-metrics { grid-template-columns: 1fr; }
            .list-row { grid-template-columns: 1fr; }
            .schedule-row { grid-template-columns: 1fr; }
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
              <h1>Hub 管理パネル</h1>
              <p class="lead">水やり機の稼働、灌水、土壌水分、起動履歴を確認します。</p>
            </div>
            <nav class="nav" aria-label="管理リンク">
              <a href="/">ホーム</a>
              <a href="/demo/mqtt-devices">UI デモ</a>
              <a href="/local/api/mqtt-devices">デバイス API</a>
              <a href="/local/api/mqtt-events">イベント API</a>
              <a href="/local/api/mqtt-connections">接続 API</a>
              <a href="/local/api/firmware-artifacts">ファームウェア API</a>
            </nav>
          </div>
          {% if demo_mode %}
          <div class="notice"><strong>デモデータ表示中</strong> 操作は保存されません。UI/UX 確認専用です。</div>
          {% endif %}
          {% if is_detail_page %}
          <div id="action-result" class="result">{{ "デモモードです。操作しても保存されません。" if demo_mode else "操作結果がここに表示されます。" }}</div>
          <div class="back-link"><a href="{{ list_path }}">水やり機一覧へ戻る</a></div>
          <div class="quick-actions" aria-label="詳細ページ内の操作">
            <a href="#ota-target" class="primary">OTA 更新対象</a>
            <a href="#firmware-maintenance">ファームウェア保守</a>
          </div>
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
            <h2>{{ selected.title }}</h2>
            <p class="lead">{{ selected.kind_label }} / {{ selected.location }} / {{ selected.id }}</p>
            {% if selected.memo %}<p>{{ selected.memo }}</p>{% endif %}
            <div class="metrics">
              <div class="metric">
                <span class="label">灌水</span>
                <span class="value"><span class="badge {{ selected.watering.class }}">{{ selected.watering.label }}</span></span>
                <div class="hint">最後の status から判断</div>
              </div>
              <div class="metric">
                <span class="label">土壌水分</span>
                <span class="value">{{ selected.soil_moisture }}</span>
                <div class="hint">しきい値 {{ selected.threshold }}</div>
              </div>
              <div class="metric">
                <span class="label">次回起床</span>
                <span class="value">{{ selected.next_wake }}</span>
                <div class="hint">sleep {{ selected.next_wake_detail }}</div>
              </div>
              <div class="metric">
                <span class="label">最終通信</span>
                <span class="value">{{ selected.last_seen_age }}</span>
                <div class="hint">{{ selected.last_seen }}</div>
              </div>
              <div class="metric">
                <span class="label">ファームウェア</span>
                <span class="value">{{ selected.firmware }}</span>
                <div class="hint">更新目標 {{ selected.target_firmware }}</div>
              </div>
              <div class="metric">
                <span class="label">更新状態</span>
                <span class="value"><span class="badge {{ selected.ota_class }}">{{ selected.ota_state }}</span></span>
                <div class="hint">{{ selected.ota_error or "問題なし" }}</div>
              </div>
            </div>
          </section>

          <section class="panel">
            <h2>水やり設定</h2>
            <form id="runtime-config-form" class="config-form">
              <div class="metrics">
                <div class="metric">
                  <span class="label">灌水しきい値</span>
                  <span class="value"><span id="threshold-display">{{ selected.config_summary.threshold }}</span></span>
                  <div class="hint">この値以下を灌水判定に使います</div>
                </div>
                <div class="metric">
                  <span class="label">強制灌水</span>
                  <span class="value"><span id="force-display">{{ selected.config_summary.force }}</span></span>
                  <div class="hint">ON の場合、条件に関わらず予約時刻に灌水します</div>
                </div>
                <div class="metric">
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
                <div class="config-field">
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
                <label class="switch-row" for="force-watering">
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

              <div>
                <h3>灌水予約</h3>
                <div id="schedule-editor" class="schedule-editor"></div>
                <div class="actions">
                  <button type="button" id="add-schedule">＋ 予約を追加</button>
                </div>
              </div>

              <div>
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

              <div>
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

              <div>
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

          <div class="section-grid">
            <section class="panel">
              <h2>灌水推移</h2>
              <div class="chart-card" data-chart-id="watering-trend-chart" data-chart-kind="watering">
                <div class="range-controls" aria-label="灌水推移の表示期間">
                  <button type="button" data-range-days="3" class="active">直近3日</button>
                  <button type="button" data-range-days="14">2週間</button>
                  <button type="button" data-range-months="1">1か月</button>
                  <button type="button" data-range-all="true">全期間</button>
                  <input type="date" data-range-start aria-label="開始日">
                  <input type="date" data-range-end aria-label="終了日">
                  <button type="button" data-range-custom="true">カスタム</button>
                </div>
                <div class="chart-body">
                  <div class="chart-loading">灌水推移を読み込み中...</div>
                </div>
              </div>
            </section>

            <section class="panel">
              <h2>土壌水分推移</h2>
              <div class="chart-card" data-chart-id="soil-moisture-chart" data-chart-kind="soil_moisture">
                <div class="range-controls" aria-label="土壌水分推移の表示期間">
                  <button type="button" data-range-days="3" class="active">直近3日</button>
                  <button type="button" data-range-days="14">2週間</button>
                  <button type="button" data-range-months="1">1か月</button>
                  <button type="button" data-range-all="true">全期間</button>
                  <input type="date" data-range-start aria-label="開始日">
                  <input type="date" data-range-end aria-label="終了日">
                  <button type="button" data-range-custom="true">カスタム</button>
                </div>
                <div class="chart-body">
                  <div class="chart-loading">土壌水分推移を読み込み中...</div>
                </div>
              </div>
            </section>
          </div>

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

          <div class="section-grid">
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

            <section class="panel">
              <h2>ファームウェア更新</h2>
              {% if selected.ota_history %}
              <div class="list">
                {% for item in selected.ota_history %}
                <div class="list-row">
                  <div class="list-time">{{ item.time }}</div>
                  <div class="list-main">
                    <span>{{ item.state }}</span>
                    <span>{{ item.from_version }} → {{ item.to_version }}</span>
                    {% if item.error %}<span class="badge danger">{{ item.error }}</span>{% endif %}
                  </div>
                </div>
                {% endfor %}
              </div>
              {% else %}
              <div class="empty">更新履歴はまだありません。</div>
              {% endif %}
            </section>
          </div>

          <section class="panel">
            <h2>詳細・保守</h2>
            <details>
              <summary>デバイスの承認・停止・基本情報</summary>
              <div class="detail-body">
                <div class="form-grid">
                  <div>
                    <h3>状態操作</h3>
                    <p>現在: <span class="badge {{ selected.state_class }}">{{ selected.state_label }}</span></p>
                    <label for="approved-by">承認者</label>
                    <input id="approved-by" type="text" value="operator">
                    <div class="actions">
                      <button type="button" data-state-action="approve">承認する</button>
                      <button type="button" data-state-action="disable">停止する</button>
                      <button type="button" data-state-action="retire">廃止する</button>
                    </div>
                  </div>
                  <form id="metadata-form">
                    <h3>表示情報</h3>
                    <label for="metadata-name">表示名</label>
                    <input id="metadata-name" name="name" type="text" value="{{ selected_device.name or '' }}">
                    <label for="metadata-location">場所</label>
                    <input id="metadata-location" name="location" type="text" value="{{ selected_device.location or '' }}">
                    <label for="metadata-memo">メモ</label>
                    <input id="metadata-memo" name="memo" type="text" value="{{ selected_device.memo or '' }}">
                    <div class="actions"><button type="submit" class="primary">保存</button></div>
                  </form>
                </div>
              </div>
            </details>

            <details>
              <summary>水やり設定 JSON</summary>
              <div class="detail-body">
                <textarea id="runtime-config-json">{{ format_json(selected_device.config) }}</textarea>
                <div class="actions">
                  <button type="button" id="apply-runtime-json">JSON をフォームに反映</button>
                  <button type="button" id="save-runtime-json">JSON で保存</button>
                  <button type="button" id="save-push-runtime-json" class="primary">JSON で保存して device に送信</button>
                </div>
              </div>
            </details>

            <details id="ota-target" open>
              <summary>OTA 更新対象</summary>
              <div class="detail-body">
                <form id="firmware-target-form">
                  <label for="target-firmware-version">更新したいバージョン</label>
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
              </div>
            </details>

            <details>
              <summary>Status History / OTA Status History / MQTT Event History</summary>
              <div class="detail-body">
                <h3>Status History</h3>
                <table>
                  <thead><tr><th>受信時刻</th><th>詳細 JSON</th></tr></thead>
                  <tbody>
                    {% for status in selected_statuses | reverse %}
                    <tr><td>{{ format_datetime(status.received_at) }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
                    {% endfor %}
                  </tbody>
                </table>
                <h3>OTA Status History</h3>
                <table>
                  <thead><tr><th>受信時刻</th><th>詳細 JSON</th></tr></thead>
                  <tbody>
                    {% for status in selected_ota_statuses | reverse %}
                    <tr><td>{{ format_datetime(status.received_at) }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
                    {% endfor %}
                  </tbody>
                </table>
                <h3>接続履歴</h3>
                {{ render_events(connection_events) | safe }}
                <h3>MQTT Event History</h3>
                {{ render_events(recent_events) | safe }}
              </div>
            </details>
          </section>
          <section id="firmware-maintenance" class="panel">
            <h2>ファームウェア保守</h2>
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
                  showChartEmpty(card, kind === "watering" ? "灌水に関する時系列データはまだありません。" : "土壌水分の時系列データはまだありません。");
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

          function createScheduleRow(schedule) {
            const row = document.createElement("div");
            row.className = "schedule-row";
            row.innerHTML = [
              '<div><label>時刻</label><input data-schedule-time type="time" required></div>',
              '<div><label>灌水時間（秒）</label><input data-schedule-duration type="number" min="1" max="3600" step="1" required></div>',
              '<div><label>系統</label><select data-schedule-channel><option value="1">系統1</option><option value="2">系統2</option><option value="3">系統1・系統2</option></select></div>',
              '<div><label>頻度</label><select data-schedule-frequency-mode><option value="daily">毎日</option><option value="interval">日にちごと</option><option value="weekdays">曜日指定</option></select></div>',
              '<div data-frequency-panel="interval"><label>間隔</label><input data-schedule-interval-days type="number" min="1" max="31" step="1"></div>',
              '<div data-frequency-panel="interval"><label>開始日</label><input data-schedule-start-date type="date"></div>',
              '<div data-frequency-panel="weekdays"><label>曜日</label><select data-schedule-weekdays multiple size="4"><option value="0">日</option><option value="1">月</option><option value="2">火</option><option value="3">水</option><option value="4">木</option><option value="5">金</option><option value="6">土</option></select></div>',
              '<button type="button" class="icon-button" data-remove-schedule aria-label="予約を削除">－</button>',
            ].join("");
            const frequency = scheduleFrequency(schedule || {});
            row.querySelector("[data-schedule-time]").value = scheduleToTime(schedule || {});
            row.querySelector("[data-schedule-duration]").value = String((schedule || {}).duration_sec || 1);
            row.querySelector("[data-schedule-channel]").value = String((schedule || {}).channel_mask || 1);
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
@app.route("/fields", methods=["GET", "POST"])
def fields_page():
    repo = field_repository()
    if request.method == "POST":
        data = _field_form_data(request.form)
        try:
            field = repo.upsert(None, data)
        except FieldValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        return redirect(f"/fields/{field['id']}")

    fields = repo.list()
    devices = device_config_service().get_all_records()
    template = """
    <html>
      <head>
        <title>Fields - INA Device Hub</title>
        <style>
          body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }
          a { color: #0f766e; }
          .layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 24px; align-items: start; }
          .field-list { display: grid; gap: 12px; }
          .field-card, form { border: 1px solid #d8dee4; border-radius: 8px; padding: 16px; background: #fff; }
          .meta { color: #667085; font-size: 13px; }
          .summary { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
          .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #e6f4f1; color: #0f766e; font-size: 12px; }
          label { display: block; font-weight: 600; margin-top: 10px; }
          input, textarea, select { width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; }
          textarea { min-height: 72px; }
          .check-row { display: flex; align-items: center; gap: 8px; font-weight: 500; }
          .check-row input { width: auto; }
          button { margin-top: 12px; padding: 8px 12px; border: 1px solid #0f766e; border-radius: 6px; background: #0f766e; color: white; cursor: pointer; }
          code { background: #eef2f7; padding: 2px 4px; border-radius: 4px; }
        </style>
      </head>
      <body>
        <p><a href="/">Home</a> / Fields</p>
        <h1>圃場</h1>
        <div class="layout">
          <section class="field-list">
            {% for field in fields %}
            <article class="field-card">
              <h2><a href="/fields/{{ field.id }}">{{ field.name }}</a></h2>
              <p class="meta">作物: {{ field.crop or '未設定' }}{% if field.crop_profile.cultivar %}（{{ field.crop_profile.cultivar }}）{% endif %} / ステージ: {{ field.stage or '未設定' }}</p>
              <p class="meta">デバイス: {{ field.device_ids|length }} 件 / カメラ: {{ field.camera_device_ids|length }} 件 / メモ: {{ field.notes|length }} 件 / 振り返り: {{ field.reflections|length }} 件</p>
              <div class="summary">
                {% if field.areas %}<span class="pill">監視単位 {{ field.areas|length }}件</span>{% else %}<span class="pill">監視単位 圃場全体</span>{% endif %}
                <span class="pill">土壌水分目標 {{ field.growth_targets.soil_moisture_percent.min }}-{{ field.growth_targets.soil_moisture_percent.max }}%</span>
                {% for action in field.control_policy.allowed_actions %}<span class="pill">{{ {'watering':'灌水','fertigation':'液肥','misting':'噴霧'}.get(action, action) }}</span>{% endfor %}
              </div>
              {% if field.memo %}<p>{{ field.memo }}</p>{% endif %}
            </article>
            {% else %}
            <p>圃場はまだありません。</p>
            {% endfor %}
          </section>
          <form method="post">
            <h2>圃場を追加</h2>
            <label>名前</label><input name="name" required>
            <label>作物</label><input name="crop" placeholder="例: トマト">
            <label>品種</label><input name="cultivar" placeholder="例: ミニトマト、桃太郎">
            <label>栽培ステージ</label><input name="stage" placeholder="例: 育苗、開花、収穫期">
            <label>栽培方式</label><input name="cultivation_method" placeholder="例: 露地、ハウス、プランター">
            <label>制御の目的</label><textarea name="objective" placeholder="例: 過湿を避けつつ土壌水分を安定させる"></textarea>
            <label class="check-row"><input type="checkbox" name="allowed_actions" value="watering" checked> 灌水を判断候補に入れる</label>
            <label class="check-row"><input type="checkbox" name="allowed_actions" value="fertigation"> 液肥を判断候補に入れる</label>
            <label class="check-row"><input type="checkbox" name="allowed_actions" value="misting"> 噴霧を判断候補に入れる</label>
            <label>MQTT device IDs</label><textarea name="device_ids" placeholder="1行に1つ、またはカンマ区切り"></textarea>
            <label>Camera device IDs</label><textarea name="camera_device_ids" placeholder="timelapse camera ID など"></textarea>
            <label>メモ</label><textarea name="memo"></textarea>
            <button type="submit">追加</button>
            <p class="meta">登録済みMQTTデバイス: {% for device_id in devices.keys() %}<code>{{ device_id }}</code> {% endfor %}</p>
          </form>
        </div>
      </body>
    </html>
    """
    return render_template_string(template, fields=fields, devices=devices)


@app.route("/fields/<field_id>", methods=["GET", "POST"])
def field_detail_page(field_id):
    repo = field_repository()
    field = repo.get(field_id)
    if field is None:
        return jsonify({"error": "field not found"}), 404

    if request.method == "POST":
        data = _field_form_data(request.form)
        try:
            repo.upsert(field_id, data)
        except FieldValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        return redirect(f"/fields/{field_id}")

    compare_date = request.args.get("compare_date", "").strip()
    context = _build_field_context(field, compare_date=compare_date)
    template = """
    <html>
      <head>
        <title>{{ field.name }} - INA Field</title>
        <script src="/local/assets/plotly.min.js"></script>
        <style>
          body { font-family: system-ui, sans-serif; margin: 0; color: #1f2933; background: #f6f8fb; }
          header { padding: 20px 28px; background: #fff; border-bottom: 1px solid #d8dee4; }
          main { padding: 20px 28px 36px; display: grid; gap: 18px; }
          a { color: #0f766e; }
          h1, h2, h3 { margin: 0 0 10px; }
          .meta { color: #667085; font-size: 13px; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; align-items: start; }
          .wide-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); gap: 16px; align-items: start; }
          section, article, form { border: 1px solid #d8dee4; border-radius: 8px; padding: 16px; background: #fff; }
          .panel-flat { border: 0; padding: 0; background: transparent; }
          .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
          .metric { display: grid; gap: 4px; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fbfcfe; }
          .metric span { color: #667085; font-size: 12px; }
          .metric strong { font-size: 18px; }
          .timeline { display: grid; gap: 10px; max-height: 620px; overflow: auto; }
          .timeline article { padding: 12px; }
          .tag { display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e6f4f1; color: #0f766e; font-size: 12px; }
          .tag.warn { background: #fff7ed; color: #c2410c; }
          .tag.wait { background: #eef2ff; color: #3730a3; }
          .candidate { display: grid; gap: 8px; }
          .candidate + .candidate { margin-top: 12px; }
          .detail-list { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 8px 12px; font-size: 14px; }
          .detail-list dt { color: #667085; }
          .detail-list dd { margin: 0; }
          label { display: block; font-weight: 600; margin-top: 10px; }
          input, textarea, select { width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; }
          textarea { min-height: 84px; }
          .check-row { display: flex; align-items: center; gap: 8px; font-weight: 500; }
          .check-row input { width: auto; }
          button { margin-top: 12px; padding: 8px 12px; border: 1px solid #0f766e; border-radius: 6px; background: #0f766e; color: white; cursor: pointer; }
          img { max-width: 100%; border-radius: 6px; border: 1px solid #e5e7eb; background: #f8fafc; }
          pre { white-space: pre-wrap; background: #f8fafc; padding: 12px; border-radius: 6px; }
          .image-compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
          .image-compare-three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
          .chart-box { min-height: 340px; }
          @media (max-width: 900px) { .wide-grid, .image-compare, .image-compare-three { grid-template-columns: 1fr; } header, main { padding-left: 14px; padding-right: 14px; } }
        </style>
      </head>
      <body>
        <header>
          <p class="meta"><a href="/fields">Fields</a> / {{ field.name }}</p>
          <h1>{{ field.name }}</h1>
          <p class="meta">作物: {{ field.crop or '未設定' }}{% if field.crop_profile.cultivar %}（{{ field.crop_profile.cultivar }}）{% endif %} / ステージ: {{ field.stage or '未設定' }} / MQTT: {{ field.device_ids|length }} / Camera: {{ field.camera_device_ids|length }}</p>
          {% if field.memo %}<p>{{ field.memo }}</p>{% endif %}
        </header>
        <main>
          <div class="grid">
            <section>
              <h2>最新センサー</h2>
              <div class="metrics">
                {% for item in context.latest_sensor_values %}
                  {% for key, value in item["values"].items() %}
                  <div class="metric"><span>{{ item.device_id }}{% if item.scope_label %} / {{ item.scope_label }}{% endif %}{% if item.crop_name %} / {{ item.crop_name }}{% endif %} / {{ metric_labels.get(key, key) }}</span><strong>{{ value }}</strong></div>
                  {% endfor %}
                {% else %}<p>センサー値はまだありません。</p>{% endfor %}
              </div>
            </section>
            <section>
              <h2>生育の前提</h2>
              <dl class="detail-list">
                <dt>作物</dt><dd>{{ field.crop or '未設定' }}{% if field.crop_profile.cultivar %} / {{ field.crop_profile.cultivar }}{% endif %}</dd>
                <dt>生育段階</dt><dd>{{ field.stage or '未設定' }}</dd>
                <dt>栽培方式</dt><dd>{{ field.cultivation_context.cultivation_method or '未設定' }}</dd>
                <dt>土・培地</dt><dd>{{ field.cultivation_context.soil_type or field.cultivation_context.substrate or '未設定' }}</dd>
                <dt>制御方針</dt><dd>{{ field.control_policy.objective }}</dd>
                <dt>自動化</dt><dd>{{ {'observe_only':'観察のみ','suggest_only':'提案のみ','manual_approval':'承認して実行','auto':'自動実行'}.get(field.control_policy.autonomy_level, field.control_policy.autonomy_level) }}</dd>
              </dl>
              <div class="metrics" style="margin-top: 12px;">
                <div class="metric"><span>土壌水分目標</span><strong>{{ field.growth_targets.soil_moisture_percent.min }}-{{ field.growth_targets.soil_moisture_percent.max }}%</strong></div>
                {% if field.growth_targets.soil_ec_us_cm.min or field.growth_targets.soil_ec_us_cm.max %}<div class="metric"><span>土壌EC目標</span><strong>{{ field.growth_targets.soil_ec_us_cm.min or '-' }}-{{ field.growth_targets.soil_ec_us_cm.max or '-' }}</strong></div>{% endif %}
                {% if field.growth_targets.soil_ph.min or field.growth_targets.soil_ph.max %}<div class="metric"><span>土壌pH目標</span><strong>{{ field.growth_targets.soil_ph.min or '-' }}-{{ field.growth_targets.soil_ph.max or '-' }}</strong></div>{% endif %}
                {% if field.growth_targets.air_humidity_percent.min or field.growth_targets.air_humidity_percent.max %}<div class="metric"><span>湿度目標</span><strong>{{ field.growth_targets.air_humidity_percent.min or '-' }}-{{ field.growth_targets.air_humidity_percent.max or '-' }}%</strong></div>{% endif %}
              </div>
              <h3 style="margin-top: 14px;">監視単位</h3>
              <dl class="detail-list">
                {% if field.areas %}
                  {% for area in field.areas %}
                  <dt>{{ area_type_labels.get(area.area_type, area.area_type) }}</dt><dd>{{ area.name }}{% if area.crop_name %} / {{ area.crop_name }}{% endif %}{% if area.memo %} / {{ area.memo }}{% endif %}</dd>
                  {% endfor %}
                {% else %}
                  <dt>圃場全体</dt><dd>区画・畝は未設定です。</dd>
                {% endif %}
              </dl>
              <h3 style="margin-top: 14px;">デバイス設置先</h3>
              <dl class="detail-list">
                {% for placement in context.device_placement_rows %}
                <dt>{{ placement.device_role_label }}</dt><dd>{{ placement.device_id }} / {{ placement.scope_label }}{% if placement.crop_name %} / {{ placement.crop_name }}{% endif %}</dd>
                {% else %}
                <dt>未設定</dt><dd>デバイスはまだ紐づいていません。</dd>
                {% endfor %}
              </dl>
            </section>
            <section>
              <h2>画像比較</h2>
              <form method="get" class="panel-flat">
                <label>基準日</label>
                <input type="date" name="compare_date" value="{{ context.compare_date }}">
                <button type="submit">比較日を更新</button>
              </form>
              <div class="image-compare image-compare-three">
                {% for group in context.image_compare_groups %}
                <article class="panel-flat">
                  <h3>{{ group.label }}</h3>
                  <p class="meta">{{ group.date }}</p>
                  {% if group.image %}
                  <p class="meta">{{ group.image.device_id or group.image.camera_id }} / {{ group.image.created_at or group.image.captured_at }}</p>
                  <img src="{{ group.image.url }}" alt="field image">
                  {% else %}<p>画像なし</p>{% endif %}
                </article>
                {% endfor %}
              </div>
            </section>
          </div>

          <section>
            <h2>次の判断候補</h2>
            <div class="grid">
              {% for candidate in context.action_candidates %}
              <article class="candidate">
                <p>
                  <span class="tag">{{ candidate.action_label }}</span>
                  {% if candidate.can_execute_now %}<span class="tag wait">承認後に実行可能</span>{% endif %}
                  {% if not candidate.support.supported %}<span class="tag warn">制御デバイス未対応</span>{% endif %}
                </p>
                <h3>{{ candidate.title }}</h3>
                <p>{{ candidate.scientific_reason }}</p>
                <dl class="detail-list">
                  <dt>根拠</dt><dd>{{ candidate.metric_label or '観察' }}{% if candidate.evidence.current_value is defined %}: {{ candidate.evidence.current_value }}{% endif %}</dd>
                  <dt>期待する変化</dt><dd>{{ candidate.expected_effect }}</dd>
                  <dt>注意点</dt><dd>{{ candidate.risk }}</dd>
                  <dt>実行可否</dt><dd>{{ candidate.support.reason }}</dd>
                </dl>
                <form method="post" action="/fields/{{ field.id }}/action-plans" class="panel-flat">
                  <input type="hidden" name="action_type" value="{{ candidate.action_type }}">
                  <input type="hidden" name="status" value="proposed">
                  <input type="hidden" name="title" value="{{ candidate.title }}">
                  <input type="hidden" name="scientific_reason" value="{{ candidate.scientific_reason }}">
                  <input type="hidden" name="expected_effect" value="{{ candidate.expected_effect }}">
                  <input type="hidden" name="risk" value="{{ candidate.risk }}">
                  <input type="hidden" name="source" value="{{ candidate.source }}">
                  <input type="hidden" name="preconditions_json" value='{{ candidate.preconditions|tojson }}'>
                  <input type="hidden" name="control_payload_json" value='{{ candidate.control_payload|tojson }}'>
                  <label>人間の判断メモ</label><textarea name="human_evaluation" placeholder="採用する理由、見送る理由、確認したいこと"></textarea>
                  <button type="submit">候補を記録する</button>
                </form>
              </article>
              {% else %}<p>判断候補はまだありません。</p>{% endfor %}
            </div>
          </section>

          <div class="wide-grid">
            <section>
              <h2>土壌水分推移</h2>
              <div class="chart-box">{{ context.soil_moisture_chart|safe if context.soil_moisture_chart else '土壌水分グラフのデータはまだありません。' }}</div>
            </section>
            <section>
              <h2>圃場イベント</h2>
              <form method="post" action="/fields/{{ field.id }}/events">
                <label>種類</label><select name="event_type"><option value="watering">潅水</option><option value="fertigation">液肥</option><option value="misting">噴霧</option><option value="fertilizer">追肥</option><option value="shade">遮光</option><option value="pest">病害虫</option><option value="harvest">収穫</option><option value="other">その他</option></select>
                <label>時刻</label><input name="occurred_at" type="datetime-local">
                <label>タイトル</label><input name="title" placeholder="例: 液肥追加、遮光ネット設置">
                <div class="grid"><div><label>量</label><input name="amount" placeholder="例: 500"></div><div><label>単位</label><input name="unit" placeholder="例: ml, g"></div></div>
                <label>対象デバイス</label><select name="device_id"><option value="">圃場全体</option>{% for placement in context.device_placement_rows %}<option value="{{ placement.device_id }}">{{ placement.device_id }} / {{ placement.scope_label }}</option>{% endfor %}</select>
                <label>内容</label><textarea name="description"></textarea>
                <label>人間の評価</label><textarea name="human_evaluation" placeholder="結果、効いた/効かなかった、次回見ること"></textarea>
                <label>タグ</label><input name="tags" placeholder="カンマ区切り">
                <button type="submit">イベントを記録</button>
              </form>
            </section>
          </div>

          <div class="wide-grid">
            <section>
              <h2>統合タイムライン</h2>
              <div class="timeline">
                {% for item in context.timeline %}
                <article>
                  <p class="meta">{{ item.at or '時刻なし' }} <span class="tag">{{ item.kind }}</span></p>
                  <h3>{{ item.title }}</h3>
                  {% if item.body %}<p>{{ item.body }}</p>{% endif %}
                </article>
                {% else %}<p>タイムラインはまだありません。</p>{% endfor %}
              </div>
            </section>
            <section>
              <h2>人間メモ</h2>
              <form method="post" action="/fields/{{ field.id }}/notes">
                <label>種別</label><select name="category"><option value="observation">観察</option><option value="work">作業</option><option value="fertilizer">施肥/液肥</option><option value="shade">遮光</option><option value="evaluation">評価</option></select>
                <label>メモ</label><textarea name="text" required></textarea>
                <label>人間の評価</label><textarea name="human_evaluation" placeholder="結果、良かった点、悪かった点、次回見ること"></textarea>
                <label>タグ</label><input name="tags" placeholder="カンマ区切り">
                <button type="submit">記録</button>
              </form>
            </section>
          </div>

          <section>
            <h2>アクション計画の履歴</h2>
            <div class="timeline">
              {% for plan in field.action_plans|reverse %}
              <article>
                <p class="meta">{{ plan.created_at }} <span class="tag">{{ {'watering':'灌水','fertigation':'液肥','misting':'噴霧','observation':'観察','environment':'環境'}.get(plan.action_type, plan.action_type) }}</span> <span class="tag wait">{{ plan.status }}</span></p>
                <h3>{{ plan.title }}</h3>
                {% if plan.scientific_reason %}<p>{{ plan.scientific_reason }}</p>{% endif %}
                {% if plan.expected_effect %}<p><strong>期待:</strong> {{ plan.expected_effect }}</p>{% endif %}
                {% if plan.human_evaluation %}<p><strong>人間の判断:</strong> {{ plan.human_evaluation }}</p>{% endif %}
              </article>
              {% else %}<p>アクション計画はまだありません。</p>{% endfor %}
            </div>
          </section>

          <section>
            <h2>データと評価の振り返り</h2>
            <form method="post" action="/fields/{{ field.id }}/reflections">
              <div class="grid"><div><label>期間開始</label><input name="period_start" type="date"></div><div><label>期間終了</label><input name="period_end" type="date"></div></div>
              <label>人間の評価</label><textarea name="human_evaluation" placeholder="この期間の結果、印象、作業の良し悪し"></textarea>
              <button type="submit">LLM振り返りを生成して保存</button>
            </form>
            <div class="timeline">
              {% for reflection in field.reflections|reverse %}
              <article>
                <p class="meta">{{ reflection.created_at }} / {{ reflection.period_start or '-' }} - {{ reflection.period_end or '-' }}</p>
                {% if reflection.human_evaluation %}<h3>人間の評価</h3><pre>{{ reflection.human_evaluation }}</pre>{% endif %}
                <h3>LLM振り返り</h3><pre>{{ reflection.llm_reflection }}</pre>
              </article>
              {% else %}<p>振り返りはまだありません。</p>{% endfor %}
            </div>
          </section>

          <section>
            <h2>圃場設定</h2>
            <form method="post">
              <label>名前</label><input name="name" value="{{ field.name }}" required>
              <div class="grid">
                <div><label>作物</label><input name="crop" value="{{ field.crop }}" placeholder="例: トマト"></div>
                <div><label>品種</label><input name="cultivar" value="{{ field.crop_profile.cultivar }}" placeholder="例: 桃太郎、アイコ"></div>
                <div><label>生育段階</label><input name="stage" value="{{ field.stage }}" placeholder="例: 育苗、開花、収穫期"></div>
              </div>
              <div class="grid">
                <div><label>播種日</label><input type="date" name="seeding_date" value="{{ field.crop_profile.seeding_date }}"></div>
                <div><label>定植日</label><input type="date" name="transplant_date" value="{{ field.crop_profile.transplant_date }}"></div>
                <div><label>収穫目標日</label><input type="date" name="target_harvest_date" value="{{ field.crop_profile.target_harvest_date }}"></div>
              </div>
              <h3>栽培条件</h3>
              <div class="grid">
                <div><label>栽培方式</label><input name="cultivation_method" value="{{ field.cultivation_context.cultivation_method }}" placeholder="例: 露地、ハウス、プランター"></div>
                <div><label>土質</label><input name="soil_type" value="{{ field.cultivation_context.soil_type }}" placeholder="例: 黒土、砂壌土"></div>
                <div><label>培地</label><input name="substrate" value="{{ field.cultivation_context.substrate }}" placeholder="例: ココピート、培養土"></div>
                <div><label>ハウス・設備</label><input name="greenhouse_type" value="{{ field.cultivation_context.greenhouse_type }}"></div>
                <div><label>マルチ</label><input name="mulching" value="{{ field.cultivation_context.mulching }}"></div>
                <div><label>潅水方式</label><input name="irrigation_method" value="{{ field.cultivation_context.irrigation_method }}" placeholder="例: 点滴、散水"></div>
                <div><label>水源</label><input name="water_source" value="{{ field.cultivation_context.water_source }}"></div>
                <div><label>面積 m2</label><input type="number" step="0.01" name="bed_area_m2" value="{{ field.cultivation_context.bed_area_m2 or '' }}"></div>
                <div><label>株数</label><input type="number" name="plant_count" value="{{ field.cultivation_context.plant_count or '' }}"></div>
              </div>
              <label>栽培条件メモ</label><textarea name="cultivation_notes">{{ field.cultivation_context.notes }}</textarea>
              <h3>圃場内の監視単位</h3>
              <label>区画・畝・測点</label>
              <textarea name="areas_text" placeholder="例: A区画,section,トマト,南側&#10;1番畝,ridge,トマト,SOI設置&#10;代表点,point,,ENVは圃場全体">{{ areas_text }}</textarea>
              <p class="meta">1行に「名前,種類,作物,メモ」。種類は section=区画 / bed=ベッド / ridge=畝 / zone=ゾーン / point=測点 / other=その他。小規模なら空欄のままで圃場全体として扱います。</p>
              <h3>目標レンジ</h3>
              <div class="grid">
                <div><label>土壌水分 下限%</label><input type="number" step="0.1" name="target_soil_moisture_min" value="{{ field.growth_targets.soil_moisture_percent.min or '' }}"></div>
                <div><label>土壌水分 上限%</label><input type="number" step="0.1" name="target_soil_moisture_max" value="{{ field.growth_targets.soil_moisture_percent.max or '' }}"></div>
                <div><label>土壌EC 下限</label><input type="number" step="0.1" name="target_soil_ec_min" value="{{ field.growth_targets.soil_ec_us_cm.min or '' }}"></div>
                <div><label>土壌EC 上限</label><input type="number" step="0.1" name="target_soil_ec_max" value="{{ field.growth_targets.soil_ec_us_cm.max or '' }}"></div>
                <div><label>土壌pH 下限</label><input type="number" step="0.1" name="target_soil_ph_min" value="{{ field.growth_targets.soil_ph.min or '' }}"></div>
                <div><label>土壌pH 上限</label><input type="number" step="0.1" name="target_soil_ph_max" value="{{ field.growth_targets.soil_ph.max or '' }}"></div>
                <div><label>湿度 下限%</label><input type="number" step="0.1" name="target_air_humidity_min" value="{{ field.growth_targets.air_humidity_percent.min or '' }}"></div>
                <div><label>湿度 上限%</label><input type="number" step="0.1" name="target_air_humidity_max" value="{{ field.growth_targets.air_humidity_percent.max or '' }}"></div>
                <div><label>光量 下限</label><input type="number" step="0.1" name="target_par_min" value="{{ field.growth_targets.par_umol_m2_s.min or '' }}"></div>
                <div><label>光量 上限</label><input type="number" step="0.1" name="target_par_max" value="{{ field.growth_targets.par_umol_m2_s.max or '' }}"></div>
              </div>
              <h3>制御方針</h3>
              <label>目的</label><textarea name="objective">{{ field.control_policy.objective }}</textarea>
              <label>自動化レベル</label>
              <select name="autonomy_level">
                <option value="observe_only" {% if field.control_policy.autonomy_level == 'observe_only' %}selected{% endif %}>観察のみ</option>
                <option value="suggest_only" {% if field.control_policy.autonomy_level == 'suggest_only' %}selected{% endif %}>提案のみ</option>
                <option value="manual_approval" {% if field.control_policy.autonomy_level == 'manual_approval' %}selected{% endif %}>承認して実行</option>
                <option value="auto" {% if field.control_policy.autonomy_level == 'auto' %}selected{% endif %}>自動実行</option>
              </select>
              <label class="check-row"><input type="checkbox" name="allowed_actions" value="watering" {% if 'watering' in field.control_policy.allowed_actions %}checked{% endif %}> 灌水</label>
              <label class="check-row"><input type="checkbox" name="allowed_actions" value="fertigation" {% if 'fertigation' in field.control_policy.allowed_actions %}checked{% endif %}> 液肥</label>
              <label class="check-row"><input type="checkbox" name="allowed_actions" value="misting" {% if 'misting' in field.control_policy.allowed_actions %}checked{% endif %}> 噴霧</label>
              <div class="grid">
                <div><label>1日の最大灌水秒数</label><input type="number" name="max_watering_sec_per_day" value="{{ field.control_policy.max_watering_sec_per_day or '' }}"></div>
                <div><label>最小灌水間隔 分</label><input type="number" name="min_watering_interval_min" value="{{ field.control_policy.min_watering_interval_min or '' }}"></div>
              </div>
              <label>安全メモ</label><textarea name="safety_notes">{{ field.control_policy.safety_notes }}</textarea>
              <h3>外部知識と画像観察</h3>
              <label>調べたい研究・栽培テーマ</label><textarea name="research_queries" placeholder="1行に1テーマ">{{ field.knowledge_context.research_queries|join('\n') }}</textarea>
              <label>参考URL</label><textarea name="external_reference_urls" placeholder="1行に1URL">{{ field.knowledge_context.external_reference_urls|join('\n') }}</textarea>
              <label>画像を見るときの観点</label><textarea name="image_observation_prompt" placeholder="例: 葉色、萎れ、病斑、節間、開花数を見る">{{ field.knowledge_context.image_observation_prompt }}</textarea>
              <label>知識メモ</label><textarea name="knowledge_notes">{{ field.knowledge_context.notes }}</textarea>
              <label>MQTT device IDs</label><textarea name="device_ids">{{ field.device_ids|join('\n') }}</textarea>
              <label>Camera device IDs</label><textarea name="camera_device_ids">{{ field.camera_device_ids|join('\n') }}</textarea>
              <h3>デバイスの紐づけ先</h3>
              <p class="meta">ENV は通常「圃場全体」、SOI は測点・畝、WTR は実際に水を入れる対象へ紐づけます。デバイスIDを追加した直後は保存後にここへ表示されます。</p>
              {% for placement in context.device_placement_rows %}
              <article class="panel-flat">
                <h3>{{ placement.device_id }}</h3>
                <p class="meta">{{ placement.device_role_label }} / 現在: {{ placement.scope_label }}{% if placement.crop_name %} / {{ placement.crop_name }}{% endif %}</p>
                <input type="hidden" name="placement_device_id_{{ loop.index0 }}" value="{{ placement.device_id }}">
                <input type="hidden" name="placement_device_role_{{ loop.index0 }}" value="{{ placement.device_role }}">
                <div class="grid">
                  <div>
                    <label>設置先の範囲</label>
                    <select name="placement_scope_type_{{ loop.index0 }}">
                      {% for value, label in scope_type_labels.items() %}
                      <option value="{{ value }}" {% if placement.scope_type == value %}selected{% endif %}>{{ label }}</option>
                      {% endfor %}
                    </select>
                  </div>
                  <div>
                    <label>対象の区画・畝・測点</label>
                    <select name="placement_area_id_{{ loop.index0 }}">
                      <option value="">圃場全体</option>
                      {% for area in field.areas %}
                      <option value="{{ area.id }}" {% if placement.area_id == area.id %}selected{% endif %}>{{ area_type_labels.get(area.area_type, area.area_type) }}: {{ area.name }}</option>
                      {% endfor %}
                    </select>
                  </div>
                  <div><label>参考にする作物</label><input name="placement_crop_name_{{ loop.index0 }}" value="{{ placement.crop_name }}" placeholder="未設定なら区画または圃場の作物"></div>
                  <div><label>設置メモ</label><input name="placement_memo_{{ loop.index0 }}" value="{{ placement.memo }}"></div>
                </div>
              </article>
              {% else %}
              <p>紐づけるデバイスはまだありません。</p>
              {% endfor %}
              <label>メモ</label><textarea name="memo">{{ field.memo }}</textarea>
              <button type="submit">保存</button>
            </form>
          </section>
        </main>
      </body>
    </html>
    """
    return render_template_string(
        template,
        field=field,
        context=context,
        metric_labels=METRIC_LABELS,
        area_type_labels=FIELD_AREA_TYPE_LABELS,
        scope_type_labels=DEVICE_SCOPE_TYPE_LABELS,
        areas_text=_field_areas_text(field.get("areas") or []),
    )


@app.route("/fields/<field_id>/notes", methods=["POST"])
def add_field_note(field_id):
    try:
        field_repository().add_note(
            field_id,
            {
                "category": request.form.get("category", "observation"),
                "text": request.form.get("text", ""),
                "human_evaluation": request.form.get("human_evaluation", ""),
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}")


@app.route("/fields/<field_id>/events", methods=["POST"])
def add_field_event(field_id):
    try:
        field_repository().add_event(
            field_id,
            {
                "event_type": request.form.get("event_type", "observation"),
                "occurred_at": request.form.get("occurred_at", ""),
                "title": request.form.get("title", ""),
                "description": request.form.get("description", ""),
                "amount": request.form.get("amount", ""),
                "unit": request.form.get("unit", ""),
                "device_id": request.form.get("device_id", ""),
                "human_evaluation": request.form.get("human_evaluation", ""),
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}")


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
                "tags": _split_lines_or_commas(request.form.get("tags", "")),
            },
        )
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return redirect(f"/fields/{field_id}")


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
    return redirect(f"/fields/{field_id}")


@app.route("/local/api/fields", methods=["GET"])
def list_fields_api():
    return jsonify(field_repository().list())


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
    request_body = request.get_json(silent=True)
    if not isinstance(request_body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        event = field_repository().add_event(field_id, request_body)
    except FieldValidationError as exc:
        return jsonify({"error": str(exc)}), 400
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


def _field_form_data(form):
    return {
        "name": form.get("name", ""),
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
        {
            key.rsplit("_", 1)[-1]
            for key in form.keys()
            if key.startswith("placement_device_id_") and key.rsplit("_", 1)[-1].isdigit()
        },
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


def _build_field_context(field: dict, compare_date: str = ""):
    compare_day = _field_compare_day(compare_date)
    device_records = device_config_service().get_all_records()
    device_ids = field.get("device_ids") or []
    camera_ids = field.get("camera_device_ids") or []
    placement_rows = _field_device_placement_rows(field, device_records)
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

    recent_status_events = sorted(recent_status_events, key=lambda item: item.get("received_at") or "", reverse=True)[:40]
    field_events = sorted(list(field.get("events") or []), key=lambda item: item.get("occurred_at") or item.get("created_at") or "", reverse=True)
    timeline = _build_field_timeline(recent_status_events, field_events, field.get("notes") or [])
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
        "soil_moisture_chart": _build_field_soil_moisture_chart(statuses_for_chart, field_events, include_plotlyjs=False) if statuses_for_chart else "",
    }
    context["action_candidates"] = build_action_candidates(context)
    return context


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
        rows.append(_format_device_placement(device_id, role, placement, areas))
        seen.add(device_id)
    for camera_id in field.get("camera_device_ids") or []:
        if camera_id in seen:
            continue
        placement = explicit.get((camera_id, "camera")) or _first_device_placement(explicit, camera_id)
        rows.append(_format_device_placement(camera_id, "camera", placement, areas))
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


def _build_field_soil_moisture_chart(statuses, field_events, include_plotlyjs=False):
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
    return _plotly_div(fig, "field-soil-moisture-chart", include_plotlyjs=include_plotlyjs)


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
        timeline.append({
            "kind": "device_status",
            "at": event.get("received_at"),
            "title": event.get("summary"),
            "body": event.get("device_id"),
        })
    for event in field_events:
        amount = ""
        if event.get("amount"):
            amount = f" {event.get('amount')}{event.get('unit') or ''}"
        timeline.append({
            "kind": event.get("event_type") or "field_event",
            "at": event.get("occurred_at") or event.get("created_at"),
            "title": f"{event.get('title') or event.get('event_type')}{amount}",
            "body": event.get("description") or event.get("human_evaluation") or "",
        })
    for note in notes:
        timeline.append({
            "kind": note.get("category") or "note",
            "at": note.get("created_at"),
            "title": note.get("text"),
            "body": note.get("human_evaluation") or "",
        })
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


def flask_run():
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
