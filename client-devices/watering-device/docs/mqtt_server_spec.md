# MQTT Server Integration Specification

Japanese version: [jp/mqtt_server_spec.md](jp/mqtt_server_spec.md)

This document defines the MQTT integration contract for the INA watering
device firmware and the hub-side application server.

## Scope

The MQTT broker can be any standard MQTT broker. The hub application connects
to the broker and implements the device workflow:

- receive runtime configuration requests from devices
- reply with the current runtime configuration
- optionally publish retained runtime configuration updates
- receive and store device status messages
- receive debug logs when enabled
- manage OTA offers and OTA status messages

## MQTT Connection

The firmware uses Arduino `PubSubClient`.

| Item | Requirement |
|---|---|
| Protocol | MQTT 3.1.1 compatible |
| QoS | QoS 0 |
| Retain | Optional; recommended only for config push and OTA offer |
| Client ID | Device `device_id` |
| Authentication | Either no username/password, or both username and password |
| TLS | Not supported by the current firmware |
| Default port | `1883` |

When the configured username is empty, the firmware connects without
username/password. When the username is present, both username and password are
sent.

## Topic Model

Generic application topics use this shape:

```text
/<device_id>/kinds/<kind>/<mode>
```

Example:

```text
/INADS-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx/kinds/config/request
```

`device_id` is generated per device and uses this format:

```text
INADS-<uuid>
```

The hub must parse `device_id` from the topic and treat it as the primary
device identifier.

| Kind | Mode | Direction | Purpose |
|---|---|---|---|
| `config` | `request` | Device -> Hub | Runtime configuration request |
| `config` | `reply` | Hub -> Device | Runtime configuration response |
| `config` | `push` | Hub -> Device | Optional server-initiated configuration update |
| `agri` | `immediate` | Device -> Hub | Status publish, using the default build settings |
| `debug` | `log` | Device -> Hub | Wake-cycle debug log publish |
| `ota` | `status` | Device -> Hub | OTA progress and result |

The default status topic kind/mode is controlled by build flags:

```text
APP_MQTT_PUB_KIND=agri
APP_MQTT_PUB_MODE=immediate
```

OTA offers use the newer device-kind-aware topic:

```text
/kinds/<device_kind>/devices/<device_id>/ota/offer
```

The watering device kind is `WTR`.

## Hub Subscriptions

The hub application should subscribe to these topics at minimum:

```text
/+/kinds/config/request
/+/kinds/agri/immediate
/+/kinds/debug/log
/+/kinds/ota/status
/kinds/+/devices/+/ota/offer
```

For broad diagnostics, `/+/kinds/+/+` can also be subscribed, but the
application should still route messages by explicit kind/mode.

## Device Registration

The current firmware has no separate registration API. The hub should treat the
first valid MQTT message as the registration trigger.

Recommended flow:

1. Subscribe to `/+/kinds/config/request`.
2. Receive a request from an unknown `device_id`.
3. Create a device record in `pending` state.
4. Reply with a safe default runtime configuration.
5. Let an operator set the name, location, and runtime configuration.
6. Move the device to `active`.

Recommended states:

| State | Meaning | Hub behavior |
|---|---|---|
| `pending` | First request received, not approved yet | Store status and return a safe default config |
| `active` | Approved production device | Return the saved runtime config |
| `disabled` | Stopped or suspicious device | Return no config, or only a no-watering safe config |
| `retired` | Removed device kept for history | Store messages but exclude from normal operation |

Broker connection events should not be the primary registration trigger because
broker-specific event APIs differ. `config/request` is the portable trigger that
the hub application can reliably observe.

## Runtime Configuration Request

The firmware requests runtime configuration after network and MQTT connection.

Request topic:

```text
/<device_id>/kinds/config/request
```

Request payload:

```json
{"request":"runtime_config"}
```

Reply topic:

```text
/<device_id>/kinds/config/reply
```

Timing requirements:

- The device waits about 5 seconds after publishing the request.
- The hub should reply immediately after receiving the request.
- If no valid reply arrives in time, the device may continue with the saved
  runtime configuration or its firmware default.

## Runtime Configuration Push

The hub may publish a configuration without waiting for a request:

