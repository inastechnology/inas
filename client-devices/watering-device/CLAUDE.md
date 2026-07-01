# CLAUDE.md — INA Water Controller 2

## Project Overview

Firmware for a **Seeed XIAO ESP32-S3** smart watering device. The device wakes every 10 hours, reads soil moisture, runs a capped watering cycle (up to 10 × 30-second loops with 30-second soak waits between loops), publishes a status JSON payload over MQTT, then enters deep sleep. Built with the Arduino framework via PlatformIO.

---

## Repository Layout

```text
client-devices/watering-device/
  src/main.cpp           # Entry point: setup() -> app_init(), loop() -> app_loop()
  src/app/               # WateringDevice : AppDevice, runtime config, watering, sensors
  src/hal/               # Watering-device HAL drivers: output, soil/TDS/temp, camera, audio
  lib/ina-client-common  # Symlink to ../common/lib/ina-client-common
  data/                  # LittleFS filesystem payload
  test/                  # PlatformIO unit/integration tests
  partitions.csv         # OTA-capable partition table
  platformio.ini         # Board config and APP_DEVICE_KIND="WTR"
  default.env.user.ini   # Template for per-developer settings
  Makefile               # Convenience wrappers around pio commands

client-devices/common/lib/ina-client-common/
  src/app/               # Shared AppDevice lifecycle, setup, config, MQTT, OTA, task, time sync, debug log, utilities
  src/hal/               # Shared config persistence HAL
```

Keep watering logic, pin mapping, runtime config schema, sensor behavior, and
status payload shape in this project. Shared boot/wake lifecycle code belongs in
`client-devices/common/lib/ina-client-common`.

---

## Build & Flash Workflow

### Prerequisites
- Linux or WSL2. Native Windows builds are not supported because the project
  uses a symlinked PlatformIO library.
- PlatformIO installed (`platformio` in PATH or via `~/.platformio/penv/bin/`)
- `.env.user.ini` populated from `default.env.user.ini`

### Common Commands

| Command | What it does |
|---|---|
| `make build` | Compile firmware for `seeed_xiao_esp32s3` |
| `make buildfs` | Build LittleFS image from `data/` |
| `make upload` | Build + upload over USB (auto-detects `/dev/ttyACM*` or `/dev/ttyUSB*`) |
| `make upload UPLOAD_PORT=/dev/ttyACM0` | Upload to specific port |
| `make merged-bin` | Produce single flashable `flash_merged.bin` at offset `0x0` |
| `make flash-merged UPLOAD_PORT=/dev/ttyACM0` | Write merged image in one shot |
| `make ports` | List detected serial ports |
| `make remote-upload` | Upload via PlatformIO Remote |
| `make remote-monitor` | Serial monitor via PlatformIO Remote |
| `platformio test -e seeed_xiao_esp32s3` | Run tests from `test/` |

### Partition Layout
| Name | Type | Offset | Size |
|---|---|---|---|
| nvs | data/nvs | 0x9000 | 24 KB |
| phy_init | data/phy | 0xF000 | 4 KB |
| factory | app | 0x10000 | 1 MB |
| storage | data/spiffs | auto | 960 KB (LittleFS) |

---

## Configuration System

Network credentials and MQTT settings flow at **build time** via `[user] network_flags` in `.env.user.ini`. These define preprocessor macros that `app_def.h` uses as defaults. At runtime, `AppConfig::init()` reads from LittleFS, falls back to defaults if uninitialized, then stores the initial config.

`AppConfig` is a packed struct stored in LittleFS with a CRC32 integrity check. Device ID is auto-generated as `INADS-{UUIDv4}` on first boot.

**Never hardcode secrets in `src/`.** `.env*` is gitignored.

---

## Application Logic

`app_init()` creates a `WateringDevice` concrete class and calls the common
`AppDevice::initialize()` lifecycle. `app_loop()` delegates to
`AppDevice::loop()`.

Common lifecycle responsibilities:

1. Mount LittleFS and load saved Wi-Fi/MQTT settings.
2. Enter setup AP mode when enabled and settings are missing or connection setup fails.
3. Start or reconnect Wi-Fi/MQTT.
4. Request runtime config and OTA offer.
5. Sync time and handle RTC fallback after deep sleep.
6. Call `WateringDevice::run_device_cycle()`.
7. Publish device status/debug log and enter deep sleep.

