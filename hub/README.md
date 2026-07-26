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
- Integrate with the Local Hub installation's configured Turso/libSQL replica.
- Generate timelapse content and schedule periodic jobs.
- Publish Instagram Reels from timelapse output when configured.
- Serve a local Flask-based admin UI.
- Register OTA firmware artifacts and deliver `firmware.bin` over HTTP.

## Design Notes

- [INAS future feature registry](../docs/FUTURE_FEATURES.md)
- [Drip irrigation calibration and substrate reset](doc/HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md)
- [AI Search documentation status](doc/AI_SEARCH_OPERATIONS.md)

## Quick Start

1. Install uv if needed: https://docs.astral.sh/uv/getting-started/installation/

2. Install dependencies:

```bash
uv sync
```

3. Create environment configuration:

```bash
uv run ina-hub install
```

4. Run the local hub. The local libSQL schema is prepared automatically:

```bash
uv run python src/ina_device_hub/serve.py
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
http://127.0.0.1:39251/fields/demo-strawberry-field/layout
http://127.0.0.1:39251/fields/demo-strawberry-field/calendar
http://127.0.0.1:39251/inas-app
```

Capture the current 16:9 product tour from the running demo server. The Japanese
and English editions share one scene plan, while their explanatory telops are
rendered independently:

```bash
HUB_URL=http://127.0.0.1:39251 npm --prefix admin-ui run capture:demo-video:ja
HUB_URL=http://127.0.0.1:39251 npm --prefix admin-ui run capture:demo-video:en
```

Both commands write a silent master and an exact scene timeline under
`/tmp/inas-demo-video/`. The shared script and narration copy live in
`admin-ui/scripts/demo-video/tour.json`. The English capture opens the real
`?lang=en` Hub mode, so the field dashboard, work board and review flow, and
irrigation pages are English in addition to the telops and narration. These
surfaces expose a `JA / EN` selector; Japanese remains the default.

With the fresh demo server running, verify that all four English tour pages and
the manager-review dialog contain no visible Japanese text before capture:

```bash
HUB_URL=http://127.0.0.1:39251 npm --prefix admin-ui run smoke:demo-english-ui
```

The finished LP media uses a wordless BGM generated with ComfyUI ACE-Step 1.5
and local Windows SAPI voices. With ComfyUI listening on port 8188, generate the
fixed-seed music bed and then render both editions:

```bash
python admin-ui/scripts/demo-video/generate_comfy_bgm.py
python admin-ui/scripts/demo-video/render_demo_media.py --locale ja --update-compatibility
python admin-ui/scripts/demo-video/render_demo_media.py --locale en
```

The default BGM path is `/tmp/inas-demo-video/inas-demo-bgm.flac`. When ComfyUI
runs as a Windows process and is not reachable from WSL localhost, run the BGM
script with ComfyUI's embedded Windows Python and pass an output path visible
from WSL; then supply that file with `--bgm` to both render commands. Rendering
requires `ffmpeg`, `ffprobe`, PowerShell, and the `Microsoft Haruka Desktop` and
`Microsoft Zira Desktop` voices. It writes `demo-ja.mp4`, `demo-en.mp4`, their
posters, and WebVTT captions into `../lp/assets/`. The compatibility flag also
refreshes the legacy Japanese `demo.mp4` and `demo-poster.jpg` files.

The demo provides 13 bindable WTR, WRS, FGT, ENV, SOI, PAR, and camera devices, plus
irrigation history, soil moisture charts, wake history, and device detail
navigation. MQTT demo operations are not
persisted. The installation layout uses the demo work directory and can be
edited and saved while the demo server is running. A fresh demo work directory
is preloaded with a greenhouse, three ridges, a strawberry planting, a 12-month
work calendar, completed/in-progress/skipped examples, and fertilizer history.
The calendar is generated without calling an external LLM;
calendar edits, selected work dates, and plant questions can be exercised from
the same screen. The demo always uses the local libSQL file under
`HUB_DEMO_WORK_DIR` and does not inherit the production Turso URL from `.env`.
Set `HUB_DEMO_AI_TEXT_ANALYZE_API_KEY` only when an external calendar-generation
call is intentionally required. The real admin UI remains `/mqtt-devices`.

