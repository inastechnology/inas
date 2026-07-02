import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from html import escape

from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, send_file
from plotly import graph_objs as go
from plotly.io import to_html

from ina_device_hub.camera_connector import camera_connector
from ina_device_hub.device_config_repository import DeviceConfigValidationError, DeviceRecordValidationError
from ina_device_hub.device_config_service import device_config_service
from ina_device_hub.device_event_log import list_device_events
from ina_device_hub.location_repository import location_repository
from ina_device_hub.ota_update_service import FirmwareArtifactValidationError, ota_update_service
from ina_device_hub.sensor_data_repository import sensor_data_repository
from ina_device_hub.sensor_device_repository import sensor_device_repository
from ina_device_hub.sensor_image_repogitory import sensor_image_repogitory
from ina_device_hub.setting import setting
from ina_device_hub.storage_connector import storage_connector
from ina_device_hub.utils import Utils

app = Flask(__name__)
MQTT_ADMIN_STATUS_HISTORY_LIMIT = 2000


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
    watering_chart = _build_watering_trend_chart(statuses, include_plotlyjs=True)
    soil_moisture_chart = _build_soil_moisture_chart(statuses, include_plotlyjs=watering_chart is None)
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
        "watering_chart": watering_chart,
        "soil_moisture_chart": soil_moisture_chart,
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
        received_at = _parse_datetime(entry.get("received_at")) if isinstance(entry, dict) else None
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
        received_at = _parse_datetime(entry.get("received_at")) if isinstance(entry, dict) else None
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
        return {"threshold": "未設定", "force": "未設定", "schedule_count": "0件"}
    return {
        "threshold": _format_percent(config.get("moisture_threshold")),
        "force": _format_bool(config.get("force_watering")),
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
    parsed = _parse_datetime(value)
    if parsed is None:
        return "未取得"
    jst = parsed.astimezone(UTC) + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


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
          }
        </style>
      </head>
      <body>
        <div class="page">
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

          <div class="section-grid">
            <section class="panel">
              <h2>灌水推移</h2>
              {% if selected.watering_chart %}
              <div class="chart-card" data-chart-id="watering-trend-chart">
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
                  {{ selected.watering_chart | safe }}
                </div>
              </div>
              {% else %}
              <div class="empty">灌水に関する時系列データはまだありません。</div>
              {% endif %}
            </section>

            <section class="panel">
              <h2>土壌水分推移</h2>
              {% if selected.soil_moisture_chart %}
              <div class="chart-card" data-chart-id="soil-moisture-chart">
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
                  {{ selected.soil_moisture_chart | safe }}
                </div>
              </div>
              {% else %}
              <div class="empty">土壌水分の時系列データはまだありません。</div>
              {% endif %}
            </section>
          </div>

          <section class="panel">
            <h2>水やり設定</h2>
            <div class="metrics">
              <div class="metric">
                <span class="label">灌水しきい値</span>
                <span class="value">{{ selected.config_summary.threshold }}</span>
              </div>
              <div class="metric">
                <span class="label">強制灌水</span>
                <span class="value">{{ selected.config_summary.force }}</span>
              </div>
              <div class="metric">
                <span class="label">予約数</span>
                <span class="value">{{ selected.config_summary.schedule_count }}</span>
              </div>
            </div>
            <h3>予約されている水やり</h3>
            {% if selected.schedules %}
            <div class="schedule-grid">
              {% for schedule in selected.schedules %}
              <div class="schedule">
                <strong>{{ schedule.time }}</strong>
                <div>{{ schedule.duration }}</div>
                <div class="muted">{{ schedule.channel }}</div>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty">水やり予約はありません。</div>
            {% endif %}
          </section>

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
              <summary>水やり設定 JSON と即時反映</summary>
              <div class="detail-body">
                <textarea id="runtime-config-json">{{ format_json(selected_device.config) }}</textarea>
                <div class="actions">
                  <button type="button" id="save-runtime-config">設定を保存</button>
                  <button type="button" id="save-push-runtime-config" class="primary">保存して device に送信</button>
                  <button type="button" id="push-runtime-config">保存済み設定を送信</button>
                </div>
              </div>
            </details>

            <details id="ota-target" open>
              <summary>OTA 更新対象</summary>
              <div class="detail-body">
                <form id="firmware-target-form">
                  <label for="target-firmware-version">更新したいバージョン</label>
                  <input id="target-firmware-version" type="text" value="{{ selected_device.target_firmware_version or '' }}">
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
                    <tr><td>{{ status.received_at }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
                    {% endfor %}
                  </tbody>
                </table>
                <h3>OTA Status History</h3>
                <table>
                  <thead><tr><th>受信時刻</th><th>詳細 JSON</th></tr></thead>
                  <tbody>
                    {% for status in selected_ota_statuses | reverse %}
                    <tr><td>{{ status.received_at }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
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
                      <input id="firmware-device-kind" name="device_kind" type="text" value="{{ selected_device.device_kind if selected_device and selected_device.device_kind else 'WTR' }}" maxlength="3">
                    </div>
                    <div>
                      <label for="firmware-version">バージョン</label>
                      <input id="firmware-version" name="version" type="text" value="{{ selected_device.target_firmware_version if selected_device and selected_device.target_firmware_version else '' }}">
                    </div>
                    <div>
                      <label for="firmware-build-id">ビルド ID</label>
                      <input id="firmware-build-id" name="build_id" type="text">
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
                  <div class="actions">
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
                  <thead><tr><th>キー</th><th>バージョン</th><th>種別</th><th>状態</th><th>サイズ</th><th>SHA-256</th><th>URL</th><th>更新日時</th></tr></thead>
                  <tbody>
                    {% for key, artifact in firmware_artifacts.items() %}
                    <tr>
                      <td>{{ key }}</td>
                      <td>{{ artifact.version }}</td>
                      <td>{{ artifact.device_kind }}</td>
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

          function resultBox() {
            return document.getElementById("action-result");
          }

          function showResult(message, ok) {
            const box = resultBox();
            box.className = "result " + (ok ? "ok" : "error");
            box.textContent = message;
          }

          async function requestJson(url, options) {
            if (demoMode) {
              return { demo: true };
            }
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
          }

          function reloadSoon() {
            if (demoMode) {
              return;
            }
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

          document.querySelectorAll(".chart-card[data-chart-id]").forEach((card) => {
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
          });

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
                });
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
                });
                showResult("表示情報を保存しました", true);
                reloadSoon();
              } catch (error) {
                showResult(error.message, false);
              }
            });
          }

          async function saveRuntimeConfig(push) {
            const textarea = document.getElementById("runtime-config-json");
            let config;
            try {
              config = JSON.parse(textarea.value);
            } catch (error) {
              showResult("水やり設定 JSON が正しくありません", false);
              return;
            }
            try {
              await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/runtime-config?push=" + String(Boolean(push)), {
                method: "PUT",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(config),
              });
              showResult(push ? "水やり設定を保存して device に送信しました" : "水やり設定を保存しました", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          }

          const saveConfigButton = document.getElementById("save-runtime-config");
          if (saveConfigButton) saveConfigButton.addEventListener("click", () => saveRuntimeConfig(false));
          const savePushConfigButton = document.getElementById("save-push-runtime-config");
          if (savePushConfigButton) savePushConfigButton.addEventListener("click", () => saveRuntimeConfig(true));
          const pushConfigButton = document.getElementById("push-runtime-config");
          if (pushConfigButton) {
            pushConfigButton.addEventListener("click", async () => {
              try {
                await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/runtime-config/push", { method: "POST" });
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
              });
              showResult("更新対象バージョンを更新しました", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          }

          const firmwareUploadForm = document.getElementById("firmware-upload-form");
          if (firmwareUploadForm) {
            firmwareUploadForm.addEventListener("submit", async (event) => {
              event.preventDefault();
              const deviceKind = document.getElementById("firmware-device-kind").value.trim();
              const version = document.getElementById("firmware-version").value.trim();
              if (!deviceKind || !version) {
                showResult("デバイス種別とバージョンは必須です", false);
                return;
              }
              const formData = new FormData();
              const file = document.getElementById("firmware-file").files[0];
              if (!file) {
                showResult("firmware.bin を選択してください", false);
                return;
              }
              formData.append("firmware", file);
              const buildId = document.getElementById("firmware-build-id").value;
              if (buildId) formData.append("build_id", buildId);
              formData.append("rollout_state", document.getElementById("firmware-rollout-state").value);
              formData.append("force", document.getElementById("firmware-force").checked ? "true" : "false");
              formData.append("allow_downgrade", document.getElementById("firmware-allow-downgrade").checked ? "true" : "false");
              try {
                await requestJson(
                  "/local/api/firmware-artifacts/" + encodeURIComponent(deviceKind) + "/" + encodeURIComponent(version) + "/upload",
                  { method: "POST", body: formData },
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
        firmware_artifacts=firmware_artifacts,
        connection_events=connection_events,
        recent_events=recent_events,
        admin_view=admin_view,
        format_json=_format_json,
        render_events=_render_event_table,
        demo_mode=demo_mode,
        device_link_prefix=device_link_prefix,
        is_detail_page=is_detail_page,
        list_path=list_path,
    )


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


@app.route("/local/api/firmware-artifacts", methods=["GET"])
def list_firmware_artifacts():
    return jsonify(ota_update_service().get_artifacts())


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


def flask_run():
    http_settings = setting().get("http") or {}
    app.run(host=http_settings.get("host", "0.0.0.0"), port=int(http_settings.get("port", 39151)))


def _request_limit(default: int = 100, maximum: int = 1000):
    try:
        limit = int(request.args.get("limit", str(default)))
    except ValueError:
        return default
    return max(1, min(limit, maximum))


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
            f"<td>{escape(str(event.get('occurred_at') or ''))}</td>"
            f"<td>{escape(str(event.get('event_type') or ''))}</td>"
            f"<td>{escape(str(event.get('direction') or ''))}</td>"
            f"<td>{escape(str(event.get('topic') or ''))}</td>"
            f"<td><pre>{payload}</pre></td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>time</th><th>event</th><th>direction</th><th>topic</th><th>payload</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
