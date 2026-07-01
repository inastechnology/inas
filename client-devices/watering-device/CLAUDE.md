# CLAUDE.md — INA Water Controller 2

## Project Overview

Firmware for a **Seeed XIAO ESP32-S3** smart watering device. The device wakes every 10 hours, reads soil moisture, runs a capped watering cycle (up to 10 × 30-second loops with 30-second soak waits between loops), publishes a status JSON payload over MQTT, then enters deep sleep. Built with the Arduino framework via PlatformIO.

---

## Repository Layout

```
src/
  main.cpp               # Entry point: setup() → app_init(), loop() → app_loop()
  app/
    inc/                 # Application-layer headers
      app.h              # app_init / app_deinit / app_loop
      app_config.h       # AppConfig class (Wi-Fi / MQTT / device ID, stored in NVS)
      app_def.h          # Build-flag-overridable defaults (SSID, MQTT broker, topics…)
      app_network.h      # Network API + app_msg_type_t enum
      app_pin.h          # GPIO pin assignments (A0 temp, A1 TDS, D2 valve, D3 pump)
      app_task.h         # Task queue structs & task_id_t (pump, valve, sensor, camera, audio)
      app_watering.h     # Watering API
      app_sensor.h       # Sensor API
      app_audio.h        # Audio API (currently commented out)
      app_camera.h       # Camera API (currently commented out)
      app_notifier.h     # Notifier API
      app_utils.h        # CRC32 + UUID helpers
      app_persistent_log.h
    src/
      app.cpp            # Main control loop: watering task + deep-sleep scheduling
      app_network.cpp    # WiFi + MQTT (PubSubClient): connect, pub/sub, reconnect
      app_watering.cpp   # Soil moisture gate + async pump drive
      app_sensor.cpp
      app_task.cpp       # Binary task-request parser for MQTT-driven scheduling
      app_resource.cpp
      app_audio.cpp      # (audio feature, currently disabled)
      app_camera.cpp     # (camera feature, currently disabled)
  hal/
    inc/                 # Hardware-abstraction headers
      hal_config.h       # NVS save/load declarations
      hal_output.h       # MOSFET output (pump/valve): init, start_async, is_in_progress
      hal_soil.h         # Soil moisture ADC: init (with dry/wet calibration), read_raw, read_percent
      hal_temperature.h  # DS18B20 temperature
      hal_tds.h          # TDS sensor
      hal_audio.h
      hal_camera.h
    src/
      hal_config.cpp     # NVS persistence for AppConfig
      hal_output.cpp     # ESP32 hardware timer + ISR for timed MOSFET pulse
      hal_soil.cpp       # ADC read with dry/wet linear calibration
      hal_temperature.cpp
      hal_tds.cpp
      hal_audio.cpp
      hal_camera.cpp
data/                    # LittleFS filesystem payload (flashed separately)
  config                 # Runtime config file
  text.txt               # Sanity-check file ("hello, world!!!!!!!!!!")
test/                    # PlatformIO unit/integration tests (currently empty)
lib/                     # Project-private libraries (currently empty)
include/                 # Shared headers (currently empty)
partitions.csv           # Custom partition table: nvs(24KB) + factory(1MB) + storage(960KB LittleFS)
platformio.ini           # PlatformIO build config
default.env.user.ini     # Template for per-developer secrets (copy → .env.user.ini)
Makefile                 # Convenience wrappers around pio commands
AGENTS.md                # Agent/AI coding guidelines (mirrors this file's conventions)
```

---

## Build & Flash Workflow

### Prerequisites
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

Network credentials and MQTT settings flow at **build time** via `[user] network_flags` in `.env.user.ini`. These define preprocessor macros that `app_def.h` uses as defaults. At runtime, `AppConfig::init()` reads from NVS, falls back to defaults if uninitialized, then always calls `apply_network_defaults()` to overwrite the Wi-Fi/MQTT fields — so changing `.env.user.ini` and rebuilding is always enough.

`AppConfig` is a packed struct stored in NVS with a CRC32 integrity check. Device ID is auto-generated as `INADS-{UUIDv4}` on first boot.

**Never hardcode secrets in `src/`.** `.env*` is gitignored.

---

## Application Logic (`app_loop`)

Each wake cycle (every `APP_WAKEUP_INTERVAL_SEC` = 36 000 s / 10 h):

1. Check/restore WiFi + MQTT connection; reboot on failure.
2. Read soil moisture via `app_watering_get_last_soil_moisture()`.
3. Run up to `APP_WATERING_MAX_LOOPS` (10) watering loops:
   - Each loop: check moisture threshold (40%); if sufficient, skip and publish a `watering_skipped=true` status.
   - If dry: call `app_watering_start_async(APP_WATERING_LOOP_DURATION_SEC=30)`, poll `app_watering_is_in_progress()`.
   - After each loop, wait `APP_WATERING_SOAK_WAIT_SEC` (30 s) for soil infiltration.
4. Publish JSON status over MQTT: `{seq, watering, watering_loops, watering_skipped, last_soil_moisture}`.
5. Disconnect network, calculate remaining sleep time, call `esp_deep_sleep()`.

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
- **`hal_config`** — NVS read/write for `AppConfig` struct.

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
