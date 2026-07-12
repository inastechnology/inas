# ina-device-hub

`ina-device-hub` is a lightweight IoT hub for INAS. It receives MQTT data from
client devices, stores and normalizes device events and measurements, serves a
local admin UI/API, and integrates with Turso/libSQL and S3-compatible storage.

Japanese version:

- [doc/jp/README.md](doc/jp/README.md)

Cross-project specification:

- [../docs/SYSTEM_SPECIFICATION.md](../docs/SYSTEM_SPECIFICATION.md)

## Main Capabilities

- Receive and process MQTT device status and telemetry.
- Store `farm/{device_id}/telemetry` payloads.
- Serve device runtime configuration through MQTT request/reply/push flows.
- Store images, audio, firmware artifacts, and logs locally or in
  S3-compatible storage.
- Integrate with Turso/libSQL.
- Generate timelapse content and schedule periodic jobs.
- Publish Instagram Reels from timelapse output when configured.
- Serve a local Flask-based admin UI.
- Register OTA firmware artifacts and deliver `firmware.bin` over HTTP.

## Quick Start

1. Install rye if needed: https://rye.astral.sh/guide/installation/

2. Install dependencies:

```bash
rye sync
```

3. Create environment configuration:

```bash
cp .default.env .env
# Edit .env for your environment.
```

4. Create the database if needed:

```bash
rye run db:create
```

5. Run the local hub:

```bash
rye run serve
# Default: http://localhost:39151
```

## Admin UI Demo

When no real device data exists, run the demo UI server. It starts only the
Flask web UI and does not connect to MQTT or devices.

```bash
python scripts/run_admin_demo_server.py
```

Open:

```text
http://127.0.0.1:39251/demo/mqtt-devices
```

The demo shows sample WTR/WRS devices, irrigation history, soil moisture charts,
wake history, and device detail navigation. Demo operations are not persisted.
The real admin UI remains `/mqtt-devices`.

## systemd Operation

This repository includes a systemd template unit and installer:

- `systemd/inas-device-hub@.service`
- `scripts/install_service.sh`

Install with:

```bash
sudo ./scripts/install_service.sh
```

Install with custom user or directory:

```bash
sudo ./scripts/install_service.sh --user mysvcuser --target-dir /opt/ina-device-hub
```

Install and enable Cloudflare Tunnel service support:

```bash
sudo ./scripts/install_service.sh --target-dir "$PWD" --enable-cloudflare-tunnel
```

Check service state:

```bash
systemctl status inas-device-hub@main
journalctl -u inas-device-hub@main -f
```

Helper scripts:

```bash
sudo ./scripts/hub_service.sh start
sudo ./scripts/hub_service.sh restart
./scripts/hub_service.sh status
./scripts/hub_service.sh logs
```

## Cloudflare Hosted Options

INAS has two Cloudflare-related operating modes:

- Tunnel option: run the local hub on the device side and expose it through
  Cloudflare Access + Tunnel.
- Cloud app option: run a Cloudflare Workers + Hono + Turso management API/UI
  foundation. This does not replace all local hub features.

Related docs:

- [doc/NETWORK_ARCHITECTURE.md](doc/NETWORK_ARCHITECTURE.md)
- [doc/CLOUDFLARE_HOSTED_OPTION.md](doc/CLOUDFLARE_HOSTED_OPTION.md)
- [doc/CLOUDFLARE_CLOUD_APP_IMPLEMENTATION.md](doc/CLOUDFLARE_CLOUD_APP_IMPLEMENTATION.md)
- [doc/AI_AGENT_ENVIRONMENT_SETUP.md](doc/AI_AGENT_ENVIRONMENT_SETUP.md)

Provision Access, Tunnel, and DNS resources from `.env`:

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
```

Start the local hub and tunnel in the foreground:

```bash
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

Manage allowed emails and the tunnel:

```bash
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
bash scripts/cloudflare_tunnel_start.sh
bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start
bash scripts/cloudflare_tunnel_daemon.sh status
```

Cloudflare Error 1033 usually means the Tunnel connector is not running or
cannot reach the origin. Check:

```bash
bash scripts/cloudflare_tunnel_daemon.sh status
```

## Cloud App Development

```bash
cd cloudflare
npm install
npm test
npm run typecheck
```

## Field Data And Improvement Loop

The hub field UI stores crop name, cultivar, growth stage, cultivation method,
soil/media, target ranges, control policy, reference information, and device
placement. Devices can be linked to the whole field, a section, a ridge/bed, or
a point.

The hub uses the latest measurements and field targets to create action
candidates. Currently, only WTR/WRS irrigation can be executed from the hub. Liquid
fertilizer and misting are recorded as future device candidates.

