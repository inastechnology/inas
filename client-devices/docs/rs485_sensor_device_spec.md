# RS485 Sensor Device Specification

Japanese version:

- [jp/rs485_sensor_device_spec.md](jp/rs485_sensor_device_spec.md)

## Purpose

INAS separates measurement-focused devices from WTR. `SOI` measures soil
moisture with low power consumption. `ENV` handles 12V RS485 sensors. Each
`device_kind` has fixed sensor connections, pin assignments, and MQTT payload
schema. A low-voltage watering build that still performs the WTR role remains a
WTR hardware profile, not a separate sensor device kind.

INAS does not use a highly dynamic `capabilities` model for these devices. If
the product behavior changes, create a separate firmware project and a separate
`device_kind`.

For XIAO ESP32S3 pin diagrams, see [pin_assignments.md](pin_assignments.md).

## Device Kinds

| device_kind | Project | Role |
|---|---|---|
| `SOI` | `soil-sensor-device` | Battery-powered soil moisture node |
| `ENV` | `environment-sensor-device` | 12V RS485 Modbus sensor hub |
| `WTR` | `watering-device` | Small-scale integrated watering device |
| `WRS` | `watering-rs485-device` | RS485-first integrated watering device |

## SOI Hardware Assumptions

`SOI` is a low-power node placed in soil. It currently supports only an analog
soil moisture sensor. It does not support RS485 sensors or 12V sensors.

| Signal | XIAO pin | Purpose |
|---|---|---|
| Soil moisture analog | `A0` | Soil moisture ADC |

The sensor is sampled after wake, and the device returns to deep sleep after
publishing status. First calibration is user-driven from the Hub. Firmware build
flags are only initial values before calibration.

Initial values:

- dry raw: `3200`
- wet raw: `1500`
- sample count: `20`
- sample interval: `40 ms`

## SOI Soil Moisture Calibration

SOI receives calibration state through runtime config `soil_calibration`. The
Hub UI should present farmer-friendly operation names and avoid exposing raw
variable names in the primary workflow.

Calibration modes:

| mode | Purpose |
|---|---|
| `normal` | Normal measurement |
| `capture_dry` | Save the current raw value as the dry reference |
| `capture_wet` | Save the current raw value as the wet reference |
| `reset` | Return to an uncalibrated state |

Initial setup:

1. Put the sensor in the dry reference condition and send `capture_dry` from the
   Hub.
2. On the next wake, SOI stores the averaged ADC value as `dry_raw`.
3. Put the sensor in the wet reference condition and send `capture_wet`.
4. On the next wake, SOI stores the averaged ADC value as `wet_raw`.
5. If `dry_raw - wet_raw >= min_delta_raw`, SOI marks the calibration as valid
   and calculates percent from calibrated values afterwards.

Manual setup is allowed. The Hub can directly set `dry_raw`, `wet_raw`, and
`calibrated`, and can tune `sample_count` and `sample_interval_ms`. `request_id`
prevents duplicate handling of one-shot calibration commands. Non-`normal`
modes require `request_id`.

SOI status payload:

```json
{
  "device_kind": "SOI",
  "sensor_model": "Analog-Soil-Moisture",
  "soil_moisture_ok": true,
  "soil_moisture_percent": 42,
  "raw_soil_moisture": 2486,
  "soil_calibration_required": false,
  "soil_calibration_calibrated": true,
  "soil_calibration_mode": "normal",
  "soil_calibration_dry_raw": 3200,
  "soil_calibration_wet_raw": 1500,
  "soil_calibration_sample_count": 20,
  "soil_calibration_sample_interval_ms": 40
}
```

## ENV Hardware Assumptions

The target board is currently `seeed_xiao_esp32s3`. RS485 uses an ESP32-S3 UART
connected to an RS485 transceiver.

| Signal | XIAO pin | GPIO | Purpose |
|---|---:|---:|---|
| RS485 TX | `D6` | `GPIO43` | UART TX |
| RS485 RX | `D7` | `GPIO44` | UART RX |
| RS485 DE/RE | `D4` | `GPIO5` | Transmit/receive direction control |

Use a 3.3V logic-compatible RS485 transceiver, such as MAX3485, SP3485, or
SN65HVD-series parts.

`ENV` assumes a 12V power source. PAR sensors, irradiance sensors, EC/pH/NPK
sensors, and similar 12V sensors belong on ENV.

## ENV Soil RS485 Sensor

The expected sensor family is a TH-EC-PH-NPK style 7-in-1 RS485 Modbus soil
sensor.

Measurements:

- Soil moisture
- Soil temperature
- EC
- pH
- Nitrogen N
- Phosphorus P
- Potassium K

