# Turn device setup into a visual builder

This ExecPlan is a living document and follows `hub/AGENTS.md`.

## Purpose / Big Picture

Watering setup should feel like assembling a small system rather than editing a protocol form. The operator should activate a supported connection port, see a wire appear, choose the connected equipment from illustrated cards, and immediately understand the resulting route. The full settings tab should follow the task order: connect equipment, decide watering behavior, set schedules, calibrate sensors, then apply the setup.

## Progress

- [x] (2026-07-18) Audited the current output capability model, settings markup, editor behavior, and browser smoke coverage.
- [x] (2026-07-18) Added an equipment-kind presentation model while preserving current config payloads and saved notes.
- [x] (2026-07-18) Replaced the output dialog with a port-and-wire builder and illustrated selection cards.
- [x] (2026-07-18) Reordered the complete settings tab into a three-step setup journey with friendly labels and progressive disclosure.
- [x] (2026-07-18) Updated tests, docs, production build, and desktop/mobile browser smoke coverage.

## Decisions

- Continue deriving technical IDs, terminals, and bit values from device capabilities. The builder changes presentation only.
- Persist the selected visual equipment kind as a small token in the existing output notes field; preserve any unrelated legacy note text.
- If a legacy note already consumes the field limit, keep it intact and derive the picture from the equipment name instead of appending the visual token.
- Use repo-native inline SVG/CSS icons for pumps, valves, drip lines, sprinklers, and generic equipment. This matches the existing icon-based UI, avoids a new bitmap dependency for simple symbols, and keeps every state crisp and accessible.
- A disabled port is visibly disconnected and its equipment cards are inactive. Enabling it draws the route immediately; selecting a type changes the endpoint icon immediately.
- Keep developer/communication and raw sensor values under collapsed advanced sections.

## Validation

Backend tests will verify that equipment kinds are derived from saved data without exposing technical fields. Browser smoke will activate a port, verify the wire state, select an illustrated type and destination card, cancel without dirtying the form, then apply and verify the overview. It will also check setup-step navigation and mobile overflow. Full Python tests, Ruff, production UI build, and `git diff --check` must pass.

Completed validation on 2026-07-18:

- `PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests`: 274 tests passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff check .`: passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff format --check .`: 114 files already formatted.
- `npm run build`: production bundle built successfully.
- `npm run smoke:device-detail`: passed, including wire activation, illustrated type/destination selection, cancel/apply state, legacy-note preservation, and zero mobile overflow.
- `git diff --check`: passed.