Related docs:

- [doc/AGRI_IMPROVEMENT_LOOP.md](doc/AGRI_IMPROVEMENT_LOOP.md)
- [doc/HUB_ADMIN_UX_IMPLEMENTATION.md](doc/HUB_ADMIN_UX_IMPLEMENTATION.md)

## Local File Migration

Export untracked local files such as `.env`, device JSON files, `data/`, and
`logs/`:

```bash
rye run local-files list
rye run local-files export-zip /tmp/ina-device-hub-local-files.zip
rye run local-files import-zip /tmp/ina-device-hub-local-files.zip --overwrite
```

Include `WORK_DIR` with:

```bash
rye run local-files export-zip /tmp/ina-device-hub-local-files.zip --include-work-dir
rye run local-files import-zip /tmp/ina-device-hub-local-files.zip --include-work-dir --overwrite
```

Move local files from an old device:

```bash
rye run local-files move-device \
  --source-dir /mnt/old-device/path/to/ina-device-hub \
  --target-dir /path/to/ina-device-hub \
  --source-work-dir /mnt/old-device/path/to/.ina-device-hub \
  --target-work-dir /path/to/.ina-device-hub \
  --overwrite
```

Use `--dry-run` to preview and `--no-work-dir` to skip `WORK_DIR`.

## Development Workflow

```bash
rye run format
rye run lint
```

## Important Files

- `pyproject.toml`: Python dependencies and rye scripts.
- `src/ina_device_hub/`: hub implementation.
- `cloudflare/`: Cloudflare Workers + Hono + Turso cloud app foundation.
- `doc/`: hub-level design and operations docs.
- `systemd/inas-device-hub@.service`: systemd template unit.
- `scripts/install_service.sh`: systemd installer.

## Environment Variables

See `src/ina_device_hub/setting.py` and [doc/ENVIRONMENT.md](doc/ENVIRONMENT.md)
for the full list. Commonly required groups:

- Turso: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
- S3-compatible storage: `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`,
  `S3_BUCKET_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- MQTT: `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`,
  `MQTT_BROKER_PASSWORD`
- Weather recording: `WEATHER_RECORD_ENABLED`,
  `WEATHER_RECORD_INTERVAL_SECONDS`, `WEATHER_PROVIDER`,
  `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_TIMEZONE`
- Cloudflare hosted option: `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`,
  `CLOUDFLARE_ACCESS_TEAM_DOMAIN`, `CLOUDFLARE_ACCOUNT_ID`,
  `CLOUDFLARE_ACCESS_API_TOKEN`
- OTA firmware URLs: `FIRMWARE_BASE_URL`, `FIRMWARE_HOSTNAME`,
  `FIRMWARE_PORT`, `HUB_HTTP_PORT`

## MQTT Device Configuration

- Devices publish requests to `/<device_id>/kinds/config/request`.
- The hub replies on `/<device_id>/kinds/config/reply`.
- Immediate updates can be published to `/<device_id>/kinds/config/push`.
- Config is stored in `WORK_DIR/.device_configs.json`.

## Farm Telemetry

- The hub subscribes to `farm/+/telemetry`.
- Payloads are parsed as JSON and stored as the latest value per `device_id`.
- `soil_moisture_*`, `soil_temp_c`, `battery_v`, `rssi`, and `timestamp` are
  stored under `latest_sensor_data.extra.telemetry`.
- `soil_temp_c` is also reflected to `latest_sensor_data.temp` for existing
  temperature chart compatibility.
- `null` values are accepted; missing values must not crash ingestion.
- The device detail view shows last receive time, voltage threshold status, and
  stale-device checks.

## Measurement Normalization

- Measurements extracted from MQTT device status are stored vertically in
  `sensor_measurements`.
- Metric display names, units, and supported device kinds are defined in
  `sensor_measurement_definitions`.
- Initial definitions include SOI/WTR soil moisture, ENV PAR, soil moisture,
  soil temperature, EC, pH, N/P/K, and future irradiance metrics.
- `latest_sensor_data` remains for compatibility, while multi-metric ENV data
  should use `sensor_measurements`.

## Local API

`PUT /local/api/device-configs/<device_id>?push=true` stores config JSON and
publishes a push update after saving.

## NTP Operation

- Run the NTP server as an OS service on the same PC as the MQTT hub when
  needed.
- `ntp_server` must be a hostname or fixed IP address resolvable by firmware.
- Devices must be able to reach UDP 123 on the local network.
- The hub only distributes the `ntp_server` value. Actual NTP service should be
  provided by existing software such as `chronyd` or `ntpd`.

## License

MIT. See `LICENSE`.
