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
- Journal start and completion records survive a restart and reject changed
  state bytes.
- Deployed 0.2.1 journal CRC records load through the read-only compatibility
  path, while new records ignore ABI tail padding.
- A single missed schedule catches up within six hours, OTA deferral remains
  pending, and older schedules are never replayed.
- Moisture guard opt-in, equality and 0/100% boundaries, failed reads, non-finite
  and out-of-range samples, and invalid configuration all follow the contract.
- Actual runtime-config parsing and in-memory LittleFS round trips preserve
  enabled/disabled guards, reject malformed JSON, and migrate version 2 and 3 records
  without changing schedules. Consumed moisture skips remain consumed after restart.

## Moisture guard bench acceptance

Use a supervised water-only setup to verify both timed-output and recipe mode:

- Enable the guard and set the threshold equal to or below the measured moisture;
  confirm all five outputs remain OFF and the status records `soil_moisture_high`.
- Set the threshold above the measurement; confirm the scheduled program starts.
- Select a specific soil sensor and then the average. Check the actual decision
  value, including equality at the threshold and reordered registry entries.
- Disconnect the selected sensor or one member of the average; confirm
  `moisture_guard_result=allow_unavailable` and normal scheduled irrigation,
  without substituting another sensor or calculating a partial mean.
- Restart after a skipped occurrence; confirm it is not replayed, then verify
  the next scheduled occurrence is evaluated normally.

These physical checks require the connected FGT and are separate from native
tests and firmware compilation.

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
- Power-cycle after a completed timed-output run and verify that the next
  schedule still runs exactly once.
- Run water-only batches before any fertilizer test.
