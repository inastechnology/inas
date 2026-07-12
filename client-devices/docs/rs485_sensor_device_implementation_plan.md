# RS485 Sensor Device Implementation Plan

Japanese version:

- [jp/rs485_sensor_device_implementation_plan.md](jp/rs485_sensor_device_implementation_plan.md)

## Direction

`SOI` and `ENV` are measurement-focused devices, but their power requirements
are different. `SOI` is a battery-powered soil moisture node. `ENV` is a
12V-powered RS485 sensor hub.

Low-level RS485 Modbus RTU handling belongs in the shared library. `ENV` owns
the register maps and status payload conversion. `SOI` reads only an analog soil
moisture sensor for now.
Layer boundaries follow [firmware_layering_policy.md](firmware_layering_policy.md).

## Implementation Steps

1. Device scaffolding
   - Generate `soil-sensor-device` / `SOI` with
     `client-devices/scripts/create_device_project.py`.
   - Generate `environment-sensor-device` / `ENV` with the same script.

2. SOI application
   - Read the soil moisture sensor on `A0` after wake.
   - Convert raw ADC values to 0-100% using dry/wet calibration.
   - Support user-driven first calibration through `soil_calibration.mode`:
     `capture_dry`, `capture_wet`, and `reset`.
   - Keep `dry_raw`, `wet_raw`, `min_delta_raw`, `sample_count`, and
     `sample_interval_ms` adjustable through runtime config.
   - Persist calibration values in LittleFS across deep sleep.
   - Start with a 900-second sleep interval.

3. Shared RS485/Modbus layers
   - Initialize UART and DE/RE pin with `hal_rs485_modbus_init()`.
   - Expose register operations through `hal_rs485_bus_read_registers()`.
   - Keep sensor register maps and unit conversion in
     `hal_rs485_sensor_protocol`.
   - Validate CRC16, slave id, function code, and byte count in the Modbus
     layer.
   - Return `false` on timeout or CRC mismatch, and let the device App expose
     failures in status payloads such as `par_ok=false` or
     `soil_rs485_ok=false`.

4. ENV application
   - Read the PAR register after wake.
   - Read 12V EC/pH/NPK soil sensors only when
     `APP_ENV_SOIL_RS485_ENABLED=1`.
   - Include `par_umol_m2_s`, soil RS485 values, and raw registers in MQTT
     status.
   - Make PAR and soil RS485 slave id, function, and register configurable
     through `env_sensors`.
   - Store per-metric `scale`, `offset`, and `calibrated` values in
     `env_calibration`.
   - In `capture_reference`, persist the offset between a known reference value
     and the current measurement to LittleFS.
   - Start with a 300-second sleep interval.

5. Hub support
   - Define metrics, display names, units, and supported device kinds in
     `sensor_measurement_definitions`.
   - Store ENV/SOI/WTR/WRS measurements vertically in `sensor_measurements`.
   - Normalize ENV status fields such as `par_umol_m2_s`, soil moisture, soil
     temperature, EC, pH, N/P/K into measurements.
   - Continue MQTT status logging even if measurement DB writes fail.

6. Build verification
   - Build `soil-sensor-device`.
   - Build `environment-sensor-device`.
   - Run firmware manifest checks.
   - Run focused hub tests for measurement normalization and config handling.

## Unknowns

The official Modbus register tables for the selected sensors are not confirmed
yet. After obtaining the real manuals, verify:

- Default slave id
- Baud rate
- Function code
- Start register
- Register count
- Signedness
- Scale factors
- NPK units
- PAR sensor unit and scale

## Tunable Areas

SOI `platformio.ini` build flags are only initial values before calibration:

```ini
-D APP_SOI_MOISTURE_PIN=A0
-D APP_SOI_DRY_RAW=3200
-D APP_SOI_WET_RAW=1500
-D APP_SOI_SAMPLE_COUNT=20
-D APP_SOI_SAMPLE_INTERVAL_MS=40
```

Runtime SOI calibration is updated from Hub runtime config:

```json
{
  "soil_calibration": {
    "mode": "normal",
    "dry_raw": 3200,
    "wet_raw": 1500,
    "min_delta_raw": 200,
    "sample_count": 20,
    "sample_interval_ms": 40,
    "calibrated": false,
    "request_id": ""
  }
}
```

ENV build flags are initial values used before runtime config is received:

```ini
-D APP_ENV_RS485_TX_PIN=43
-D APP_ENV_RS485_RX_PIN=44
-D APP_ENV_RS485_DE_RE_PIN=5
-D APP_ENV_PAR_MODBUS_SLAVE_ID=1
-D APP_ENV_PAR_REGISTER=0
-D APP_ENV_PAR_SCALE=1
```

Runtime ENV settings are updated from Hub runtime config:

```json
{
  "env_sensors": {
    "par": { "enabled": true, "slave_id": 1, "function": 4, "register": 0, "count": 1 },
    "soil_rs485": { "enabled": true, "slave_id": 2, "function": 4, "register": 0, "count": 7 }
  },
  "env_calibration": {
    "par_umol_m2_s": { "scale": 1.0, "offset": 0.0, "calibrated": false },
    "soil_ec_us_cm": { "scale": 1.0, "offset": 0.0, "calibrated": false },
    "soil_ph": { "scale": 1.0, "offset": 0.0, "calibrated": false }
  }
}
```

## Risks

- A 5V-only RS485 transceiver can damage ESP32-S3 GPIO.
- A separate sensor power domain still requires a common GND.
- Long RS485 wiring may require termination and bias resistors.
- Register maps may differ by vendor listing or production lot.
- Multiple sensors on one ENV RS485 bus must not share the same slave id.
- SOI soil moisture percent depends strongly on dry/wet raw calibration.
