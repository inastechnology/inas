# OTA Implementation Traceability

Japanese version:

- [jp/ota_implementation_traceability.md](jp/ota_implementation_traceability.md)

This document maps OTA specification items to implementation layers and files.

| Area | Responsibility | Files |
|---|---|---|
| Common lifecycle | Boot, setup AP mode, network/reconnect, runtime config request, OTA, time sync, debug log, deep sleep | `../common/lib/ina-client-common/src/app/inc/app_device.h`, `../common/lib/ina-client-common/src/app/src/app_device.cpp` |
| Device orchestration | Concrete `AppDevice`, irrigation decision, OTA-related irrigation skip, normal status publish | `src/app/src/app.cpp` |
| Device adapter | Bridge from common transport to device-specific runtime config handling | `src/app/src/app.cpp`, `../common/lib/ina-client-common/src/app/inc/app_device_adapter.h` |
| Common OTA app | Device kind validation, retained offer validation, OTA status payload, HTTP download, SHA-256 validation, inactive slot write, post-reboot confirmation | `../common/lib/ina-client-common/src/app/inc/app_ota.h`, `../common/lib/ina-client-common/src/app/src/app_ota.cpp` |
| Firmware manifest | Embedded firmware metadata marker | common firmware manifest implementation |
| Hub artifact registry | Firmware upload/register, size, sha256, generated URL | hub OTA service and web server |
| Hub HTTP delivery | `GET /firmware/<device_kind>/<version>/firmware.bin` | hub web server |
| MQTT offer/status | OTA offer and status topics | common OTA app and hub MQTT handling |

Use this file when changing OTA behavior to confirm that firmware, hub API,
artifact storage, MQTT control, and HTTP binary delivery remain aligned.
