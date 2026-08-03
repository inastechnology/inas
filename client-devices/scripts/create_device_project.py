#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
DEVICE_KIND_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class DeviceProjectSpec:
    project_slug: str
    device_kind: str
    display_name: str
    class_name: str
    board: str
    env_name: str
    firmware_version: str
    firmware_build_id: str
    setup_ap_ssid: str


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def create_device_project(spec: DeviceProjectSpec, repo_root: Path, *, dry_run: bool = False) -> Path:
    repo_root = repo_root.resolve()
    project_root = repo_root / "client-devices" / spec.project_slug
    common_library_root = repo_root / "client-devices" / "common" / "lib" / "ina-client-common"
    if not common_library_root.exists():
        raise FileNotFoundError(f"common library not found: {common_library_root}")
    if project_root.exists():
        raise FileExistsError(f"device project already exists: {project_root}")

    files = _render_files(spec)
    directories = [
        project_root / "src" / "app" / "inc",
        project_root / "src" / "app" / "src",
        project_root / "src" / "hal" / "inc",
        project_root / "src" / "hal" / "src",
        project_root / "include",
        project_root / "lib",
        project_root / "test",
        project_root / "data",
        project_root / "docs",
    ]
    if dry_run:
        print(f"Would create device project: {project_root}")
        for directory in directories:
            print(f"  dir  {directory.relative_to(repo_root)}")
        for relative_path in sorted(files):
            print(f"  file client-devices/{spec.project_slug}/{relative_path}")
        print(f"  link client-devices/{spec.project_slug}/lib/ina-client-common -> ../../common/lib/ina-client-common")
        return project_root

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=False)
    for relative_path, content in files.items():
        path = project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    link_path = project_root / "lib" / "ina-client-common"
    target = os.path.relpath(common_library_root, link_path.parent)
    link_path.symlink_to(target)
    return project_root


def build_spec(
    *,
    project_slug: str,
    device_kind: str,
    display_name: str | None,
    board: str,
    env_name: str | None,
    firmware_version: str,
    firmware_build_id: str | None,
    setup_ap_ssid: str | None,
    repo_root: Path,
) -> DeviceProjectSpec:
    project_slug = _normalize_project_slug(project_slug)
    device_kind = _normalize_device_kind(device_kind)
    return DeviceProjectSpec(
        project_slug=project_slug,
        device_kind=device_kind,
        display_name=display_name or _default_display_name(project_slug),
        class_name=_pascal_case(project_slug),
        board=board,
        env_name=env_name or board,
        firmware_version=firmware_version,
        firmware_build_id=firmware_build_id or _default_build_id(repo_root),
        setup_ap_ssid=setup_ap_ssid or f"INAS-{device_kind}-setup",
    )


def _normalize_project_slug(value: str) -> str:
    if not PROJECT_SLUG_RE.match(value):
        raise ValueError("project must be lowercase kebab-case, e.g. soil-device")
    return value


def _normalize_device_kind(value: str) -> str:
    if not DEVICE_KIND_RE.match(value):
        raise ValueError("device_kind must be exactly three uppercase letters, e.g. SOI")
    return value


def _default_display_name(project_slug: str) -> str:
    return "INA " + " ".join(part.capitalize() for part in project_slug.split("-"))


def _pascal_case(project_slug: str) -> str:
    return "".join(part.capitalize() for part in project_slug.split("-"))


def _default_build_id(repo_root: Path) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    commit = "nogit"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
        commit = result.stdout.strip() or commit
    except (OSError, subprocess.CalledProcessError):
        pass
    return f"{timestamp}+{commit}"


def _render_files(spec: DeviceProjectSpec) -> dict[str, str]:
    return {
        ".gitignore": GITIGNORE_TEMPLATE,
        "AGENTS.md": _render_agents_md(spec),
        "Makefile": _render_makefile(spec),
        "README.md": _render_readme(spec),
        "default.env.user.ini": _render_default_env(spec),
        ".env.user.ini": _render_default_env(spec),
        "platformio.ini": _render_platformio(spec),
        "partitions.csv": PARTITIONS_TEMPLATE,
        "src/main.cpp": MAIN_CPP_TEMPLATE,
        "src/app/inc/app.h": APP_H_TEMPLATE,
        "src/app/src/app.cpp": _render_app_cpp(spec),
        "src/app/src/app_resource.cpp": APP_RESOURCE_CPP_TEMPLATE,
        "src/hal/inc/README.md": HAL_README_TEMPLATE,
        "src/hal/src/README.md": HAL_README_TEMPLATE,
        "include/README": INCLUDE_README_TEMPLATE,
        "lib/README": LIB_README_TEMPLATE,
        "test/README": TEST_README_TEMPLATE,
        "data/.gitkeep": "",
        "docs/README.md": _render_docs_readme(spec),
    }