Watering-device responsibilities:

1. Parse and persist watering runtime config.
2. Check due schedules and soil moisture.
3. Run valve/pump output through `app_watering_start_async()`.
4. Build the watering-specific status JSON payload.

---

## MQTT Protocol

**Topic format:** `/<device_id>/kinds/<kind>/<mode>`

| Direction | Topic example | Notes |
|---|---|---|
| Publish | `/<INADS-uuid>/kinds/agri/immediate` | Status, sensor data, images |
| Subscribe | `/+/kinds/+/+` | Wildcard; only messages for own `device_id` are processed |

Incoming binary payloads matching the `task_request_header_t` magic (`0x1A5D`) are fed to the task engine. Currently defined task types: `TASK_ID_SENSOR_REPORT`, `TASK_ID_CAMERA_REPORT`, `TASK_ID_AUDIO_REPORT`, `TASK_ID_PUMP_CONTROL`, `TASK_ID_VALVE_CONTROL`.

Large payloads use `app_network_send_large()` which chunks data in 896-byte writes.

---

## HAL Layer Conventions

- **`hal_output`** — single MOSFET channel driven by an ESP32 hardware timer (Timer 0, 80× prescaler → 1 µs/tick). `hal_output_start_async(duration_ms, callback)` starts the pulse; an ISR fires `on_complete` and pulls the pin LOW. Only one channel at a time (guarded by `s_in_progress`).
- **`hal_soil`** — ADC read with linear mapping from (`dry_raw=1895`, `wet_raw=1285`) to 0–100%. Calibration values match real sensor measurements for this hardware.
- **`hal_temperature`** — DS18B20 via OneWire on pin `A0`.
- **`hal_tds`** — TDS sensor on pin `A1`.
- **`hal_config`** — LittleFS read/write for `AppConfig` struct.

---

## Coding Style & Naming Conventions

- **Language:** C++17, Arduino framework, ESP-IDF APIs used directly where needed.
- **Indentation:** 4 spaces, Allman-style braces (opening brace on its own line).
- **Naming:** `snake_case` throughout; module-prefixed:
  - `app_*` — application layer
  - `hal_*` — hardware abstraction layer
- **Filenames:** lowercase with module prefix, e.g. `app_watering.cpp`, `hal_output.h`.
- **Constants:** `constexpr` or typed enums for compile-time values; `#define` only for build flags and cross-module preprocessor tokens.
- **Logging:** `ESP_LOGI/E/D(TAG, ...)` for module logs; `Serial.printf/println` for low-level diagnostics. `TAG` is `__FILE__` in most modules.
- **C/C++ interop:** HAL headers wrap declarations in `extern "C"` so they are callable from C files.
- **Disabled features:** Audio, camera, and sensor subsystems are present in the tree but their `app_*_init()` calls are commented out in `app.cpp`. The files `app_notifier.cpp_` and `.idea/app_*.cpp_` have a trailing `_` making them non-compiled; treat them as drafts.

---

## Testing

- Place tests under `test/`, grouped by feature: `test/watering/test_watering.cpp`.
- Name test files `test_<module>.cpp`.
- Cover both normal flow and failure paths: sensor read failure, network reconnect, watering timeout.
- No coverage threshold yet; include tests for all new non-trivial logic.

---

## Commit & PR Conventions

- Use **Conventional Commits**: `feat(watering): add configurable moisture threshold`, `fix(hal_output): prevent double-start race`.
- Keep commits focused and buildable.
- PR description should include: purpose, affected modules, test evidence (`make build` output, test logs), and hardware/behavior impact notes.

---

## Security Notes

- Copy `default.env.user.ini` → `.env.user.ini` and set real credentials. The `.env*` glob is gitignored.
- `AppConfig::show()` redacts passwords; avoid logging raw credentials elsewhere.
- MQTT payloads > 512 bytes are rejected in the subscribe callback.
- `MQTT_MAX_PACKET_SIZE=65535` is set in build flags; do not transmit unvalidated external data at that size.