The selected ComWinTop CWT-SOIL `NPKPHCTH-S` profile is source-confirmed from
the vendor's five-probe V1.4 manual. The source hashes, wiring revisions,
complete register table, and field cautions are recorded in
[the Japanese product-specific specification](jp/comwintop_cwt_soil_npkphcth_s_spec.md).

Confirmed profile:

| Item | Setting |
|---|---|
| Power | 12V in INAS; sensor rating is 5-30V |
| Serial | Modbus RTU, 4800bps, 8N1 |
| Factory slave id | `1` |
| Read function | `0x03` |
| Start register | `0x0000` |
| Register count | `7` |

Confirmed register map:

| offset | payload field | scale |
|---:|---|---:|
| 0 | `soil_moisture_percent` | register / 10 |
| 1 | `soil_temperature_c` | signed register / 10 |
| 2 | `soil_ec_us_cm` | register |
| 3 | `soil_ph` | register / 10 |
| 4 | `soil_n_mg_kg` | register |
| 5 | `soil_p_mg_kg` | register |
| 6 | `soil_k_mg_kg` | register |

The V1.4 manual has a `0x30` typo in its read-function heading, while all of its
request examples and the bundled configuration tool use `0x03`. INAS reserves
fixed role IDs: soil sensor 1=`1`, soil sensor 2=`2`, and PAR=`3`. Keep the
first soil sensor at its factory ID `1`; configure only the second soil sensor
as ID `2`. PAR remains ID `3` even when the second soil sensor is absent.

As of 2026-08-01, some firmware and Hub defaults still contain the old ID
allocation and the pre-manual FC04 assumption. Runtime config for this CWT
sensor must explicitly set `modbus_slave_id` to `1` and `modbus_function` to
`3`. The current schema has one soil-sensor slot; reading the reserved ID `2`
sensor concurrently requires a separate extension.

ENV soil RS485 status payload:

```json
{
  "device_kind": "ENV",
  "sensor_model": "RS485-12V-ENV",
  "soil_rs485_enabled": true,
  "soil_rs485_ok": true,
  "soil_rs485_modbus_slave_id": 1,
  "soil_moisture_percent": 42.1,
  "soil_temperature_c": 21.5,
  "soil_ec_us_cm": 820,
  "soil_ph": 6.5,
  "soil_n_mg_kg": 34,
  "soil_p_mg_kg": 18,
  "soil_k_mg_kg": 102
}
```

## ENV Calibration

ENV receives runtime config through `env_sensors` and `env_calibration`.
`env_sensors` configures RS485 slave id, function code, and register.
`env_calibration` stores per-metric `scale`, `offset`, and `calibrated`.

Calibration modes:

| mode | Purpose |
|---|---|
| `normal` | Normal measurement |
| `capture_reference` | Save an offset that aligns the current value to a known reference |
| `reset` | Return to an uncalibrated state |

Initial setup:

1. Select the target metric, such as PAR, EC, or pH.
2. Enter a known reference value in the Hub, such as a pH standard solution, EC
   standard solution, or a value measured by another trusted light meter.
3. Send `capture_reference`.
4. On the next wake, ENV stores the offset between the current measurement and
   the reference value.
5. If needed, manually tune `scale` and `offset` in detail settings.

This is a one-point correction. For strict two-point pH/EC calibration or
sensor-native Modbus calibration commands, add dedicated modes after confirming
the product manual.

## ENV Light Sensor

The initial supported light sensor is the DFRobot SEN0641 with a 0-4000
umol/m2/s range over RS485 Modbus. Add separate register, scale, and range
profiles for other PAR sensors.

Initial provisional register map:

| register | payload field | scale |
|---:|---|---:|
| 0 | `par_umol_m2_s` | register * `APP_ENV_PAR_SCALE` |

ENV status payload:

```json
{
  "device_kind": "ENV",
  "sensor_model": "RS485-12V-ENV",
  "par_enabled": true,
  "par_ok": true,
  "par_modbus_slave_id": 3,
  "par_umol_m2_s": 1234.0
}
```

### DFRobot SEN0641 Profile

