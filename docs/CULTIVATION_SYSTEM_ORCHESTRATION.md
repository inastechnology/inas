# Cultivation System Orchestration

Japanese version:

- [jp/CULTIVATION_SYSTEM_ORCHESTRATION.md](jp/CULTIVATION_SYSTEM_ORCHESTRATION.md)

## Purpose

This document records the INAS design policy for crop-specific systems such as
a strawberry drip cultivation system. A crop system should not be treated as one
large device. It should be modeled as a system profile that the device hub
orchestrates from multiple simpler devices.

The device boundary stays stable. The crop-specific behavior lives in the hub
policy, field context, device placement, action history, and evaluation loop.

## Core Policy

A crop-specific cultivation system is a composition:

```text
strawberry-drip-system-01
  field / bed / point context
  environment sensor device
  irrigation instruction device
  irrigation feedback soil moisture sensor
  hub orchestration policy
```

The hub owns orchestration. Devices own measurement or actuation. A device
should not need to understand that it is growing strawberries unless that
knowledge changes its fixed hardware and payload contract.

## Device Roles

| Role | Responsibility | Example |
|---|---|---|
| Environment sensor device | Observes broad environment values used for decisions | `ENV` with PAR/PPFD, air temperature, humidity, soil EC/pH/NPK |
| Soil feedback device | Measures the moisture response at the irrigation target | `SOI`, WTR built-in soil moisture, WRS RS485 soil sensor, or another colocated probe |
| Irrigation instruction device | Turns the water source on and off | WTR/WRS output, SwitchBot Plug Mini controlling an AC/DC adapter or pump |
| Device hub | Compares context and measurements, decides, commands, verifies, logs | Local hub policy and action plans |

For strawberry drip cultivation, the irrigation instruction device should be
paired with a soil moisture sensor at the same bed, ridge, or representative
point. The plug or pump switch alone is not enough to prove that irrigation
actually reached the root zone.

## Irrigation Feedback Rule

Irrigation is an action with an expected sensor response. The hub should record
and evaluate that response.

Minimum sequence:

1. Read soil moisture before irrigation.
2. Start irrigation with a bounded duration.
3. Stop irrigation even if later verification fails.
4. Read soil moisture during or after the settling window.
5. Record the before/after delta and classify the result.

Response classification:

| Result | Meaning | Hub behavior |
|---|---|---|
| `expected_response` | Moisture increased within the expected range | Store as successful irrigation evidence |
| `weak_response` | Moisture increased, but less than expected | Flag possible short duration, emitter clog, sensor placement issue, or dry medium |
| `no_response` | Moisture did not increase | Stop repeated automatic irrigation and alert for empty tank, pump failure, plug failure, blocked tube, or misplaced sensor |
| `excessive_response` | Moisture increased too much or too fast | Alert for over-irrigation, leak, poor drainage, or unsuitable duration |

The expected delta should be crop, medium, sensor, and placement dependent. Do
not hard-code one global value as a universal truth. Start with conservative
thresholds and adjust from field history.

## SwitchBot Plug As An Irrigation Instruction Device

SwitchBot Plug Mini is a practical first actuator when it is cheaper and safer
than building an ESP32 relay device for AC power control. In INAS, treat it as
an external actuator adapter rather than a full irrigation device.

Recommended boundary:

```text
device hub
  -> SwitchBot Plug command: turn on/off
  -> AC/DC adapter or pump power
  -> drip line
  -> soil feedback sensor confirms root-zone response
```

Operational rules:

- The hub must send duration-bounded irrigation commands. A plain `turnOn`
  without a planned `turnOff` is not an irrigation command.
- The hub should retry `turnOff` and verify plug state or current when
  available.
- The hub should pair the plug with a soil moisture sensor placement. For
  example, `strawberry-irrigation-plug-01` may be paired with
  `strawberry-soil-bed-a-01`.
- The hub should also use physical safety limits such as tank capacity, leak
  detection, maximum runtime, minimum interval, and manual stop.
- API-dependent actuators are acceptable for small personal installations, but
  they should not be the only safety boundary.

## System Profile Example

```json
{
  "system_id": "strawberry-drip-system-01",
  "crop": "strawberry",
  "field_unit": "bed-a",
  "devices": {
    "environment": ["env-field-01"],
    "irrigation_actuator": "switchbot-plug-drip-01",
    "irrigation_feedback": ["soil-bed-a-01"]
  },
  "policy": {
    "automation_level": "manual_approval",
    "max_duration_sec": 120,
    "min_interval_min": 90,
    "require_moisture_response": true,
    "response_settle_sec": 300
  }
}
```

The exact storage schema can evolve, but the model should preserve these
relationships: crop context, target field unit, actuator, feedback sensor, and
policy.

## Failure Handling

For irrigation actions, failure handling should favor stopping water first and
explaining uncertainty second.

- If actuator state cannot be confirmed after `turnOn`, send `turnOff`, mark
  the action uncertain, and alert.
- If `turnOff` fails or the state remains on, retry and escalate immediately.
- If the plug reports current but soil moisture does not rise, suspect water
  path failure rather than only sensor error.
- If soil moisture rises without a command, suspect leak, manual irrigation, or
  another water source and record it as an observation.
- If the soil sensor is missing or stale, the hub may still allow manual
  irrigation, but should not treat it as verified automatic irrigation.

## Relation To Device Kinds

`WTR` remains useful as an all-in-one personal watering device because it owns
both irrigation output and local soil feedback. `WRS` is the RS485-first
successor for installations that should add soil, PAR, and irradiance sensors on
the same bus without changing pin assignments. `SOI` and `ENV` support a more
modular direction where the hub composes dedicated sensor devices and external
actuators into a crop system.

Do not create a new device kind only because the crop is strawberry. Create a
new device kind when the hardware contract, payload schema, or power model
changes materially.

Related documents:

- [SYSTEM_SPECIFICATION.md](SYSTEM_SPECIFICATION.md)
- [hub/doc/AGRI_IMPROVEMENT_LOOP.md](../hub/doc/AGRI_IMPROVEMENT_LOOP.md)
- [client-devices/docs/rs485_sensor_device_spec.md](../client-devices/docs/rs485_sensor_device_spec.md)
