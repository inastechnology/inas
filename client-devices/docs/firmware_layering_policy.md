# Client Firmware Layering Policy

Japanese version:

- [jp/firmware_layering_policy.md](jp/firmware_layering_policy.md)

## Purpose

This document defines the layer boundary for INAS client firmware. Use it when
adding a device, sensor, actuator, bus, or protocol driver.

The goal is to keep hardware abstractions reusable and understandable. Do not
create a HAL module whose only purpose is to group existing HAL calls under a
device kind or product name.

## Layer Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Common App | Boot/wake lifecycle, setup AP, Wi-Fi/MQTT transport, OTA, time sync, debug log, shared task/config utilities | Device-specific runtime config schema, pin maps, sensor/actuator behavior |
| Device App | `device_kind`, product behavior, runtime config parsing, schedule/control policy, sensor sampling order, payload shape | Raw GPIO/UART register handling when a common HAL exists |
| HAL | Physical hardware primitives such as switched MOSFET/power rails, ADC, camera, audio, RS485 UART/DE, I2C/SPI devices | Product policy, device kind semantics, MQTT payloads, runtime config parsing |
| Protocol Driver | Wire/register protocol over a bus, such as Modbus register maps for RS485 sensors | Power sequencing, irrigation decisions, MQTT, sleep scheduling |
| Hub | Device orchestration, UI, config distribution, persistence, cloud integration | Firmware GPIO/pin behavior |

## HAL Rules

- A HAL module name must describe a hardware primitive or a concrete peripheral,
  not a product or `device_kind`.
- Prefer reusable common HAL modules when the same hardware primitive can appear
  in more than one device.
- A device-specific HAL is allowed only when the device has a real hardware
  primitive that is not reusable yet, such as a specific camera wiring,
  board-local ADC circuit, or sensor electrical behavior.
- Do not create a wrapper such as `hal_<device_kind>` if it only delegates to
  existing HAL modules or renames pins.
- Do not put MQTT topics, status JSON fields, runtime config parsing, schedule
  decisions, or crop/product policy in HAL.
- Pin selection belongs in `platformio.ini`, a small device App constant block,
  or a focused pin map helper. Pin selection alone is not enough reason to
  create a new HAL layer.

## App Rules

- The device App owns orchestration: when to power sensors, when to read them,
  when to irrigate, when to stop, and what status to publish.
- The device App may compose multiple common HAL modules directly when the
  composition represents product behavior.
- Timed irrigation behavior is App behavior unless it is generalized as a
  reusable timed output primitive.
- A device App should depend on HAL/protocol headers, but HAL/protocol modules
  must not include device App headers.

## RS485 Rules

Keep RS485 in three layers:

1. `hal_rs485_modbus`: UART, DE/RE control, Modbus frame send/receive, CRC, and
   response timeout.
2. `hal_rs485_bus`: hardware bus boundary exposed as register read/write style
   operations.
3. `hal_rs485_sensor_protocol`: sensor-specific register maps and unit
   conversion over the bus.

The device App decides which sensors are enabled, powers the sensor rail, calls
the protocol driver, and interprets missing sensors as `*_ok=false`.

Adding another RS485 sensor should normally add or extend a protocol driver, not
create a new device HAL wrapper.

## MOSFET And Power Rules

- Use `hal_power_switch` for MOSFET-switched power rails or simple on/off
  outputs.
- Use multiple `hal_power_switch_t` instances when a device has multiple
  independent outputs, such as irrigation output 1, irrigation output 2, and
  12V sensor power.
- The meaning of an output, such as pump, valve, solenoid, or relay, belongs to
  device App config and documentation. The HAL only switches the electrical
  output.
- If a reusable timed multi-channel output primitive is needed, implement it as
  a generic common HAL, not as a device-kind-specific HAL.

## WRS Application

`WRS` uses:

- `hal_power_switch` instances for irrigation output 1, irrigation output 2,
  and switched 12V sensor power.
- `hal_rs485_bus` for the RS485 hardware boundary.
- `hal_rs485_sensor_protocol` for soil/PAR sensor register maps.
- `app_wrs_runtime_config` and `app.cpp` for irrigation policy, schedule
  handling, sensor power sequencing, and MQTT status fields.

`WRS` must not define a `hal_wrs` wrapper unless WRS later gains a concrete
hardware primitive that cannot be expressed by existing HAL modules.

## Review Checklist

Before adding a new firmware module:

1. Does the module name describe hardware, protocol, or product behavior?
2. If it is HAL, can another device reuse it without knowing the current
   `device_kind`?
3. If it wraps existing HAL calls, is it adding a real hardware abstraction or
   only grouping product behavior?
4. Does any HAL include App headers or parse runtime config JSON?
5. Does any protocol driver control power rails or make product decisions?
6. Could the change be simpler as App orchestration plus existing common HALs?
