# INA Soil Sensor

PlatformIO firmware project for `SOI`.

This project is generated from the INAS device scaffold and uses the shared
client library at `lib/ina-client-common`.
Layer boundaries follow
[../docs/firmware_layering_policy.md](../docs/firmware_layering_policy.md).

`SOI` is a low-power soil moisture node. It currently reads only an analog soil
moisture sensor on `A0`; 12V RS485 sensors such as EC/pH/NPK belong to `ENV`.

## Setup

```bash
cd client-devices/soil-sensor-device
make build
make check-firmware
```

Local build settings live in `.env.user.ini`. The checked-in
`default.env.user.ini` is safe to copy or regenerate.

## Device Contract

- `APP_DEVICE_KIND`: `SOI`
- Firmware project: `soil-sensor-device`
- Board environment: `seeed_xiao_esp32s3`
- Sensor: analog soil moisture on `A0`
- Power model: 18650 battery / deep sleep

Keep connected sensors, actuators, payload schema, and pin assignment fixed for
this device kind. If the hardware contract changes materially, create a new
device project and a new three-letter device kind.

## Soil Moisture Calibration

SOI starts with default dry/wet raw values, but field calibration should be
done from Hub after installation.

1. Put the sensor in the dry reference condition and send
   `soil_calibration.mode=capture_dry`.
2. After the next wake, put the sensor in the wet reference condition and send
   `soil_calibration.mode=capture_wet`.
3. When the dry/wet gap is at least `soil_calibration.min_delta_raw`, SOI stores
   the values in LittleFS and reports `soil_calibration_calibrated=true`.

Manual calibration is also supported through runtime config fields:
`dry_raw`, `wet_raw`, `calibrated`, `min_delta_raw`, `sample_count`, and
`sample_interval_ms`.

Hub must attach a new `request_id` when sending `capture_dry`, `capture_wet`, or
`reset`. SOI uses it to avoid processing the same retained command twice.
