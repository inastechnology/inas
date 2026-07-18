# Implementation Plan

## Architecture

1. `lib/fgt-core` owns recipe validation, deterministic phase transitions,
   actuator commands, timeouts, and fault names. It has no Arduino dependency.
2. Device App owns saved JSON configuration, schedules, batch journal,
   RS485 sampling, state-machine orchestration, MQTT status, and sleep policy.
3. HAL owns MCP23017 register I/O and inlet-flow pulse counting.
4. Common INA client code continues to own Wi-Fi, MQTT, OTA, setup portal,
   LittleFS mount, time synchronization, and deep sleep.

## Delivery sequence

1. Document product boundary, electrical defaults, configuration, status, and
   verification criteria.
2. Write native state-machine tests before hardware orchestration.
3. Implement the state machine until nominal and fault tests pass.
4. Implement MCP23017 and flow-meter primitives with OFF-on-reset behavior.
5. Implement FGT runtime configuration with bounded defaults and CRC storage.
6. Integrate schedules, batch execution, network servicing, RS485 readings, and
   status publication.
7. Add an interrupted-batch journal. Never auto-resume a saved in-progress
   marker.
8. Build firmware, validate its OTA manifest, and run repository regressions.

## Deliberate v1 limits

- One active recipe is shared by all daily schedule entries.
- Inlet volume is measured; irrigation terminates from tank-empty plus timeout.
- Tank EC/pH feedback is not assumed. Soil EC/pH/NPK remains an RS485 field
  sensor and is not used as proof of tank mixture concentration.
- Automatic recovery from an interrupted batch is prohibited.
- Hardware-in-loop calibration of flow and A/B pump rates is required before
  enabling unattended fertilizer dosing.
