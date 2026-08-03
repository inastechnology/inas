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

### SEN0641 and MAX485

The DFRobot SEN0641 PAR sensor uses `4800bps`, 8N1, function `0x03`, register
`0x0000`, one register, and scale `1.0`. Its factory slave address is `1`.
Connect its brown wire to switched sensor 12V, black to `RS485_GND`, yellow to
`RS485_A`, and blue to `RS485_B`.

The selected ComWinTop CWT-SOIL five-probe profile uses `4800bps`, 8N1,
function `0x03`, seven registers from `0x0000`, and factory slave address `1`.
INAS uses fixed role IDs: soil sensor 1=`1`, soil sensor 2=`2`, and PAR=`3`.
Keep the first CWT at ID `1`; configure only the second CWT as ID `2`, and
configure the SEN0641 as ID `3`. PAR remains ID `3` when the second soil sensor
is absent. Configure each changed device while it is the only device on the
bus. The current V1.4 CWT cable is brown=`12V+`, black=`RS485_GND`,
yellow/green=`RS485_A`, and blue=`RS485_B`. See the
[source-confirmed product specification](../docs/jp/comwintop_cwt_soil_npkphcth_s_spec.md)
for the alternate cable revision and write frame.

MAX485 modules normally use 5V logic. Do not connect a 5V MAX485 `RO` output
directly to XIAO `D7/GPIO44`; level-shift RX to 3.3V. A 3.3V-logic MAX3485,
SP3485, or SN65HVD transceiver is preferred for new hardware.

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
      "modbus_slave_id": 1,
      "modbus_function": 3,
      "start_register": 0
    },
    "par": {
      "enabled": false,
      "modbus_slave_id": 3,
      "modbus_function": 3,
      "register": 0,
      "scale": 1.0
    },
    "power_settle_ms": 800
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
      "switch_id": "irr2",
      "name": "Strawberry drip line B",
      "enabled": true,
      "role": "irrigation",
      "terminal": "IRR2",
      "channel_mask": 2,
      "controlled_load": "pump relay input"
    },
    {
      "switch_id": "sensor_power",
      "name": "RS485 sensor power",
      "enabled": true,
      "role": "sensor_power",
      "terminal": "SENSOR_12V_SW",
      "channel_mask": 0,
      "controlled_load": "soil and PAR sensors"
    }
  ],
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
      "soil": {"enabled": true, "modbus_slave_id": 1, "modbus_function": 3, "start_register": 0},
      "par": {"enabled": false, "modbus_slave_id": 3, "modbus_function": 3, "register": 0, "scale": 1.0},
      "power_settle_ms": 800
    }
  }
}
```

The `wrs` overlay wins over `env_sensors` when both are present.

These examples are the CWT profile and the fixed INAS ID allocation. Some
firmware and Hub defaults still use the old `soil=2 / PAR=1` allocation and
FC04. Explicitly send `soil.modbus_slave_id: 1`, `par.modbus_slave_id: 3`, and
`soil.modbus_function: 3` until those defaults are changed after bench
validation.

The current WRS runtime schema and watering logic have one `soil` slot. ID `2`
is reserved for a second soil sensor, but simultaneous reads and per-sensor
status require a separate firmware/Hub extension.

`channel_mask` is a device-side irrigation output mask. WRS does not know
whether an output is connected to a pump, valve, relay, or solenoid:

| `channel_mask` | Active output |
|---:|---|
| `1` | Irrigation output 1 (`D2`) |
| `2` | Irrigation output 2 (`D3`) |
| `3` | Irrigation outputs 1 and 2 |

Use `mosfet_switches` as the hub-managed output inventory. `name` and
`controlled_load` describe the installed field hardware, while `channel_mask`
keeps the firmware control path generic.

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
