# Repository Guidelines

## Project Structure

- `src/main.cpp` is the firmware entry point.
- `src/app/src/app.cpp` contains `EnvironmentSensorDevice : AppDevice`.
- `src/app/inc` contains device-specific app headers.
- `src/hal` is used only for device-specific HAL drivers that satisfy
  `../docs/firmware_layering_policy.md`; prefer common HAL modules for reusable
  hardware primitives.
- `lib/ina-client-common` is a symlink to the shared INAS client library.
- `data/` contains LittleFS payload files.
- `test/` is reserved for PlatformIO tests.

## Commands

- `make build`: compile firmware for `seeed_xiao_esp32s3`.
- `make check-firmware`: build and verify the embedded OTA manifest.
- `make upload`: build and upload to a locally connected board.
- `make factory-bin`: create `firmware.factory.bin`, flashable at address `0x0`.

## Device Contract

`ENV` is a fixed device kind. Do not add runtime capabilities or
ad-hoc pin profiles inside this project. If the hardware role changes, create a
new device project with a new three-letter `APP_DEVICE_KIND`.
Layer boundaries follow `../docs/firmware_layering_policy.md`.
