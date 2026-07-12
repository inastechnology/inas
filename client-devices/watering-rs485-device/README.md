# WRS Watering RS485 Device

Device kind: `WRS`

Project status: first firmware implementation.

`WRS` is the RS485-first all-in-one watering device. It controls local 12V
watering MOSFET outputs, switches 12V sensor power, reads RS485 sensors through
the common bus abstraction, and publishes WTR/ENV-compatible measurement names
to the hub.

## Hardware Boundary

Default XIAO ESP32S3 pin assignment:

| Signal | XIAO pin | GPIO | Purpose |
|---|---:|---:|---|
| Irrigation output 1 MOSFET | `D2` | `GPIO3` | Watering channel 1 |
| Irrigation output 2 MOSFET | `D3` | `GPIO4` | Watering channel 2 |
| RS485 DE/RE | `D4` | `GPIO5` | MAX485 transmit/receive direction |
| RS485 TX | `D6` | `GPIO43` | UART TX to MAX485 DI |
| RS485 RX | `D7` | `GPIO44` | UART RX from MAX485 RO |
| 12V sensor power MOSFET | `D8` | `GPIO7` | Switches 12V to RS485 sensors |

The analog soil moisture ADC is not used by WRS. Soil feedback is expected from
an RS485 Modbus soil sensor.

## Firmware Layers

Layer boundaries follow
[../docs/firmware_layering_policy.md](../docs/firmware_layering_policy.md).

- `hal_power_switch`: common switched MOSFET/power control. WRS uses separate
  instances for irrigation output 1, irrigation output 2, and 12V sensor power.
- `hal_rs485_bus`: common RS485 bus boundary.
- `hal_rs485_sensor_protocol`: common Modbus register mapping for RS485 soil
  and PAR sensors.
- `app_wrs_runtime_config`: WRS runtime config, schedule parsing, persistence.
- `app.cpp`: WRS cycle orchestration.

## Runtime Behavior

Each wake cycle:

1. Requests runtime config from the hub.
2. Powers RS485 sensors and reads soil/PAR values.
3. Checks whether a watering schedule is due, or whether WRS auto watering is
   enabled and soil moisture is below threshold.
4. Starts watering only when enabled, selected channels are valid, and soil
   feedback rules allow it.
5. Waters in short chunks, re-reading RS485 soil moisture after each chunk.
6. Stops when the configured target moisture is reached, feedback is lost, or
   the duration limit is reached.
7. Publishes status and measurement values, then sleeps.

## Runtime Config

WRS accepts the existing WTR/ENV fields:

```json
{
  "ntp_server": "pool.ntp.org",
  "timezone_offset_sec": 32400,
  "sleep_sec": 300,
  "moisture_threshold": 40,
  "force_watering": false,
  "debug_log_on_wake": false,
  "ota_check_interval_sec": 21600,
  "env_sensors": {
    "soil": {
      "enabled": true,
      "modbus_slave_id": 2,
      "modbus_function": 4,
      "start_register": 0
    },
    "par": {
      "enabled": false,
      "modbus_slave_id": 1,
      "modbus_function": 3,
      "register": 0,
      "scale": 1.0
    },
    "power_settle_ms": 800
  },
  "schedules": [
    {
      "hour": 6,
      "minute": 30,
      "duration_sec": 60,
      "channel_mask": 1,
      "frequency": {"mode": "daily"}
    }
  ]
}
```

WRS also accepts a WRS-specific overlay:

```json
{
  "wrs": {
    "watering": {
      "enabled": true,
      "auto_on_low_moisture": false,
      "require_soil_feedback": true,
      "force_watering": false,
      "moisture_threshold": 40,
      "stop_moisture_percent": 55,
      "max_duration_sec": 60,
      "check_interval_sec": 10,
      "channel_mask": 1
    },
    "sensors": {
      "soil": {"enabled": true, "modbus_slave_id": 2, "modbus_function": 4, "start_register": 0},
      "par": {"enabled": false, "modbus_slave_id": 1, "modbus_function": 3, "register": 0, "scale": 1.0},
      "power_settle_ms": 800
    }
  }
}
```

The `wrs` overlay wins over `env_sensors` when both are present.

`channel_mask` is a device-side irrigation output mask. WRS does not know
whether an output is connected to a pump, valve, relay, or solenoid:

| `channel_mask` | Active output |
|---:|---|
| `1` | Irrigation output 1 (`D2`) |
| `2` | Irrigation output 2 (`D3`) |
| `3` | Irrigation outputs 1 and 2 |

## Status Payload

WRS publishes:

- watering state: `watering_due`, `watering_started`, `watering_stop_reason`,
  `watering_elapsed_sec`.
- RS485 soil values: `soil_moisture_percent`, `soil_temperature_c`,
  `soil_ec_us_cm`, `soil_ph`, `soil_n_mg_kg`, `soil_p_mg_kg`,
  `soil_k_mg_kg`.
- PAR values: `par_umol_m2_s`.
- raw Modbus values and sensor power state.

These names match the hub measurement repository, so no WRS-only schema is
required for time-series storage.

## Build

```bash
cd client-devices/watering-rs485-device
make build
```

Use `make check-firmware` to verify the embedded OTA manifest after build.