def _render_platformio(spec: DeviceProjectSpec) -> str:
    return f"""; Generated by client-devices/scripts/create_device_project.py

[platformio]
extra_configs = .env.user.ini

[env:{spec.env_name}]
platform = espressif32
board = {spec.board}
framework = arduino

monitor_speed = 115200
board_build.filesystem = littlefs
board_build.partitions = partitions.csv
build_flags =
    ${{common.build_flags}}
    -D APP_DEVICE_KIND=\\"{spec.device_kind}\\"
    -D APP_FIRMWARE_VERSION=\\"{spec.firmware_version}\\"
    -D APP_FIRMWARE_BUILD_ID=\\"{spec.firmware_build_id}\\"
    -D APP_FIRMWARE_PROJECT=\\"{spec.project_slug}\\"
    -D APP_FIRMWARE_TARGET=\\"{spec.env_name}\\"
    -D APP_FIRMWARE_FRAMEWORK=\\"arduino\\"
    -Wl,-u,INAS_FIRMWARE_MANIFEST
    ${{user.network_flags}}
lib_deps =
    bblanchon/ArduinoJson@^7.1.0
    esphome/ESPAsyncWebServer-esphome@^3.3.0
    links2004/WebSockets@^2.6.1
    knolleary/pubsubclient@^2.8

[common]
build_flags =
    -D ARDUINO_USB_CDC_ON_BOOT=1
    -D ARDUINO_USB_MODE=1
    -D BOARD_HAS_PSRAM=1
    -D CONFIG_ASYNC_TCP_QUEUE_SIZE=65536
    -D CONFIG_ASYNC_TCP_RUNNING_CORE=1
    -D CONFIG_ASYNC_TCP_STACK_SIZE=4096
    -D WS_MAX_QUEUED_MESSAGES=1
    -D MQTT_MAX_PACKET_SIZE=65535
    -D MQTT_KEEPALIVE=60
    -D MQTT_SOCKET_TIMEOUT=60
    -I src/app/inc
    -I src/hal/inc
    -I lib/ina-client-common/src/app/inc
    -I lib/ina-client-common/src/hal/inc
"""


def _render_makefile(spec: DeviceProjectSpec) -> str:
    return f"""DEVICE_ID := {spec.project_slug}
DEVICE_KIND := {spec.device_kind}
DEVICE_NAME := {spec.display_name}
DEVICE_VERSION := {spec.firmware_version}
PIO_ENV := {spec.env_name}
ESP_CHIP := esp32s3
FLASH_SIZE := 8MB
HAS_FILESYSTEM := 1

include ../common/make/esp32-firmware.mk

.PHONY: remote-upload remote-monitor
remote-upload:
\t$(PIO_RUN) remote run --target upload --environment $(PIO_ENV)

remote-monitor:
\t$(PIO_RUN) remote device monitor --environment $(PIO_ENV)
"""


def _render_app_cpp(spec: DeviceProjectSpec) -> str:
    return APP_CPP_TEMPLATE.replace("__CLASS_NAME__", spec.class_name).replace("__DISPLAY_NAME__", spec.display_name)


def _render_default_env(spec: DeviceProjectSpec) -> str:
    return f"""[user]
network_flags =
    -D APP_INITIAL_SETTING_SSID="\\"{spec.setup_ap_ssid}\\""
"""


def _render_readme(spec: DeviceProjectSpec) -> str:
    return f"""# {spec.display_name}

PlatformIO firmware project for `{spec.device_kind}`.

This project is generated from the INAS device scaffold and uses the shared
client library at `lib/ina-client-common`.

## Setup

```bash
cd client-devices/{spec.project_slug}
make build
make check-firmware
```

Local build settings live in `.env.user.ini`. The checked-in
`default.env.user.ini` is safe to copy or regenerate.

## Device Contract

- `APP_DEVICE_KIND`: `{spec.device_kind}`
- Firmware project: `{spec.project_slug}`
- Board environment: `{spec.env_name}`

Keep connected sensors, actuators, payload schema, and pin assignment fixed for
this device kind. If the hardware contract changes materially, create a new
device project and a new three-letter device kind.
"""


