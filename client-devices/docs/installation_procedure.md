# Installation Procedure

Japanese version:

- [jp/installation_procedure.md](jp/installation_procedure.md)

This procedure covers field installation after a device has passed manufacturing
inspection.

## Pre-Installation Survey

1. Confirm crop, field, section, ridge, bed, and measurement point names.
2. Decide the device placement scope in the hub: field, section, ridge/bed, or
   point.
3. Confirm available power: 12V DC for `WTR`, `WRS`, and `ENV`; charged 18650
   battery for `SOI`.
4. Confirm network conditions for setup AP, Wi-Fi, and MQTT reachability.
5. Record sensor positions and planned Modbus slave IDs.
6. Confirm water source, pump direction, valve direction, and safe drainage.

## Mounting

- Mount enclosures above splash and flood level.
- Keep cable glands facing down or sideways, not upward.
- Use strain relief for pump, valve, sensor, and power cables.
- Keep sensor cables away from pump motor cables when possible.
- Put a service loop near each sensor and actuator.

## Sensor Placement

| Device kind | Placement |
|---|---|
| `SOI` | Root-zone representative point in the ridge or bed |
| `ENV` | Field or section representative environment point |
| `WTR` | Near pump/valve and the irrigation target |
| `WRS` | Near irrigation output wiring with RS485 soil/PAR/irradiance sensors on the same bus |

For strawberry drip cultivation, place soil feedback near the root-zone affected
by the drip line. Do not validate irrigation only from pump runtime.

## Commissioning

1. Power the device and confirm it boots.
2. Enter setup AP mode if Wi-Fi/MQTT configuration is missing.
3. Register or confirm the device ID in the hub.
4. Assign device placement in the field model.
5. Confirm the latest status payload reaches the hub.
6. For RS485 sensors, confirm each expected sensor reports `*_ok=true`.
7. For missing optional sensors, confirm `*_ok=false` is shown without changing
   pin assignments.
8. Run a short manual irrigation test for `WTR` and `WRS`.
9. Confirm soil moisture increases after irrigation or document why it did not.
10. Save installation notes, photos, sensor IDs, and Modbus slave IDs.

## Acceptance Criteria

- Device appears in the hub with the correct `device_kind`.
- Device placement matches the crop and field unit it represents.
- Sensor values are plausible for the site.
- Pump and valve outputs are off unless commanded.
- Irrigation duration and interval limits are configured before unattended use.
- Enclosure is closed, labelled, and weather protected.

## Handover

Give the operator:

- Device ID and device kind.
- Location and placement scope.
- Sensor list and Modbus slave IDs.
- Calibration status.
- Manual stop procedure.
- First inspection date.
