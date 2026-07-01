# Repository Guidelines

## Project Structure & Module Organization
- `src/main.cpp` is the firmware entry point (`setup()`/`loop()`).
- Application logic lives in `src/app`: headers in `src/app/inc`, implementations in `src/app/src` (networking, watering, sensors, tasks).
- Hardware abstraction layer lives in `src/hal`: headers in `src/hal/inc`, implementations in `src/hal/src` (audio, camera, output, soil/TDS/temperature).
- `data/` contains LittleFS payload files flashed to the device filesystem.
- `lib/` is for project-private reusable libraries; `include/` is for shared headers.
- `test/` is reserved for PlatformIO unit/integration tests.

## Build, Test, and Development Commands
- `make build`: compile firmware for `seeed_xiao_esp32s3`.
- `make upload`: build and upload to a locally connected board.
- `make remote-upload`: upload via PlatformIO Remote.
- `make remote-monitor`: open remote serial monitor.
- `make help`: list available targets.
- `platformio test -e seeed_xiao_esp32s3`: run tests from `test/`.

## Coding Style & Naming Conventions
- Language: C++ (Arduino framework on ESP32S3).
- Follow existing style: 4-space indentation, opening braces on new lines (Allman style).
- Use module-prefixed snake_case names: `app_*` for app layer, `hal_*` for HAL.
- Keep filenames lowercase with module prefixes, e.g. `app_watering.cpp`, `hal_output.h`.
- Prefer `constexpr`/typed constants for compile-time values; reserve macros for build flags and cross-module defines.

## Testing Guidelines
- Place tests under `test/`, grouped by feature (for example `test/watering/test_watering.cpp`).
- Name new test files `test_<module>.cpp`.
- Validate both normal flow and hardware-failure paths (sensor read failure, network reconnect, watering timeout).
- No formal coverage threshold is defined yet; include tests for all new non-trivial logic.

## Commit & Pull Request Guidelines
- Current repository history has no commits yet, so no established convention exists.
- Use Conventional Commits going forward, e.g. `feat(network): add MQTT reconnect backoff`.
- Keep commits focused and buildable.
- PRs should include: purpose, affected modules, test evidence (`make build`, `platformio test` logs), and hardware/behavior impact notes.

## Security & Configuration Tips
- Copy `default.env.user.ini` to `.env.user.ini` and set local Wi-Fi/MQTT values.
- Never commit credentials; `.env*` is gitignored.
- Keep secrets in build flags/config, not hardcoded in `src/`.