def _render_agents_md(spec: DeviceProjectSpec) -> str:
    return f"""# Repository Guidelines

## Project Structure

- `src/main.cpp` is the firmware entry point.
- `src/app/src/app.cpp` contains `{spec.class_name} : AppDevice`.
- `src/app/inc` contains device-specific app headers.
- `src/hal` is reserved for device-specific HAL drivers.
- `lib/ina-client-common` is a symlink to the shared INAS client library.
- `data/` contains LittleFS payload files.
- `test/` is reserved for PlatformIO tests.

## Commands

- `make build`: compile firmware for `{spec.env_name}`.
- `make check-firmware`: build and verify the embedded OTA manifest.
- `make upload`: build and upload to a locally connected board.
- `make merged-bin`: create a single flashable provisioning image.

## Device Contract

`{spec.device_kind}` is a fixed device kind. Do not add runtime capabilities or
ad-hoc pin profiles inside this project. If the hardware role changes, create a
new device project with a new three-letter `APP_DEVICE_KIND`.
"""


def _render_docs_readme(spec: DeviceProjectSpec) -> str:
    return f"""# {spec.display_name} Docs

Document the fixed `{spec.device_kind}` hardware contract here:

- pin assignment
- connected sensors and actuators
- MQTT status payload
- runtime config payload
- OTA and release checklist
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new INAS PlatformIO client device project.")
    parser.add_argument("project", help="Project directory name in lowercase kebab-case, e.g. soil-device")
    parser.add_argument("device_kind", help="Three-letter uppercase device kind, e.g. SOI")
    parser.add_argument("--display-name", help="Human-readable device name")
    parser.add_argument("--board", default="seeed_xiao_esp32s3", help="PlatformIO board id")
    parser.add_argument("--env", dest="env_name", help="PlatformIO environment name; defaults to --board")
    parser.add_argument("--firmware-version", default="0.1.0", help="Initial firmware version")
    parser.add_argument("--firmware-build-id", help="Initial firmware build id; defaults to timestamp+git")
    parser.add_argument("--setup-ap-ssid", help="Default setup AP SSID; defaults to INAS-<kind>-setup")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without writing files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = repo_root_from_script()
    try:
        spec = build_spec(
            project_slug=args.project,
            device_kind=args.device_kind,
            display_name=args.display_name,
            board=args.board,
            env_name=args.env_name,
            firmware_version=args.firmware_version,
            firmware_build_id=args.firmware_build_id,
            setup_ap_ssid=args.setup_ap_ssid,
            repo_root=repo_root,
        )
        project_root = create_device_project(spec, repo_root, dry_run=args.dry_run)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    if not args.dry_run:
        print(f"Created {project_root}")
        print(f"Next: cd {project_root.relative_to(repo_root)} && make build && make check-firmware")
    return 0


GITIGNORE_TEMPLATE = """# Device-local PlatformIO state
.pio/
.pio-core/

# Local secrets; examples remain version-controlled
.env
.env.*
!.env.example
!.env.*.example
"""

PARTITIONS_TEMPLATE = """# Name,   Type, SubType, Offset,  Size, Flags
# Note: if you have increased the bootloader size, make sure to update the offsets to avoid overlap
nvs,      data, nvs,     0x9000,  0x5000,
otadata,  data, ota,     0xe000,  0x2000,
app0,     app,  ota_0,   0x10000, 0x330000,
app1,     app,  ota_1,   0x340000,0x330000,
storage,  data, spiffs,  0x670000,0x180000,
coredump, data, coredump,0x7F0000,0x10000,
"""

MAIN_CPP_TEMPLATE = """#include "app.h"

#include <Arduino.h>

static bool s_app_initialized = false;

void setup()
{
    s_app_initialized = (app_init() == 0);
}

void loop()
{
    if (s_app_initialized)
    {
        app_loop();
        return;
    }

    delay(1000);
}
"""

APP_H_TEMPLATE = """#ifndef __APP_H__
#define __APP_H__

int app_init();
void app_deinit();
void app_loop();

