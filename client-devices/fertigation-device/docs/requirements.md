# FGT Requirements

## Product boundary

FGT prepares one diluted A/B fertilizer batch and irrigates a colocated crop.
It is a separate `device_kind` because its safety state, runtime configuration,
and status payload materially differ from WRS. It is not a crop-specific device;
strawberry is the first installation profile.

There is currently no fabricated dedicated FGT PCB. The current firmware
profile uses the
[direct-wired XIAO ESP32-C6 pin contract](jp/minimal_wiring.md). The KiCad PCB
is an in-progress future design and is not part of the current hardware.

Version 1 assumptions:

- Approximately 5 L total delivery for ten strawberry plants, including the
  clean-water rinse volume.
- One or two scheduled batches per day.
- Water inlet is either a normally-closed valve or a transfer pump.
- A and B stock solutions use independent 12 V peristaltic pumps.
- Mixing and irrigation use independent 12 V brushless pumps.
- Soil and PAR/irradiance sensors share one protected 12 V RS485 Modbus bus.
- Five actuator commands and the RS485 sensor-power enable connect directly to
  dedicated XIAO ESP32-C6 GPIOs.
- Flow, tank-level, leak, and emergency-stop inputs remain product requirements
  for future protected hardware; they are not present in the current minimal
  pin contract.
- Clean water rinses the tank and the irrigation path after a fertilizer batch.

## Nominal batch

1. Verify that actuator I/O is healthy, no leak/emergency input is active, and
   the tank is empty.
2. Add the configured initial water volume, initially 1.25 L (about one quarter
   of the 5 L delivery plan).
3. Start circulation and establish mixing flow.
4. Add A concentrate while mixing.
5. Mix for the configured A settling time.
6. Add B concentrate while mixing. A and B are never active together.
7. Mix for the configured B settling time.
8. Add the remaining water while continuing to mix.
9. Perform final mixing.
10. Irrigate until the tank-empty input activates, bounded by a timeout.
11. Add rinse water, mix, and discharge it through the irrigation path.
12. Stop every output and record completion before sleeping.

The irrigation plan must count both nutrient-batch water and rinse water. With
the v1 defaults, 4.5 L prepares the batch and 0.5 L rinses the tank and line;
the plant receives approximately 5.0 L plus the small calibrated A/B stock
volume.

## Required safety invariants

These are product acceptance requirements, not a claim that the current
minimal direct-wired prototype already implements every physical safety input.

- All actuator commands are OFF during boot, OTA, sleep, configuration failure,
  I/O failure, leak, emergency stop, and fault handling.
- A and B concentrate pumps can never be active simultaneously.
- A or B dosing requires the mixer to be active and the tank not to be empty.
- Water inlet and irrigation are never active simultaneously.
- Water flow must progress while the inlet is commanded; otherwise stop within
  the configured no-flow timeout.
- A full-tank input before the expected volume is an error, not permission to
  continue dosing.
- Irrigation and rinse drain stop immediately at the empty-tank input.
- Each phase and the complete batch have an upper time limit.
- Firmware must not automatically resume an interrupted batch after reset or
  power loss. A recovery-required status is reported and all outputs stay OFF.
- Recipe values are device-side bounded even when supplied by the Hub.

## Version 1 acceptance criteria

- The pure state machine completes the nominal and rinse paths under native
  PlatformIO tests.
- Tests prove every safety invariant and relevant timeout.
- Firmware builds for the XIAO ESP32-C6 direct-GPIO hardware profile and
  contains an `FGT` OTA manifest.
- Status includes phase, fault, commanded outputs, target/observed water volume,
  schedule, batch identifier, and RS485 sensor health/readings.
- Saved configuration is CRC-protected and invalid content falls back safely.
