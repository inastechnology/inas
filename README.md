# INAS

Japanese documentation: [docs/jp/README.md](docs/jp/README.md)

INAS is an agriculture platform for observing field conditions, operating
irrigation equipment, managing device settings and firmware, and recording the
results of farm work. This monorepo contains the complete platform: ESP32-S3
device firmware, the Local Hub, the field-side Edge Gateway, the shared Cloud
Hub, common contracts, extensions, and user documentation.

The system is designed to keep MQTT communication and safety-critical device
operation on the field LAN. A site can operate devices directly from a Local
Hub or use an Edge Gateway that synchronizes with one parent Local Hub or Cloud
Hub over outbound HTTPS.

Start with [INAS System Specification](docs/SYSTEM_SPECIFICATION.md) for the cross-project
architecture, device roles, field data model, OTA flow, and Cloudflare hosted
options. The draw.io source for the system diagrams is
[docs/assets/inas_system_diagrams.drawio](docs/assets/inas_system_diagrams.drawio).
Documentation writing and localization rules are defined in
[docs/DOCUMENTATION_GUIDE.md](docs/DOCUMENTATION_GUIDE.md).
System-wide layer boundaries are defined in
[docs/ARCHITECTURE_LAYERING_POLICY.md](docs/ARCHITECTURE_LAYERING_POLICY.md).
Planned and community-proposed work is indexed in
[docs/FUTURE_FEATURES.md](docs/FUTURE_FEATURES.md).
Japanese documentation is stored under documentation directories such as
[docs/jp/README.md](docs/jp/README.md), [hub/doc/jp/README.md](hub/doc/jp/README.md),
and [client-devices/docs/jp/README.md](client-devices/docs/jp/README.md).

## System overview

![INAS system architecture](docs/assets/inas_system_architecture.svg)

```text
INAS devices -- MQTT --> Local Hub

INAS devices -- MQTT --> Edge Gateway -- Sync v1 HTTPS --> Local Hub or Cloud Hub
```

The Hub combines device status, measurements, irrigation history, field and
crop context, work records, Runtime Config, and OTA updates in one operator
interface. See the
[INAS System Specification](docs/SYSTEM_SPECIFICATION.md) for the complete
architecture, data flow, device roles, storage boundaries, and current feature
scope.

## Repository layout

| Path | Purpose |
|---|---|
| [`hub/`](hub/README.md) | Local Hub: Flask UI/API, MQTT processing, scheduling, storage integration, and OTA delivery |
| [`hub-cloud/`](hub-cloud/README.md) | Shared Cloudflare Workers Cloud Hub with authenticated tenant routing and one database per customer |
| [`edge-gateway/`](edge-gateway/README.md) | Field appliance: local MQTT broker integration, configuration cache, durable outbox, and parent synchronization |
| [`client-devices/`](client-devices/README.md) | PlatformIO firmware for WTR, WRS, FGT, SOI, and ENV devices, plus the shared firmware library |
| [`shared/`](shared/README.md) | Language-neutral Sync contracts and the Python edge runtime shared by the Hub and Gateway |
| [`extensions/`](extensions/README.md) | Declarative, build-time Hub UI extensions |
| [`docs-site/`](docs-site/README.md) | Japanese-first public setup, operation, and troubleshooting website |
| [`docs/`](docs/README.md) | Cross-project specifications, architecture policies, and editable system diagrams |
| [`lp/`](lp/README.md) | Product landing page and its deployable assets |
| [`pitch-deck/`](pitch-deck/) | Product presentation sources and generated artifacts |

## Installation and first run

This is a multi-component repository; there is no repository-wide installer.
Install dependencies from the directory of the component you intend to run.

### Prerequisites

- Git
- Python 3.11 or later and
  [uv](https://docs.astral.sh/uv/getting-started/installation/) for the Local
  Hub, Edge Gateway, and shared Python runtime
- Node.js 22 and npm for the Cloud Hub, admin UI, documentation site, and
  product web assets
- Linux or WSL2, GNU Make, and PlatformIO for client firmware builds

Client firmware uses symbolic links for local PlatformIO libraries. Native
Windows firmware builds are not supported; use WSL2 and clone the repository
inside the Linux filesystem rather than under `/mnt/c`.

### Clone the repository

```bash
git clone https://github.com/inastechnology/inas.git
cd inas
```

### Run the Local Hub

```bash
cd hub
uv sync
uv run ina-hub install
uv run python src/ina_device_hub/serve.py
```

The default local URL is `http://localhost:39151`. The installation command
creates the Hub environment configuration interactively. MQTT, database,
object storage, Cloudflare, and production service settings are documented in
the [Hub README](hub/README.md) and
[Hub operations documentation](hub/doc/OPERATIONS.md).

### Build client firmware

The following example builds the WTR watering device:

```bash
cd client-devices/watering-device
cp default.env.user.ini .env.user.ini
make build
```

Run `make upload` to flash a connected development device or
`make merged-bin` to produce a distributable image. Hardware preparation,
wiring, per-device build targets, and manufacturing steps are indexed from the
[client device documentation](client-devices/README.md).

### Start another component

| Goal | Initial dependency command | Detailed guide |
|---|---|---|
| Develop the Edge Gateway | `cd edge-gateway && uv sync --frozen` | [Edge Gateway README](edge-gateway/README.md) |
| Develop or test the Cloud Hub | `cd hub-cloud && npm ci` | [Cloud Hub README](hub-cloud/README.md) |
| Preview the public documentation | `cd docs-site && npm ci && npm run dev` | [Documentation site README](docs-site/README.md) |
| Build the Hub admin UI | `cd hub/admin-ui && npm ci && npm run build` | [Hub README](hub/README.md) |

## Documentation

For installation, configuration, daily operation, firmware updates, and
troubleshooting, start with the task-oriented
[INAS user documentation](https://docs.inas-technologies.com/). Its source and
local preview instructions are in [`docs-site/`](docs-site/README.md).

Developers should use these entry points instead of adding implementation
details to this README:

- [System specification](docs/SYSTEM_SPECIFICATION.md)
- [Architecture layering policy](docs/ARCHITECTURE_LAYERING_POLICY.md)
- [Device Definition specification](docs/DEVICE_DEFINITION_SPECIFICATION.md)
- [Hub Extension specification](docs/EXTENSION_SPECIFICATION.md)
- [Edge Gateway hardware and identity](docs/EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md)
- [Documentation index](docs/README.md)

Each component owns its dependencies, environment variables, tests, deployment
procedures, and security notes. Run commands from that component's directory
and follow its README before changing or deploying it. Never commit real
database tokens, MQTT credentials, Cloudflare secrets, device credentials, or
generated production configuration.
