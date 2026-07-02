import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from html import escape

from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, send_file

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


@app.route("/mqtt-devices", methods=["GET"])
def mqtt_devices_page():
    device_id = request.args.get("device_id")
    devices = device_config_service().get_all_records()
    selected_device_id = device_id or next(iter(devices), None)
    selected_device = devices.get(selected_device_id) if selected_device_id else None
    selected_statuses = device_config_service().list_statuses(selected_device_id, limit=20) if selected_device_id else []
    selected_ota_statuses = ota_update_service().list_ota_statuses(selected_device_id, limit=20) if selected_device_id else []
    firmware_artifacts = ota_update_service().get_artifacts()
    recent_events = list_device_events(limit=50, device_id=selected_device_id) if selected_device_id else list_device_events(limit=50)
    connection_events = (
        list_device_events(limit=50, device_id=selected_device_id, connection_events_only=True)
        if selected_device_id
        else list_device_events(limit=50, connection_events_only=True)
    )
    template = """
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>MQTT Devices</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; color: #1f2933; }
          a { color: #1652a8; }
          table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
          th, td { border: 1px solid #d9e2ec; padding: 6px 8px; vertical-align: top; font-size: 14px; }
          th { background: #f0f4f8; text-align: left; }
          pre { white-space: pre-wrap; word-break: break-word; background: #f7f9fb; border: 1px solid #d9e2ec; padding: 10px; }
          textarea { box-sizing: border-box; width: 100%; min-height: 220px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px; }
          input, select, button { font-size: 14px; padding: 6px 8px; margin: 3px 4px 8px 0; }
          label { display: block; font-weight: 600; margin-top: 8px; }
          section { border-top: 1px solid #d9e2ec; padding-top: 16px; margin-top: 20px; }
          .actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0 14px; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; align-items: start; }
          .muted { color: #52606d; font-size: 13px; }
          .nav a { margin-right: 12px; }
          .result { border: 1px solid #d9e2ec; background: #f7f9fb; padding: 10px; min-height: 20px; }
          .error { border-color: #d64545; background: #fff5f5; color: #8a1f1f; }
          .ok { border-color: #2f855a; background: #f0fff4; color: #22543d; }
        </style>
      </head>
      <body>
        <h1>MQTT Devices</h1>
        <p class="nav">
          <a href="/">Home</a>
          <a href="/local/api/mqtt-devices">Devices API</a>
          <a href="/local/api/mqtt-events">Events API</a>
          <a href="/local/api/mqtt-connections">Connections API</a>
          <a href="/local/api/firmware-artifacts">Firmware API</a>
        </p>
        <div id="action-result" class="result muted"></div>
        <h2>Registered Devices</h2>
        <table>
          <thead>
            <tr>
              <th>device_id</th>
              <th>state</th>
              <th>kind</th>
              <th>firmware</th>
              <th>target</th>
              <th>OTA state</th>
              <th>last config request</th>
              <th>last status</th>
            </tr>
          </thead>
          <tbody>
            {% for id, record in devices.items() %}
            <tr>
              <td><a href="/mqtt-devices?device_id={{ id }}">{{ id }}</a></td>
              <td>{{ record.state }}</td>
              <td>{{ record.device_kind }}</td>
              <td>{{ record.firmware_version }}</td>
              <td>{{ record.target_firmware_version }}</td>
              <td>{{ record.ota_state }}</td>
              <td>{{ record.last_config_request_at }}</td>
              <td>{{ record.last_status_at }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% if selected_device %}
        <h2>Selected Device</h2>
        <p><strong>{{ selected_device_id }}</strong></p>
        <div class="grid">
          <section>
            <h3>Device State</h3>
            <p>state: <strong>{{ selected_device.state }}</strong></p>
            <label for="approved-by">approved_by</label>
            <input id="approved-by" type="text" value="operator">
            <div class="actions">
              <button type="button" data-state-action="approve">Approve</button>
              <button type="button" data-state-action="disable">Disable</button>
              <button type="button" data-state-action="retire">Retire</button>
            </div>
          </section>
          <section>
            <h3>Metadata</h3>
            <form id="metadata-form">
              <label for="metadata-name">name</label>
              <input id="metadata-name" name="name" type="text" value="{{ selected_device.name or '' }}">
              <label for="metadata-location">location</label>
              <input id="metadata-location" name="location" type="text" value="{{ selected_device.location or '' }}">
              <label for="metadata-memo">memo</label>
              <input id="metadata-memo" name="memo" type="text" value="{{ selected_device.memo or '' }}">
              <div class="actions"><button type="submit">Save metadata</button></div>
            </form>
          </section>
        </div>

        <section>
          <h3>Runtime Config</h3>
          <textarea id="runtime-config-json">{{ format_json(selected_device.config) }}</textarea>
          <div class="actions">
            <button type="button" id="save-runtime-config">Save config</button>
            <button type="button" id="save-push-runtime-config">Save and push</button>
            <button type="button" id="push-runtime-config">Push current config</button>
          </div>
        </section>

        <section>
          <h3>OTA Target</h3>
          <form id="firmware-target-form">
            <label for="target-firmware-version">target_firmware_version</label>
            <input id="target-firmware-version" type="text" value="{{ selected_device.target_firmware_version or '' }}">
            <div class="actions">
              <button type="submit">Set target</button>
              <button type="button" id="clear-firmware-target">Clear target</button>
            </div>
          </form>
        </section>

        <section>
          <h3>Status History</h3>
          <table>
            <thead><tr><th>received_at</th><th>payload</th></tr></thead>
            <tbody>
              {% for status in selected_statuses | reverse %}
              <tr><td>{{ status.received_at }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
              {% endfor %}
            </tbody>
          </table>
        </section>

        <section>
          <h3>OTA Status History</h3>
          <table>
            <thead><tr><th>received_at</th><th>payload</th></tr></thead>
            <tbody>
              {% for status in selected_ota_statuses | reverse %}
              <tr><td>{{ status.received_at }}</td><td><pre>{{ format_json(status.payload) }}</pre></td></tr>
              {% endfor %}
            </tbody>
          </table>
        </section>

        <section>
          <h3>Connection History</h3>
          {{ render_events(connection_events) | safe }}
        </section>
        <section>
          <h3>MQTT Event History</h3>
          {{ render_events(recent_events) | safe }}
        </section>
        {% endif %}

        <section>
          <h2>Firmware Artifacts</h2>
          <form id="firmware-upload-form" enctype="multipart/form-data">
            <div class="grid">
              <div>
                <label for="firmware-device-kind">device_kind</label>
                <input id="firmware-device-kind" name="device_kind" type="text" value="{{ selected_device.device_kind if selected_device and selected_device.device_kind else 'WTR' }}" maxlength="3">
              </div>
              <div>
                <label for="firmware-version">version</label>
                <input id="firmware-version" name="version" type="text" value="{{ selected_device.target_firmware_version if selected_device and selected_device.target_firmware_version else '' }}">
              </div>
              <div>
                <label for="firmware-build-id">build_id</label>
                <input id="firmware-build-id" name="build_id" type="text">
              </div>
              <div>
                <label for="firmware-rollout-state">rollout_state</label>
                <select id="firmware-rollout-state" name="rollout_state">
                  <option value="active">active</option>
                  <option value="paused">paused</option>
                  <option value="revoked">revoked</option>
                </select>
              </div>
            </div>
            <label for="firmware-file">firmware.bin</label>
            <input id="firmware-file" name="firmware" type="file" required>
            <div class="actions">
              <label><input id="firmware-force" name="force" type="checkbox">force</label>
              <label><input id="firmware-allow-downgrade" name="allow_downgrade" type="checkbox">allow_downgrade</label>
              <button type="submit">Upload and register</button>
            </div>
          </form>
          <table>
            <thead><tr><th>key</th><th>version</th><th>kind</th><th>state</th><th>size</th><th>sha256</th><th>url</th><th>updated</th></tr></thead>
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
        </section>

        <script>
          const selectedDeviceId = {{ selected_device_id | tojson }};

          function resultBox() {
            return document.getElementById("action-result");
          }

          function showResult(message, ok) {
            const box = resultBox();
            box.className = "result " + (ok ? "ok" : "error");
            box.textContent = message;
          }

          async function requestJson(url, options) {
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
            window.setTimeout(() => window.location.reload(), 500);
          }

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
                showResult("Device state updated", true);
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
                showResult("Metadata saved", true);
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
              showResult("Runtime config JSON is invalid", false);
              return;
            }
            try {
              await requestJson("/local/api/mqtt-devices/" + encodeURIComponent(selectedDeviceId) + "/runtime-config?push=" + String(Boolean(push)), {
                method: "PUT",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(config),
              });
              showResult(push ? "Runtime config saved and pushed" : "Runtime config saved", true);
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
                showResult("Runtime config pushed", true);
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
              showResult("Firmware target updated", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          }

          const firmwareUploadForm = document.getElementById("firmware-upload-form");
          firmwareUploadForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const deviceKind = document.getElementById("firmware-device-kind").value.trim();
            const version = document.getElementById("firmware-version").value.trim();
            if (!deviceKind || !version) {
              showResult("device_kind and version are required", false);
              return;
            }
            const formData = new FormData();
            const file = document.getElementById("firmware-file").files[0];
            if (!file) {
              showResult("firmware.bin is required", false);
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
              showResult("Firmware uploaded and registered", true);
              reloadSoon();
            } catch (error) {
              showResult(error.message, false);
            }
          });
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
        format_json=_format_json,
        render_events=_render_event_table,
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