The installation layout also exposes Hub-local live collaboration. Editors of
the same field see active users, tabs, edit state, and remote selections. The
browser uses a short HTTP sync loop so the current Flask/Waitress deployment
does not need a WebSocket server. Layout JSON remains protected by revision
checks and three-way merge; presence is temporary process-local metadata and
never replaces the saved layout. Run the focused two-tab check against the demo
server with:

```bash
HUB_URL=http://127.0.0.1:39251 npm --prefix admin-ui run smoke:collaboration
```

The `/inas-app` route is the public product landing page and doubles as an A4
print brochure. To refresh its real Hub screenshots, first run `npm run smoke`
against an isolated demo server, then run `npm run capture:marketing`. Validate
the desktop, mobile, and three-page print outputs with `npm run smoke:marketing`.

Build the React/Konva installation layout after changing `admin-ui/src`:

```bash
cd admin-ui
npm install
npm run build
```

## Hub Extensions

Repository Extensions live under `../extensions/<name>/extension.json`. Validate
them and refresh the packaged registry after changing a manifest:

```bash
uv run python scripts/build_extension_registry.py
uv run python scripts/build_extension_registry.py --check
```

Extension API version 1 supports safe, declarative device-detail overview cards
and supplementary tabs. See
[`../docs/EXTENSION_SPECIFICATION.md`](../docs/EXTENSION_SPECIFICATION.md). The
running Hub reads the generated registry packaged under
`ina_device_hub/extensions/generated/` plus manifests explicitly installed by
an administrator from **App settings → Extensions**. Upload runs local static
checks only; a separate confirmation is required before optional AI review, and
installation is a final independent action. Neither source executes
Extension-owned code. See the
[security review policy](../docs/EXTENSION_SECURITY_REVIEW_POLICY.md).

With the demo server running on port 39252, the browser smoke test can be run
with `HUB_URL=http://127.0.0.1:39252 npm run smoke`.

## systemd Operation

This repository includes a systemd template unit and installer:

- `systemd/inas-device-hub@.service`
- `scripts/install_service.sh`

Install or update while preserving an existing `.env` and MQTT configuration:

```bash
sudo ./scripts/install_service.sh
```

Install with custom user or directory:

```bash
sudo ./scripts/install_service.sh --user mysvcuser --target-dir /opt/ina-device-hub
```

Install and enable Cloudflare Tunnel service support:

```bash
sudo ./scripts/install_service.sh --production --target-dir "$PWD" --enable-cloudflare-tunnel
```

Use `--production` only for the first Cloudflare production deployment or an
explicit Access/Tunnel reprovision. After pulling a normal update, omit it so
the installer validates but does not rewrite existing MQTT, HTTP,
authentication, database, or Cloudflare settings. See
[`doc/jp/OPERATIONS.md`](doc/jp/OPERATIONS.md).

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

## Cloudflare deployment modes

This Local Hub may be exposed through its optional Cloudflare Access + Tunnel
configuration. That does not change its existing Turso/libSQL database.

The separate [`../hub-cloud/`](../hub-cloud/README.md) application serves
customers who do not operate a Local Hub. It uses one shared Worker/frontend,
one directory DB, and one dedicated Turso DB per customer. Edge Gateways
synchronize to it over authenticated HTTPS; they never receive a Turso
credential.

Related docs:

- [doc/NETWORK_ARCHITECTURE.md](doc/NETWORK_ARCHITECTURE.md)
- [doc/CLOUDFLARE_HOSTED_OPTION.md](doc/CLOUDFLARE_HOSTED_OPTION.md)
- [doc/AI_AGENT_ENVIRONMENT_SETUP.md](doc/AI_AGENT_ENVIRONMENT_SETUP.md)

