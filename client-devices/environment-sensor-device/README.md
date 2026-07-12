# INA Environment Sensor

PlatformIO firmware project for `ENV`.

This project is generated from the INAS device scaffold and uses the shared
client library at `lib/ina-client-common`.
Layer boundaries follow
[../docs/firmware_layering_policy.md](../docs/firmware_layering_policy.md).

`ENV` is a 12V-powered RS485 sensor node. Use it for PAR/light sensors and
12V soil EC/pH/NPK sensors that are not suitable for the battery-powered `SOI`
node.

## Setup

```bash
cd client-devices/environment-sensor-device
make build
make check-firmware
```

Local build settings live in `.env.user.ini`. The checked-in
`default.env.user.ini` is safe to copy or regenerate.

## Device Contract

- `APP_DEVICE_KIND`: `ENV`
- Firmware project: `environment-sensor-device`
- Board environment: `seeed_xiao_esp32s3`
- Sensor bus: RS485 Modbus RTU
- Power model: 12V wired power

Keep connected sensors, actuators, payload schema, and pin assignment fixed for
this device kind. If the hardware contract changes materially, create a new
device project and a new three-letter device kind.

## Sensor Calibration

ENV stores runtime sensor settings and calibration parameters in LittleFS.
Hub sends them through `env_sensors` and `env_calibration`.

1. Enable the connected sensor group in Hub: light sensor, soil EC/pH/NPK, or both.
2. Confirm the Modbus slave id, function code, and register address from the sensor manual.
3. Put the sensor in a known reference condition and send
   `env_calibration.mode=capture_reference`.
4. ENV records an offset so the current reading matches
   `env_calibration.reference_value`.

Manual adjustment is also supported per metric with `scale`, `offset`, and
`calibrated`. This is a one-point correction. If a sensor requires native
Modbus calibration commands or two-point calibration, add a dedicated mode after
confirming the product manual.