DFRobot `SEN0641` can be used as the ENV/WRS RS485 PAR sensor. Treat the [DFRobot SEN0641 Wiki](https://wiki.dfrobot.com/sen0641/) and [Modbus reference](https://wiki.dfrobot.com/sen0641/docs/20337) as the authoritative product specifications.

| Item | Setting |
|---|---|
| Power | DC 5-30V, less than 10mA. Connect to `SENSOR_12V_SW+` on WRS |
| Measurement | 0-4000 umol/m2/s with 1 umol/m2/s resolution |
| Communication | Modbus RTU, 4800bps, 8 data bits, no parity, 1 stop bit |
| Slave ID | `1` at factory default |
| Read function | `0x03` |
| PAR register | `0x0000`, one register, scale `1.0` |
| Wires | brown=VCC, black=GND, yellow=485-A, blue=485-B |

The SEN0641 factory ID is `1`, but the INAS fixed allocation is soil sensor
1=`1`, soil sensor 2=`2`, and PAR=`3`. Configure the SEN0641 as ID `3` while it
is the only device on the bus. Do not compress PAR to ID `2` when soil sensor 2
is absent. All devices on one bus must use the same baud rate.

When a 5V MAX485 module is used with the XIAO ESP32S3, do not connect its 5V `RO` output directly to `D7/GPIO44`. Level-shift the receive signal to 3.3V or use a 3.3V-logic transceiver such as MAX3485, SP3485, or an SN65HVD variant. Verify the specific MAX485 module's pull-ups, termination, and A/B labels against its schematic.

## WRS Hardware Assumptions

`WRS` is the RS485-first all-in-one watering device. It keeps WTR-style local
irrigation outputs, but treats the RS485 bus as the primary sensor expansion
point instead of relying on analog soil moisture as the main feedback path.

The initial pin assignment should match WTR for irrigation output and RS485 so
that enclosure and wiring work can be reused:

| Signal | XIAO pin | GPIO | Purpose |
|---|---:|---:|---|
| Irrigation output 1 MOSFET | `D2` | `GPIO3` | Irrigation channel 1 |
| Irrigation output 2 MOSFET | `D3` | `GPIO4` | Irrigation channel 2 |
| RS485 DE/RE | `D4` | `GPIO5` | Transmit/receive direction control |
| RS485 TX | `D6` | `GPIO43` | UART TX |
| RS485 RX | `D7` | `GPIO44` | UART RX |
| 12V sensor power MOSFET | `D8` | `GPIO7` | Switches only the 12V branch going to RS485 sensors |

The analog soil moisture ADC pin may remain unused or reserved for diagnostics.
Do not create a new pin assignment every time a sensor is added. Add sensors on
the RS485 bus, assign each sensor a unique Modbus slave ID, and report missing
sensors as `*_ok=false` after timeout, CRC failure, or no response.

Initial WRS sensor groups:

- RS485 PAR sensor, for `par_umol_m2_s`.
- RS485 soil sensor, for moisture, temperature, EC, pH, and N/P/K.
- Optional RS485 irradiance sensor, for `solar_radiation_w_m2`.

WRS status should use the same metric names as ENV and WTR so the hub can store
measurements vertically without a separate schema:

```json
{
  "device_kind": "WRS",
  "sensor_model": "RS485-WATERING-AIO",
  "watering_due": true,
  "watering_started": true,
  "soil_rs485_ok": true,
  "soil_moisture_percent": 42.1,
  "soil_temperature_c": 21.5,
  "soil_ec_us_cm": 820,
  "soil_ph": 6.5,
  "par_ok": true,
  "par_umol_m2_s": 1234.0
}
```

## Measurement DB Definition

ENV/SOI/WTR/WRS measurements are stored as vertical time-series records
rather than only fixed columns.

`sensor_measurement_definitions`:

- `metric`: metric id such as `soil_ec_us_cm`
- `display_name`: UI display name
- `unit`: unit
- `category`: `soil` / `light`
- `device_kinds`: JSON list of supported device kinds
- `value_type`: value type such as `float`

`sensor_measurements`:

- `device_id`
- `device_kind`
- `measured_at`
- `metric`
- `value`
- `unit`
- `quality`
- `raw_value`
- `source`
- `payload`

Initial definitions include soil moisture, soil temperature, EC, pH, N/P/K, PAR,
and future irradiance metrics. SOI contributes analog
`soil_moisture_percent`. WRS supports the same RS485 soil and light metrics as
ENV while also supporting irrigation action fields.

## OTA

SOI, ENV, WTR, and WRS firmware binaries embed `INAS_FW_MANIFEST_V1`. After build, run
`make check-firmware` before uploading firmware to the Hub.

## Operational Rules

- Sensor connections and payload schemas are fixed per `device_kind`.
- Use a new device project and new `device_kind` for materially different
  hardware behavior.
- Use `WRS` when irrigation output and RS485 soil/PAR/irradiance sensors belong
  to one stronger all-in-one device.
- Treat a low-voltage watering node as a WTR hardware profile when it keeps the
  WTR behavior and payload contract.
- Keep user-facing UI terms farmer-friendly; reserve raw variable names and JSON
  for detail screens.
