# Make device settings task-oriented and capability-aware

This ExecPlan is a living document and follows `hub/AGENTS.md`.

## Purpose / Big Picture

Device settings currently expose protocol and circuit terminology, allow users to type values that the hardware may not support, and mix a readable status view with a dense editor. The result should instead begin with a graphical, read-only view of what each physical output controls. Editing must use only the endpoints supported by the selected device kind; fixed identifiers, terminals, and channel values are derived rather than typed. Watering summaries should lead directly to the relevant setting, and soil-moisture calibration should be explained as a guided procedure before any command is sent.

## Progress

- [x] (2026-07-18) Audited runtime-config persistence, device-kind data, output rendering, schedule selection, and calibration controls.
- [x] (2026-07-18) Added a device capability model and exposed supported physical outputs to the view.
- [x] (2026-07-18) Separated output overview from a constrained graphical editor and removed circuit terminology from operator UI.
- [x] (2026-07-18) Added contextual watering-setting links and a soil-moisture calibration guide modal.
- [x] (2026-07-18) Updated tests and documentation, rebuilt the admin UI, and completed desktop/mobile browser smoke coverage.

## Decisions

- Keep the existing `mosfet_switches`, `switch_id`, `terminal`, and `channel_mask` payload fields for firmware and stored-data compatibility, but never ask an operator to type them.
- Derive output number, protocol ID, terminal, and channel value from device-kind capabilities. WTR exposes two irrigation outputs; WRS exposes two irrigation outputs and its sensor-power output. Other kinds do not expose output editing.
- Populate the controlled-equipment selector from the device's assigned targets and existing saved value. This prevents arbitrary unsupported channel values while preserving existing descriptions.
- Keep low-level JSON and calibration raw values available under advanced disclosures so existing installations remain recoverable.

## Validation

Backend HTML tests will assert that circuit terms and internal identifiers are absent from operator-facing markup, supported output numbers are present, fixed technical values are not editable, watering summary links reach the exact settings section, and the calibration dialog contains ordered dry/wet guidance. Browser smoke will exercise overview-to-settings navigation, output edit mode, constrained selectors, modal open/close, and mobile overflow. The complete Python suite, Ruff, UI build, and relevant smoke flows must pass.

Validation completed on 2026-07-18:

- `PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests`: 266 tests passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff check .`: passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff format --check .`: 112 files already formatted.
- `npm run build`: TypeScript and Vite production build passed.
- `HUB_URL=http://127.0.0.1:39251 npm run smoke:device-detail`: passed for five tabs, WTR and ENV charts, the exact settings deep link, both dialogs, and 0 px mobile overflow.

## Outcomes

The device detail now answers “what is connected?” before exposing editing. WTR and WRS output choices come from a fixed capability table, while the existing wire-format fields remain derived and persisted for firmware compatibility. Existing unsupported output records are carried forward unchanged instead of being discarded. Watering summaries lead to the relevant schedule, and soil-moisture calibration is a four-step guided action rather than an unexplained group of raw values.
