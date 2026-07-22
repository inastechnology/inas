# Drip Irrigation Calibration and Substrate Reset

Japanese detailed specification:
[jp/HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md](jp/HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md)

## Status

This document describes a future Hub feature. It does not change the current
WTR, WRS, or FGT runtime behavior.

## Goal

The Hub should guide a grower through three separate workflows:

1. Calibrate a drip line by collecting water from one emitter at a time.
2. Convert crop, growth-stage, weather, substrate, and measured flow inputs into
   an explainable irrigation proposal.
3. Remove accumulated fertilizer salts from a substrate with controlled
   clean-water pulses, using drain EC as the primary completion observation.

These workflows must not be collapsed into one fixed irrigation duration.

## Key decisions

- Total line discharge alone is insufficient for calibration. Each sample is
  collected from one emitter, with representative samples near the inlet,
  middle, and end of the line.
- Crop reference values are starting points, not universal prescriptions. The
  Hub converts a target volume into seconds only after a local flow
  calibration.
- Soil-moisture feedback cannot determine salt accumulation. A substrate reset
  requires drain/substrate EC observations and confirmed drainage.
- A substrate reset means controlled leaching. It is not line rinsing,
  sterilization, or unconditional removal of all nutrients.
- Initial releases remain `suggest_only` or `manual_approval`. Missing EC,
  drainage, stale calibration, or actuator feedback prevents verified
  automatic execution.
- Hub domain records bind to a declared irrigation capability and placement,
  never directly to a GPIO pin. Device Definitions and firmware retain
  ownership of physical terminals and safety limits.

## Planned records

The detailed design defines three auditable record groups:

- line calibration: individual-emitter samples, representative flow,
  distribution variation, and confidence;
- irrigation proposal/execution: target amount, derived duration, reasons,
  approval, observed moisture/drainage response, and outcome;
- substrate-reset plan/execution: source/feed/drain EC, pulse limits, manual
  approvals, drain observations, stop reason, and post-work assessment.

Reference agronomic values must retain crop, cultivar, growth stage,
cultivation system, source, and revision metadata. An LLM may explain a
validated proposal, but must not invent target volumes, EC limits, or reset
completion criteria.

## Delivery order

1. Guided manual emitter calibration and saved calculations.
2. Explainable irrigation proposals without automatic runtime-config changes.
3. Manual-approval substrate-reset work with hand-entered EC observations.
4. Sensor-assisted EC and drainage verification.
5. Site-specific learning and narrowly bounded automation after sufficient
   verified history exists.

## Related documents

- [INAS future feature registry](../../docs/FUTURE_FEATURES.md)
- [Fertilization recommendation policy](jp/HUB_FERTILIZATION_RECOMMENDATION_POLICY.md)
- [Agentic farm operations policy](jp/HUB_AGENTIC_FARM_OPERATIONS_POLICY.md)
- [Cultivation system orchestration](../../docs/CULTIVATION_SYSTEM_ORCHESTRATION.md)
- [Device Definition specification](../../docs/DEVICE_DEFINITION_SPECIFICATION.md)
