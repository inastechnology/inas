# Compact Debug Log Format

Japanese version:

- [jp/debug_log_format.md](jp/debug_log_format.md)

This document defines the compact binary debug log published by the device over
MQTT.

## Purpose

The debug log helps diagnose wake-cycle failures that are difficult to understand
from normal status alone:

- Wi-Fi or MQTT connection failure.
- Missing or invalid runtime config.
- NTP synchronization failure.
- Schedule evaluation result.
- Irrigation start, skip, or output start failure.
- Retained OTA offer handling.
- Status publish result.
- Next sleep seconds.

Secrets such as SSID, Wi-Fi password, and MQTT password are never included in the
payload.

## Runtime Config

Enable with:

```json
{
  "debug_log_on_wake": true
}
```

The payload is sent only when the wake cycle has valid runtime config and
network connection is available.

## Payload

The payload is binary bytes, not a UTF-8 string.

General layout:

- Header: 16 bytes.
- Record: 13 bytes each.
- A 512-byte MQTT payload can carry up to 38 records.

Records are stored in priority order so that the most important events fit in a
single publish.

See firmware `app_debug_log.h` for file id and event code mappings.
