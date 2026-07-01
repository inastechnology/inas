# ina-client-common

Shared PlatformIO library for INAS client firmware.

This library is consumed from each device project through a symbolic link:

```text
client-devices/<device>/lib/ina-client-common
  -> ../../common/lib/ina-client-common
```

The library is intentionally limited to reusable client firmware behavior. Keep
device-specific application flow, pin maps, sensor logic, actuator logic, and
runtime config schemas inside each device project.

## Device Lifecycle

`AppDevice` provides the common boot and wake-cycle lifecycle:

- serial/debug initialization
- LittleFS mount and saved connection config loading
- setup AP handling, controlled by `AppDeviceInitializeOptions::setup_ap_enabled`
- Wi-Fi/MQTT startup and reconnect
- runtime config request/wait
- OTA request/offer handling
- NTP/RTC time synchronization
- status/debug-log publish hooks
- deep sleep scheduling

Device projects should implement one concrete `AppDevice` subclass. The subclass
also satisfies `AppDeviceAdapter`, so common transport code can call
device-owned runtime configuration behavior without including device headers.

Each device project must:

1. Subclass `AppDevice`.
2. Implement runtime config adapter methods.
3. Implement device hooks such as `on_initialize()`, `run_device_cycle()`, and
   `publish_device_status()`.
4. Call `initialize()` with the desired `AppDeviceInitializeOptions`.

Device projects must define their own three-letter device kind code, for
example:

```ini
build_flags =
    -D APP_DEVICE_KIND=\"WTR\"
```
