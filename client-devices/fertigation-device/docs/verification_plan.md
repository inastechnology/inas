# Verification Plan

The dedicated KiCad controller PCB is still an unbuilt future design and is not
used by the current FGT prototype. The current direct-wired pin contract has no
flow, tank-level, leak, or emergency-stop input. Until protected hardware adds
and verifies those inputs, testing is limited to supervised, water-only bench
operation with an external hard disconnect for the 12 V actuator rail.

## Native regression tests

- Valid and invalid recipe bounds.
- Nominal initial fill, pre-mix, A dose, A mix, B dose, B mix, final fill,
  final mix, irrigation, rinse fill, rinse mix, rinse drain, and completion.
- A/B mutual exclusion at every phase.
- Dosing always implies mixer ON and non-empty tank.
- No-flow, early-full, empty-during-mixing, irrigation timeout, I/O failure,
  leak, emergency stop, and whole-batch timeout.
- Reset from fault only when the tank and safety inputs permit it.
- Phase and fault string stability for MQTT/UI consumers.

## Build regression

```bash
make test
make build
make check-firmware
```

The repository Hub Python test suite is also run because adding `FGT` affects
device-kind handling, OTA metadata, health monitoring, and UI labels.

## Hardware acceptance before unattended use

The following section is a future product release gate. It cannot pass on the
current minimal direct-wired prototype.

- Measure whole-device deep-sleep current at the battery input.
- Measure actual inlet pulses/liter at low and high battery states.
- Weigh at least ten A and ten B doses and store separate calibrated rates.
- Verify pump/valve start current and BMS/DC-DC headroom.
- Interrupt or invalidate each direct contact input during every relevant
  active phase and verify immediate master OFF.
- Reset the ESP32-C6 during every active phase and verify that the hardware
  pull-downs and master-enable chain keep all five actuator gates OFF.
- Simulate every float, leak, and emergency input.
- Power-cycle during every phase and verify no automatic continuation.
- Run water-only batches before any fertilizer test.