#endif // __APP_H__
"""

APP_RESOURCE_CPP_TEMPLATE = """#include <stdio.h>

#include "app_config.h"

AppConfig appConfig = AppConfig();
"""

APP_CPP_TEMPLATE = """#include "app.h"

#include <Arduino.h>
#include <string.h>

#include "app_def.h"
#include "app_device.h"
#include "app_network.h"

class __CLASS_NAME__ : public AppDevice
{
public:
    bool apply_runtime_config_json(const uint8_t *payload, size_t length) override
    {
        (void)payload;
        (void)length;
        m_runtime_config_received = true;
        m_runtime_config_valid = true;
        return true;
    }

    bool has_valid_runtime_config() const override
    {
        return m_runtime_config_valid;
    }

    bool is_runtime_config_received() const override
    {
        return m_runtime_config_received;
    }

protected:
    const char *device_name() const override
    {
        return "__DISPLAY_NAME__";
    }

    bool on_initialize() override
    {
        return true;
    }

    void prepare_runtime_config_request() override
    {
        m_runtime_config_received = false;
    }

    void on_runtime_config_ready(bool config_received) override
    {
        Serial.printf("Runtime config ready: received=%s valid=%s\\n",
                      config_received ? "true" : "false",
                      m_runtime_config_valid ? "true" : "false");
    }

    const char *runtime_ntp_server() const override
    {
        return "pool.ntp.org";
    }

    int32_t runtime_timezone_offset_sec() const override
    {
        return 32400;
    }

    AppDeviceCycleResult run_device_cycle(const AppDeviceWakeContext &context) override
    {
        (void)context;
        AppDeviceCycleResult result = {};
        result.next_sleep_sec = kDefaultSleepSec;
        result.publish_debug_log = false;
        return result;
    }

    bool publish_device_status(const AppDeviceWakeContext &context,
                               const AppDeviceCycleResult &cycle_result) override
    {
        char payload[512];
        snprintf(payload,
                 sizeof(payload),
                 "{\\"seq\\":%lu,\\"device_kind\\":\\"%s\\",\\"firmware_version\\":\\"%s\\",\\"firmware_build_id\\":\\"%s\\",\\"network_connected\\":%s,\\"runtime_config_valid\\":%s,\\"config_received\\":%s,\\"time_synced\\":%s,\\"ota_update_attempted\\":%s,\\"next_sleep_sec\\":%lu,\\"uptime_ms\\":%lu}",
                 static_cast<unsigned long>(context.seq_id),
                 APP_DEVICE_KIND,
                 APP_FIRMWARE_VERSION,
                 APP_FIRMWARE_BUILD_ID,
                 context.network_connected ? "true" : "false",
                 m_runtime_config_valid ? "true" : "false",
                 context.config_received ? "true" : "false",
                 context.time_synced ? "true" : "false",
                 context.ota_update_attempted ? "true" : "false",
                 static_cast<unsigned long>(cycle_result.next_sleep_sec),
                 static_cast<unsigned long>(millis()));

        Serial.printf("Sending status: %s\\n", payload);
        const bool sent = app_network_send(APP_MSG_TYPE_STATUS,
                                           reinterpret_cast<const uint8_t *>(payload),
                                           strlen(payload),
                                           context.seq_id);
        if (sent)
        {
            app_network_flush(APP_MQTT_STATUS_PUBLISH_DRAIN_MS);
        }
        return sent;
    }

private:
    static constexpr uint32_t kDefaultSleepSec = 300;
    bool m_runtime_config_received = false;
    bool m_runtime_config_valid = true;
};

static __CLASS_NAME__ s_device;

int app_init()
{
    AppDeviceInitializeOptions options;
    options.setup_ap_enabled = true;
    options.start_network = true;
    options.print_littlefs_files = false;
    return s_device.initialize(options);
}

void app_deinit()
{
}

void app_loop()
{
    s_device.loop();
}
"""

HAL_README_TEMPLATE = """Device-specific HAL code goes here.
"""

INCLUDE_README_TEMPLATE = """This directory is intended for project header files.
"""

LIB_README_TEMPLATE = """Project-specific libraries go here.

The shared INAS client framework is linked as `ina-client-common`.
"""

TEST_README_TEMPLATE = """PlatformIO tests go here.
"""


if __name__ == "__main__":
    raise SystemExit(main())
