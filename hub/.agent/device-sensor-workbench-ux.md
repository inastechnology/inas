# Turn sensor settings into a visual workbench

This ExecPlan is a living document and follows `hub/AGENTS.md`.

## Purpose / Big Picture

Sensor setup should resemble connecting and tuning real equipment, not editing a protocol form. Light and soil sensors must appear as separate pieces of equipment. Enabling one reveals only its own controls. Calibration should use a clear target, a visual range control, a live value readout, and explicit actions. Every current-value card on a device detail page should lead directly to its corresponding time-series chart, while decision values lead to the exact setting that changes them.

## Progress

- [x] (2026-07-18) Audited device-kind metrics, chart anchors, sensor configuration persistence, and current calibration controls.
- [x] (2026-07-18) Made operational value cards action-oriented across WTR, WRS, ENV, SOI, PAR, and detected device kinds.
- [x] (2026-07-18) Split light and soil equipment into separate visual cards with inactive settings hidden.
- [x] (2026-07-18) Replaced the generic calibration form with a guided sensor tuning workbench and adaptive slider.
- [x] (2026-07-18) Updated tests, docs, production build, and desktop/mobile browser coverage.
- [x] (2026-07-18) Removed fixed sensor bus identifiers and reading positions from every user-facing layer while preserving stored values internally.
- [x] (2026-07-18) Moved each display adjustment into a focused modal and made the OFF state hide the complete sensor body reliably.
- [x] (2026-07-18) Established and tested the simple-first / advanced-second interaction rule for device settings.
- [x] (2026-07-18) Showed the recorded reference directly on each sensor adjustment button, immediately and after saved-config rendering.
- [x] (2026-07-18) Captured and visually inspected desktop and mobile screenshots of the recorded-value state.

## Decisions

- Preserve `env_sensors` and `env_calibration` exactly; the change is presentation and interaction only.
- Keep Modbus addresses, functions, registers, scale, and offset under per-sensor advanced disclosures for recovery, but do not place them in the primary workflow.
- Use one calibration command workbench because the firmware accepts one target per request. Equipment cards select which target enters that workbench.
- Give each metric a stable monitoring anchor so a current-value card can open the correct chart directly.
- Treat sensor address, read function, and register position as device capabilities, not user choices. Preserve them in hidden form state only so old database records round-trip without loss.
- Keep optional scale and offset overrides behind one clearly named `上級者設定` disclosure; do not mix them into connection or daily setup.
- Use a modal for a single calibration target so the equipment card remains a readable current-state view.
- Use the existing top-level calibration target/reference as the persisted last-recorded value; do not add a database or firmware schema solely for presentation. Other metrics may show `調整済み` when their existing calibrated flag is true.

## Validation

Backend tests will verify history links for soil moisture and all sensor metrics. Browser smoke will verify that disabled sensor panels are hidden, enabling a sensor reveals only its controls, selecting a metric changes the workbench range and unit, and the current soil-moisture card opens the soil-moisture graph. Existing config values must round-trip unchanged. Full Python tests, Ruff, UI build, browser smoke, and `git diff --check` must pass.

Completed on 2026-07-18: 275 Python tests passed; Ruff check and format check passed; the production admin UI build passed; browser smoke passed with five device tabs, two watering charts, three environment charts, exact soil-moisture deep linking, configuration-schema assertions, and zero mobile horizontal overflow.

Follow-up completed on 2026-07-18: browser-computed style verifies that an OFF soil sensor body is `display: none`; fixed connection identifiers are hidden state rather than controls; calibration opens and closes as a modal; the same 275-test suite, Ruff, format check, production build, and device-detail browser smoke all pass.

Recorded-value follow-up completed on 2026-07-18: adjustment buttons show `未調整`, `調整済み`, or a unit-bearing value such as `基準 6.5 pH`. Browser smoke verifies immediate and saved-config rendering. Desktop and 390 px mobile screenshots were inspected; the value remains legible without clipping, card overlap, or horizontal overflow. The 275-test suite, Ruff, format check, production build, and browser smoke pass.
