# Client Devices

Device firmware projects are organized by device type.

```text
client-devices/
  common/lib/ina-client-common/
  watering-device/
```

## Layering Policy

- `common/lib/ina-client-common`: shared client firmware library.
- `<device>/src/app`: device-specific `AppDevice` subclass, runtime config, and
  product behavior.
- `<device>/src/hal`: device-specific HAL drivers for sensors, actuators, pins,
  audio, camera, and other hardware peripherals.
- `<device>/platformio.ini`: board, build flags, device kind code, and local
  dependencies for that device.

The common library should contain behavior that can be reused by multiple device
types, such as boot/wake lifecycle, Wi-Fi/MQTT setup, setup AP transition, OTA
control flow, config persistence, task helpers, time sync, and common utilities.

The device project should contain behavior that changes per product, such as
watering logic, sensor sampling, pin mapping, runtime configuration schema, and
top-level application orchestration.

## Adding A Device

1. Create `client-devices/<device-name>/`.
2. Add device-specific `src/app`, `src/hal`, `platformio.ini`, and `Makefile`.
3. Implement one concrete `AppDevice` subclass.
4. Link the shared library into the device's `lib/` directory.
5. Assign a three-letter uppercase device kind code in the device
   `platformio.ini`.
6. Build and verify from the device directory.

The concrete device class should call `initialize()` with
`AppDeviceInitializeOptions`. For example, keep `setup_ap_enabled=true` for
devices that should fall back to setup AP mode when Wi-Fi/MQTT settings are
missing.

Example symlink from inside `client-devices/<device-name>/lib`:

```bash
ln -s ../../common/lib/ina-client-common ina-client-common
```

## Development Environment

Use Linux or WSL2. Client device projects rely on symbolic links for shared
PlatformIO libraries. Native Windows builds are not supported.