```text
/<device_id>/kinds/config/push
```

Use `config/push` when the latest configuration should be retained in the
broker for the next wake cycle. The hub should still implement `config/reply`
for deterministic request/response synchronization.

## Runtime Configuration Payload

The payload is JSON. The firmware ignores unknown fields, so the hub may add
server-side metadata only when payload size remains safe.

Example:

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 40,
  "force_watering": false,
  "debug_log_on_wake": false,
  "ota_check_interval_sec": 21600,
  "watering_pattern": {
    "enabled": true,
    "on_sec": 60,
    "off_sec": 60,
    "cycles": 1
  },
  "mosfet_switches": [
    {
      "switch_id": "irr1",
      "name": "Strawberry drip line A",
      "enabled": true,
      "role": "irrigation",
      "terminal": "IRR1",
      "channel_mask": 1,
      "controlled_load": "12V solenoid valve"
    },
    {
      "switch_id": "sensor_power",
      "name": "RS485 sensor power",
      "enabled": true,
      "role": "sensor_power",
      "terminal": "SENSOR_12V_SW",
      "channel_mask": 0,
      "controlled_load": "RS485 sensor branch"
    }
  ],
  "schedules": [
    {
      "hour": 6,
      "minute": 0,
      "duration_sec": 120,
      "channel_mask": 1,
      "frequency": {
        "mode": "daily"
      }
    }
  ]
}
```

Validation requirements before publish:

- payload is valid JSON
- MQTT payload is less than 4096 bytes
- `schedules` is an array
- at least one valid schedule exists
- schedule count is 8 or less
- `hour` is `0..23`
- `minute` is `0..59`
- `duration_sec` is `1` or greater
- `channel_mask` is `1` or greater
- `frequency.mode` is omitted, `daily`, `interval`, or `weekdays`
- `interval_days` is `1..31` when `frequency.mode` is `interval`
- `start_date` is `YYYY-MM-DD` when interval scheduling is used
- weekdays contain at least one value and each value is `0..6`
- `moisture_threshold` is `0..100`
- `timezone_offset_sec` matches the operating region
- `mosfet_switches`, when present, is an output inventory for hub management:
  `switch_id` is unique, `name` is farmer-facing, `terminal` is the physical
  terminal label, `controlled_load` records the connected load, and
  `channel_mask` is `0` for non-scheduled switches such as sensor power

The firmware ignores invalid schedule entries. If no valid schedule remains, it
does not apply the configuration.

## Status Publish

The device publishes status at the end of each wake cycle. The WTR firmware
measures soil moisture on every wake cycle, even when no watering schedule is
due. The measured value is included as `last_soil_moisture`.

Default topic:

```text
/<device_id>/kinds/agri/immediate
```

Representative payload fields:

| Field | Meaning |
|---|---|
| `device_id` | Device identifier |
| `config_received` | Whether a valid runtime config was received in this cycle |
| `runtime_config_valid` | Whether a saved or received config is usable |
| `network_connected` | Network connection result |
| `mqtt_connected` | MQTT connection result |
| `time_synced` | NTP synchronization result |
| `watering_due` | Whether a schedule was due |
| `watering_started` | Whether watering output was started |
| `last_soil_moisture` | Soil moisture measured during this wake cycle |
| `threshold` | Active soil moisture threshold |
| `next_sleep_sec` | Planned sleep duration |
| `firmware_version` | Running firmware version |

Operational interpretations:

| Condition | Interpretation |
|---|---|
| `config_received=false` | No reply arrived in time, or the payload was invalid |
| `runtime_config_valid=true`, `config_received=false` | Device is operating with saved config |
| `time_synced=false` | Schedule execution is skipped because time is unreliable |
| `watering_due=true`, `watering_started=false` | Schedule was due, but watering was blocked or output failed |
| `watering_due=false` | No schedule matched the current time |

Even when `watering_due=false`, `last_soil_moisture` is still the latest soil
moisture measurement and should be stored as a time-series value.

## Debug Log

When `debug_log_on_wake` is `true`, the device publishes a debug log at the end
of the wake cycle.

Default topic:

```text
/<device_id>/kinds/debug/log
```

The hub should parse the JSON payload and store it separately from normal
status data. Debug logs are intended for diagnostics, not the main farmer-facing
dashboard.

## OTA

Firmware binaries are not transferred through MQTT. The hub serves firmware via
HTTP and MQTT only carries the OTA offer/status workflow.

See [ota_update_spec.md](ota_update_spec.md) for the detailed OTA contract.

Current OTA rules:

- The hub serves the firmware binary from its HTTP server.
- The hub builds the firmware URL from `FIRMWARE_BASE_URL` or hosted hostname
  configuration.
- The firmware currently accepts `http://` firmware URLs.
- The hub must not offer an artifact when the artifact `device_kind` differs
  from the requesting device kind.
