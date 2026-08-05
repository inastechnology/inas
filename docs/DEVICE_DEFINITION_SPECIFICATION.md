# Device Definition Specification

Japanese version: [jp/DEVICE_DEFINITION_SPECIFICATION.md](jp/DEVICE_DEFINITION_SPECIFICATION.md)

## Purpose

A Device Definition tells the hub what a firmware product can measure, operate,
configure, and display. It keeps the hub UI and the JSON sent to a device aligned
with the firmware implementation without coupling a running hub to a firmware
source directory.

The stable terms are:

- **Device Definition**: static product metadata owned by a firmware project.
- **Runtime Config**: the per-device JSON stored by the hub and sent over MQTT.
- **Installation settings**: user choices stored by the hub, such as the connected
  equipment name, placement, and whether an optional sensor is installed.

## Goals

- Make each firmware project the source of truth for its supported sensors,
  outputs, actions, status values, and Runtime Config shape.
- Build device screens from the registered definition instead of hard-coded hub
  lists.
- Show every value that the product supports and distinguish `not connected`,
  `not measured`, and a measured value. Missing data must never be displayed as
  zero.
- Hide electronic and protocol details from normal users. Stable slot IDs,
  terminals, masks, buses, and pins are not editable in the normal UI.
- Preserve existing hub database values during migration.

## Non-goals

- A definition does not add firmware behavior or execute code.
- A definition does not replace firmware validation or safety interlocks.
- A definition does not describe arbitrary circuit wiring. Fixed-function ports
  remain fixed; generic ports offer only the load types implemented by firmware.
- The hub does not read firmware directories at runtime.

## Ownership And Files

Each firmware project owns a `hub-definition/` directory:

```text
client-devices/<device>/hub-definition/
  device.json
  runtime-config.schema.json
  status.schema.json
  ui.json
  actions.json
```

`device.json` contains identity, fixed sensor slots, fixed or assignable output
slots, and references to the other files. Slot IDs are stable machine keys. They
may be shown only in advanced diagnostics.

The build script validates and combines these files into a generated registry in
the hub package. Production uses that registry, so installing or starting the hub
does not require the firmware source tree.

## Runtime Flow

```text
firmware project/hub-definition
              |
              | build and validate
              v
      generated hub registry
              |
       +------+------------------+
       |                         |
       v                         v
 definition-driven UI     Runtime Config projection
       |                         |
       | user choices            | device-kind keys only
       v                         v
 existing hub database       MQTT reply/push
```

The hub keeps its existing stored configuration as the compatibility source.
Before a reply or push, it projects that stored object through the selected
Device Definition. Unknown legacy keys remain in the database but are not sent
to a firmware type that does not declare them.

`runtime-config.schema.json` may declare `fixed_values` for product invariants
that are not user choices. Fixed dot-path values override stored legacy values
in every Runtime Config preview, reply, and push. Each fixed path must be below
a top-level key listed in `send_keys`.

## UI Rules

- The primary screen uses farmer-facing names and pictures: for example,
  `water pump`, `mixing pump`, or `soil sensor`, not switch technologies or bus
  addresses.
- The screen first shows the current installation. Editing is a separate action.
- Fixed FGT roles cannot be reassigned. Generic WTR/WRS routes can select only
  the equipment categories declared by their output slot.
- Optional sensors that are disabled show `not connected`. Enabled sensors with
  no sample show `not measured`. Both remain visible so the user understands the
  device capability.
- Calibration opens as a guided task and the adjusted value is summarized on
  the action button.
- Advanced settings may expose diagnostic values, but changing them still
  requires an allowed field in the definition.
- A scheduled actuator product may declare `ui.scheduled_operation`. The hub
  uses its enable, schedule, program, and required-output paths to distinguish a
  usable schedule from one that cannot actuate, and warns before saving or
  pushing a non-actuating configuration.

## Compatibility And Failure Handling

- Existing database rows are not rewritten when definitions are introduced.
- Unknown device kinds use a small read-only fallback definition and retain the
  legacy configuration path.
- A missing or invalid generated definition fails the registry build. A running
  hub never loads an unvalidated definition from a device or network payload.
- `definition_version` versions presentation and projection metadata;
  `schema_version` versions the definition file format. Firmware Runtime Config
  compatibility remains the firmware's responsibility.

## Implementation And Verification

1. Add definitions to every supported firmware project.
2. Generate and validate the hub registry.
3. Read labels, sensor cards, charts, output cards, and editable sections from
   the registry.
4. Project MQTT reply and push JSON through `runtime_config.send_keys`.
5. Add regression tests for registry completeness, missing measurements, fixed
   slots, legacy database preservation, and per-kind MQTT payloads.
6. Run the hub demo for every registered kind, capture the screens, inspect the
   images, and compare the exact Runtime Config preview with the expected keys.

## Related Documents

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md)
- [ARCHITECTURE_LAYERING_POLICY.md](ARCHITECTURE_LAYERING_POLICY.md)
- [../hub/doc/HUB_ADMIN_UX_IMPLEMENTATION.md](../hub/doc/HUB_ADMIN_UX_IMPLEMENTATION.md)