Provision Local Hub Access, Tunnel, and DNS resources from its existing `.env`:

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
bash scripts/migrate_local_files.sh list
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --overwrite
```

Include `WORK_DIR` with:

```bash
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip --include-work-dir
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --include-work-dir --overwrite
```

Move local files from an old device:

```bash
bash scripts/migrate_local_files.sh move-device \
  --source-dir /mnt/old-device/path/to/ina-device-hub \
  --target-dir /path/to/ina-device-hub \
  --source-work-dir /mnt/old-device/path/to/.ina-device-hub \
  --target-work-dir /path/to/.ina-device-hub \
  --overwrite
```

Use `--dry-run` to preview and `--no-work-dir` to skip `WORK_DIR`.

## Development Workflow

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
```

## Important Files

- `pyproject.toml`: Python dependencies and tool configuration.
- `src/ina_device_hub/`: hub implementation.
- `doc/`: hub-level design and operations docs.
- `systemd/inas-device-hub@.service`: systemd template unit.
- `scripts/install_service.sh`: systemd installer.

## Environment Variables

See `src/ina_device_hub/setting.py` and [doc/ENVIRONMENT.md](doc/ENVIRONMENT.md)
for the full list. Commonly required groups:

- Turso/libSQL: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`
- S3-compatible storage: `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`,
  `S3_BUCKET_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- MQTT: `MQTT_BROKER_URL`, `MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`,
  `MQTT_BROKER_PASSWORD`
- Weather recording: `WEATHER_RECORD_ENABLED`,
  `WEATHER_RECORD_INTERVAL_SECONDS`, `WEATHER_PROVIDER`,
  `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_TIMEZONE`
- Cloudflare Local Hub option: `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`,
  `CLOUDFLARE_ACCESS_TEAM_DOMAIN`, `CLOUDFLARE_ACCOUNT_ID`,
  `CLOUDFLARE_ACCESS_API_TOKEN`
- OTA firmware URLs: `FIRMWARE_BASE_URL`, `FIRMWARE_HOSTNAME`,
  `FIRMWARE_PORT`, `HUB_HTTP_PORT`

## MQTT Device Configuration

- Devices publish requests to `/<device_id>/kinds/config/request`.
- The hub replies on `/<device_id>/kinds/config/reply`.
- Immediate updates can be published to `/<device_id>/kinds/config/push`.
- Config business records remain in `WORK_DIR/.device_configs.json`.
- Effective device runtime config is mirrored into the revisioned local Edge
  cache at `WORK_DIR/edge-runtime/edge.db`; the Local Hub identity is persisted
  separately at `WORK_DIR/edge-runtime/identity.json`.
- A cache failure falls back to the validated JSON record, so a device config
  reply does not depend on Turso or WAN availability.
- The same local database provides a durable event outbox. Standalone Local
  Hubs continue using their existing event logs; parent-bound enqueueing is
  enabled together with parent Sync enrollment so an unconsumed outbox cannot
  grow indefinitely.

## Hierarchical Sync

A Local Hub can act as a Sync v1 parent for Edge Gateways or other Local Hubs
while remaining the MQTT controller for its directly connected devices. It can
also initiate outbound Sync v1 exchanges to one upstream Local Hub.
The upstream connection is outside the local MQTT safety loop: cached runtime
configuration, direct commands, readiness, and field operation continue while
the WAN or parent is unavailable.

Child enrollment returns a bearer token exactly once:

```text
POST /local/api/hierarchy/children/enrollments
POST /local/api/hierarchy/children/<node_id>/revoke
POST /sync/v1/nodes/<node_id>/exchange
```

Node Sync authentication is separate from browser and Cloudflare Access
authentication. Production parent URLs require HTTPS and a node bearer-token
file; optional mTLS private keys are also read only from absolute private
files. See
[the Japanese Sync v1 operations guide](doc/jp/HIERARCHICAL_SYNC.md) for the
topology, enrollment flow, API list, security boundary, and outage behavior.

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