- The device checks OTA after runtime config retrieval and before watering.
- A wake cycle that starts OTA update must not run watering.
- OTA requires an OTA-capable partition layout.

## Recommended Hub Data Model

Store at least the current runtime configuration and recent telemetry per
device.

Recommended device fields:

| Field | Description |
|---|---|
| `device_id` | Primary device identifier |
| `device_kind` | Fixed device kind such as `WTR` |
| `state` | `pending`, `active`, `disabled`, or `retired` |
| `name` | Operator-facing name |
| `location` | Installation location |
| `memo` | Optional note |
| `runtime_config` | Current runtime configuration JSON |
| `first_seen_at` | First received message timestamp |
| `last_seen_at` | Last received message timestamp |
| `last_config_request_at` | Last config request timestamp |
| `last_config_reply_at` | Last config reply timestamp |
| `last_status_at` | Last status timestamp |
| `last_status` | Last status payload |
| `created_at` | Record creation timestamp |
| `updated_at` | Record update timestamp |
| `approved_at` | Approval timestamp |
| `approved_by` | Operator who approved the device |

Keep runtime configuration history in a separate table or log so changes can be
audited and rolled back.

## Safe Default Configuration

For unknown or pending devices, return a valid configuration that does not cause
unexpected watering. The firmware rejects an empty `schedules` array, so include
one valid schedule and set `moisture_threshold` low enough to suppress watering.

Example:

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "moisture_threshold": 0,
  "force_watering": false,
  "debug_log_on_wake": false,
  "schedules": [
    {
      "hour": 6,
      "minute": 0,
      "duration_sec": 1,
      "channel_mask": 1,
      "frequency": {
        "mode": "daily"
      }
    }
  ]
}
```

## Admin Operations

The hub UI or API should support these operations:

| Operation | Purpose |
|---|---|
| List devices | Show state, name, location, last seen, and health |
| Approve device | Move `pending` to `active` |
| Disable device | Stop a device without deleting history |
| Retire device | Remove a device from normal operation |
| Update metadata | Edit name, location, and memo |
| Get runtime config | Inspect current configuration |
| Update runtime config | Validate and save a new configuration |
| Push runtime config | Publish optional `config/push` |
| List statuses | Inspect status history |
| List audit logs | Inspect operator actions |

Configuration updates and device disabling should require an operator or admin
role. Viewing status can be allowed for viewer roles.

## Health Monitoring

Compute device health from status and expected wake timing.

Recommended states:

| Health | Meaning |
|---|---|
| `ok` | Recent status is normal and arrived within the expected window |
| `warning` | One missed status, config failure, or time sync failure |
| `critical` | Repeated missing status, repeated NTP failure, or repeated config failure |
| `disabled` | Device state is `disabled` or `retired` |

Monitor at least:

- status missing after the expected wake time plus a grace period
- repeated `config_received=false`
- repeated `time_synced=false`
- repeated `watering_due=true` and `watering_started=false`
- `last_soil_moisture` staying below threshold for too long
- abnormal `next_sleep_sec`

## Compatibility Notes

- The firmware discards runtime configuration payloads that are too large.
- The firmware only treats `config/reply` and `config/push` topics addressed to
  its own `device_id` as runtime configuration.
- `config/request` is device-to-hub only.
- There is no dedicated config ACK topic. Use `status.config_received` and
  `status.runtime_config_valid` to determine the result.
- Current OTA uses retained `ota/offer` and `ota/status`. Legacy
  `ota/request`/`ota/reply` support may remain on the hub for older firmware.
