# Client Device Common Code

`client-devices/common` contains code that is shared by client device firmware
projects.

The PlatformIO library is:

```text
client-devices/common/lib/ina-client-common
```

Device projects use this library through a symbolic link from their local
`lib/` directory. This keeps each device project buildable as a normal
PlatformIO project while avoiding duplicated framework code.

## Current Boundary

The common library currently owns:

- boot/runtime definitions and common build-time defaults
- `AppDevice` boot/wake lifecycle abstraction
- Wi-Fi and MQTT setup flow
- MQTT publish/subscribe transport
- OTA request, offer validation, status, download, and install flow
- device adapter interface for device-owned runtime configuration handling
- setup portal handling
- time synchronization
- task helpers
- debug log helpers
- LittleFS-backed config storage
- shared utilities

Device projects currently own:

- device kind assignment, such as `WTR`
- concrete `AppDevice` subclass and product-specific App flow
- runtime configuration schema and persistence
- sensor, actuator, camera, and audio behavior
- board pin mapping
- device-specific HAL drivers

`app_network` must not include a device runtime configuration header directly.
`AppDevice::initialize()` registers the concrete device as the active
`AppDeviceAdapter` before the common network stack starts.
