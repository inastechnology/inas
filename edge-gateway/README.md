# INAS Edge Gateway

`ina-edge-gateway` is the standalone field appliance used between INAS client
devices and one parent Local Hub or Cloud Hub. MQTT remains on the isolated
field LAN.
The Gateway initiates outbound Sync v1 HTTPS exchanges and never receives
Turso, tenant-routing, Cloudflare administrative, or cloud MQTT credentials.

```text
INADS devices -- local MQTT --> Edge Gateway -- outbound HTTPS --> one parent
                       ^             |
                       |             +-- SQLite config cache/outbox
                       +-- config reply and retained config push
```

## Implemented runtime

- strict, provisioned `INAEG-<UUIDv4>` identity loading;
- local Mosquitto MQTT 3.1.1 client;
- cached runtime-config replies with the existing topic/QoS/retain contract;
- restart-safe telemetry/status outbox;
- bounded, authenticated Sync v1 HTTP transport;
- correlation, target-node, acknowledgement, revision, and command validation;
- expiring/idempotent command inbox and durable terminal results;
- read-only `/healthz`, `/readyz`, and `/maintenance/v1/status`;
- systemd watchdog notification.

The first executable command is `device.runtime_config_push`. Arbitrary actuator
commands are rejected until their safety and idempotency contracts are defined.
An expired command is never published. If the process stops after command
activation, a `running` command is reported as `execution_interrupted` rather
than being replayed blindly.

## Development

```bash
uv sync --frozen
TMPDIR=/tmp uv run python -m unittest discover -s tests -p 'test_*.py'
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv build
```

Create a development identity only when manufacturing provisioning is not
available:

```bash
uv run ina-edge-gateway bootstrap-development-identity \
  --path /tmp/inas-edge-development/identity.json
```

Production identities and keys are provisioned during manufacturing. The
development command must not be used to replace a lost production identity.

Copy `config/edge-gateway.example.json` to a protected location, use absolute
paths, and validate it before starting:

```bash
uv run ina-edge-gateway check-config --config /etc/inas/edge-gateway.json
uv run ina-edge-gateway run --config /etc/inas/edge-gateway.json
```

`parent: null` is the unclaimed/offline state. Local MQTT, health, and cached
operation remain available, but no parent outbox acknowledgement occurs. The
claim flow will write an authenticated HTTPS parent configuration after the
operator scans the Gateway QR code through Hub or the optional Flutter console.

For Cloud Hub shipments, the factory workflow under `../hub-cloud/` assigns the
customer, registers the node, and emits the protected identity/config/credential
overlay:

```bash
cd ../hub-cloud
npm run gateway:kit
```

Credential values never belong in the JSON config. MQTT and parent bearer
credentials are read from separate mode-0600 files. HTTPS may instead use a
client certificate and key. Plain HTTP is rejected except for an explicitly
enabled loopback-only development parent.

## Appliance fixtures

`deployment/` contains templates and policy fixtures for a Raspberry Pi or
Compute Module image:

- NetworkManager AP on `192.168.50.1/24`, WPA2, client isolation, no shared/NAT
  mode;
- dnsmasq DHCP/local names and chrony service for the device LAN;
- nftables input allow-list and unconditional device-interface forwarding drop;
- authenticated Mosquitto listener with Gateway and per-INADS topic ACLs;
- hardened systemd service, `/var/lib/inas`, watchdog, and mode-0700 state;
- optional SORACOM NetworkManager template.

Files containing `@@...@@` are templates and must be rendered during secure
provisioning. They are not directly installable and contain no usable password,
claim code, SIM identity, or token. The repository does not include a command
that writes an OS image or chooses a block device.

The maintenance API intentionally exposes no mutation endpoint or credential
material. Readiness depends on the local MQTT control loop, not WAN or billing,
so a parent outage does not mark field control unavailable.

To stage a source bundle without touching the host OS:

```bash
python3 scripts/stage_appliance_bundle.py --output /tmp/inas-edge-bundle
cd /tmp/inas-edge-bundle/edge-gateway
uv sync --frozen --no-dev
```

The output directory must be new and outside the repository. The command refuses
the filesystem root, home directory, repository paths, and existing targets. It
copies the canonical shared Runtime beside the Gateway and writes
`MANIFEST.sha256`; it never installs system services or selects a block device.
