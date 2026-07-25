# INAS Architecture Layering Policy

Japanese version:

- [jp/ARCHITECTURE_LAYERING_POLICY.md](jp/ARCHITECTURE_LAYERING_POLICY.md)

## Purpose

This document defines the system-wide layer boundaries for INAS. Use it before
adding a feature, device, sensor, actuator, cloud integration, UI flow, or data
model.

The main rule is simple: name each layer by the responsibility it owns, not by
the product that currently uses it. Product behavior belongs to product/device
orchestration. Reusable boundaries belong to common layers.

## System Layers

| Layer | Owns | Must not own |
|---|---|---|
| Crop system orchestration | Crop-specific goals such as strawberry drip cultivation, target ranges, automation level, action approval, result evaluation | New monolithic device types for every crop workflow |
| Hub application | Device orchestration, runtime config distribution, MQTT handling, field/device placement, measurement normalization, action plans, OTA decisions, farmer-facing UI/API | Firmware GPIO behavior, sensor register maps, power sequencing inside devices |
| Hub repositories/storage | Persistence, schema translation, history queries, file/artifact storage | UI wording, device electrical behavior, MQTT transport policy |
| Hub adapters/connectors | Cloudflare, Turso, S3-compatible storage, weather, Instagram, camera/RTSP, external APIs | Core domain decisions that should work without that connector |
| MQTT/API contracts | Stable message shapes, topics, status/config/OTA contracts | Local implementation shortcuts or hardware details |
| Device App | `device_kind`, product behavior, runtime config parsing, schedule/control policy, sensor sampling order, status payload shape | Raw hardware implementation when a common HAL/protocol layer exists |
| Firmware HAL | Physical hardware primitives such as GPIO-switched power, ADC, UART/RS485 direction control, camera, audio | Product policy, MQTT payloads, crop rules, runtime config parsing |
| Firmware protocol driver | Protocol/register mapping over a bus, such as Modbus sensor register conversion | Power sequencing, irrigation policy, hub persistence |

## Cross-Layer Rules

- The hub orchestrates systems. Devices measure or actuate through fixed
  `device_kind` contracts.
- Crop-specific systems, such as strawberry drip cultivation, are compositions
  of devices and hub policy. Do not create a giant crop-specific firmware
  device unless the hardware contract itself changes.
- A `device_kind` fixes the hardware role and payload contract. If that contract
  changes materially, create a new firmware project and `device_kind`.
- Hardware-only variants, such as supply voltage, MOSFET rating, enclosure, or
  whether a WTR build drives a small low-voltage load, are hardware profiles
  inside the existing `device_kind` unless the payload contract or hub behavior
  changes.
- Reusable mechanisms belong in common layers. Examples: MQTT transport, OTA,
  RS485 bus handling, Modbus frame handling, GPIO-switched power, storage
  repositories, and Cloudflare provisioning helpers.
- Product decisions belong above reusable mechanisms. Examples: when to water,
  what threshold to use, how to interpret missing feedback, and what UI wording
  a grower sees.
- MOSFET output names and controlled-load descriptions are hub/device App
  configuration metadata. The electrical primitive remains a power switch or
  output channel; the HAL must not know whether the load is a pump, valve,
  relay, sensor rail, or field-specific label.
- Do not add wrapper layers whose only purpose is to group existing lower-level
  calls under a product name. A wrapper must introduce a real boundary, not just
  a rename.

## Hub Layer Rules

- Flask routes should handle request/response shape and call services.
- Services should hold orchestration and domain decisions.
- Repositories should persist and query data without UI wording or transport
  details.
- Connectors/adapters should isolate external systems. The core hub behavior
  should remain understandable without reading Cloudflare, S3, Instagram, or
  weather-provider code.
- Local Hub and Cloud Hub are separate product applications over shared
  contracts. Local Hub keeps its existing per-installation Turso/libSQL and
  direct MQTT control. Cloud Hub may use a directory adapter plus one dedicated
  Turso DB per customer, but caller input must never choose a DB. Do not import
  Cloud multi-tenant routing or credentials into Local Hub or Edge Runtime.

## Device Firmware Rules

Detailed firmware rules live in
[../client-devices/docs/firmware_layering_policy.md](../client-devices/docs/firmware_layering_policy.md).

In short:

- HAL names describe hardware primitives, not device kinds.
- The device App may compose common HAL modules when the composition is product
  behavior.
- Protocol drivers map bus/register protocols and do not control power rails or
  make product decisions.
- WRS uses `hal_power_switch`, `hal_rs485_bus`, and
  `hal_rs485_sensor_protocol`; it must not reintroduce a `hal_wrs` wrapper
  unless a real new hardware primitive appears.
- A battery or low-voltage watering build is a WTR hardware profile when it
  still performs the WTR role: local irrigation output plus local soil moisture
  feedback. Do not create a new `device_kind` for that hardware-only difference.

## Data And UI Rules

- Measurements use metric definitions plus time-series values. Do not create a
  new fixed table column for every sensor unless the query model truly needs it.
- UI should present farmer-facing language first. Raw payloads, register names,
  and debug fields belong in detail views.
- Runtime config may carry display metadata such as `mosfet_switches` so the
  hub can show "drip line A" instead of only `channel_mask=1`. That metadata is
  not a firmware HAL contract.
- Data placement is part of the model: field, section, ridge/bed, or point.
  Do not infer placement from device IDs or MQTT topics alone.

## Review Checklist

Before implementing a change:

1. Which layer owns the decision?
2. Which contract crosses the next layer boundary?
3. Is the new module named after a responsibility rather than a product?
4. Could this be App/service orchestration over an existing common primitive?
5. Does the change leak UI wording into persistence, hardware behavior into hub
   services, or crop policy into firmware HAL?
6. What build, test, or link check proves the boundary still works?
