# OTA Update Specification

Japanese version:

- [jp/ota_update_spec.md](jp/ota_update_spec.md)

This document specifies OTA firmware update behavior for the INA Water
Controller.

## Scope

Included:

- Firmware image OTA update.
- MQTT update offer and status messages.
- Firmware binary HTTP delivery from the hub or management server.
- Integration with the existing deep sleep wake cycle.

Excluded:

- Delivering firmware binary over MQTT.
- HTTPS OTA before device-side certificate validation exists.
- Updating bootloader or partition table over OTA.

## Firmware Artifact

Firmware binaries must embed `INAS_FW_MANIFEST_V1`. Before uploading to the hub,
run:

```bash
make check-firmware
```

The hub upload/register API calculates:

- size
- sha256
- device kind
- firmware version
- generated HTTP URL

Firmware is stored under:

```text
WORK_DIR/firmware/<device_kind>/<version>/firmware.bin
```

## Delivery Model

MQTT is the control path. HTTP is the binary delivery path.

```text
Hub -> MQTT OTA offer -> Device
Device -> HTTP GET firmware.bin -> Hub
Device -> MQTT OTA status -> Hub
```

The offer URL is generated from `FIRMWARE_BASE_URL` when set. Otherwise the hub
uses `FIRMWARE_HOSTNAME`, OS `HOSTNAME`, or the OS hostname with
`FIRMWARE_PORT` / `HUB_HTTP_PORT`.

Current device firmware accepts only `http://` OTA URLs.

## Wake Cycle Behavior

On wake, the device:

1. Connects to network and MQTT.
2. Requests runtime config.
3. Checks retained OTA offer or OTA check interval.
4. Validates device kind, version, size, and sha256.
5. Downloads the firmware over HTTP.
6. Writes to the inactive OTA slot.
7. Reboots into the new firmware.
8. Confirms the running firmware after reboot.
9. Publishes OTA status.

Irrigation should be skipped while an OTA update is in progress.

## Status

The device publishes OTA status for major states:

- offer received
- offer ignored
- download started
- download failed
- sha256 mismatch
- write failed
- reboot pending
- update confirmed

Status payloads must include enough information to diagnose version, URL,
device kind, and failure reason without exposing secrets.
