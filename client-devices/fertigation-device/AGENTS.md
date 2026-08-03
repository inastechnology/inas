# FGT Firmware Guidelines

- `FGT` is the liquid-fertilizer preparation and irrigation device. Product
  sequencing belongs in the Device App or `fgt-core`, never in a HAL wrapper.
- Keep the batch state machine in `lib/fgt-core`; it must remain free of Arduino
  dependencies and be covered by native PlatformIO tests.
- Hardware drivers describe concrete primitives (direct GPIO outputs and
  contact inputs, pulse flow input, and the RS485 transceiver). Do not create a
  `hal_fgt` facade.
- Every actuator must default OFF. Any I/O, leak, emergency-stop, level, flow,
  or timeout failure must turn all actuator commands OFF.
- A and B concentrate outputs must never be active simultaneously. Dosing is
  permitted only while the mixer is active and the tank is not empty.
- Run `make test`, `make build`, and `make check-firmware` before handoff.
