# Introduce rail-independent agentic farm-operation readiness

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The cultivation calendar already explains how to water, transplant, prune, and harvest, while the field page can separately propose watering from soil moisture. After this change, every calendar action exposes one consistent execution-readiness view: what must be checked, what cancels the work, how completion is verified, and whether a physically linked device or a person can perform it.

The design does not assume FarmBot-style rails. A rail, mobile robot, fixed actuator, or person is an executor selected by declared capability and physical reach. Phase 1 connects watering actions to WTR/WRS devices only when the installation layout explicitly targets the crop placement. It intentionally does not energize a pump; acknowledged, idempotent action dispatch is a later safety boundary.

## Progress

- [x] (2026-07-19) Traced calendar work plans, soil-moisture action candidates, field control policy, device definitions, and installation-layout bindings.
- [x] (2026-07-19) Documented the common lifecycle, action-specific safety boundaries, and phased roadmap.
- [x] (2026-07-19) Added a deterministic readiness service and physically linked watering executor discovery.
- [x] (2026-07-19) Exposed readiness in field bundles and rendered it in calendar action details.
- [x] (2026-07-19) Added service/API/browser regression coverage and visually inspected desktop/mobile screenshots.

## Surprises & Discoveries

- Observation: The Hub already has useful deterministic start, skip, method, and completion guidance for watering, repotting, pruning, and harvest.
  Evidence: `plant_work_catalog.py` supplies `work_plan` data for calendar actions.

- Observation: Existing soil-moisture candidates consider any WTR/WRS in the field sufficient, even if the installation layout does not connect that device to the target crop.
  Evidence: `_action_support` in `agri_action_service.py` checks only the device kind.

- Observation: Device definitions advertise actions such as `water_now`, but the Hub has no acknowledged on-demand action dispatcher.
  Evidence: runtime configuration push exists, but no request-id/ack/result action protocol exists in the web or MQTT service.

- Observation: The first mobile capture inherited the illustration's narrow second column for the entire readiness panel.
  Evidence: `/tmp/ina-agentic-watering-readiness-mobile.png` initially left about one third of the viewport empty; making the copy wrapper participate in the mobile grid lets only the heading share the illustration row and restores full-width details.

## Decision Log

- Decision: Treat rails as one optional executor, never as the domain model.
  Rationale: most existing farms can adopt fixed valves, pumps, sensors, cameras, and human work without rebuilding the field around rails.
  Date/Author: 2026-07-19 / Codex

- Decision: A watering device is eligible only when its installation-layout binding targets the planting placement and its device definition declares irrigation action support.
  Rationale: device presence alone does not prove that water reaches the intended plant.
  Date/Author: 2026-07-19 / Codex

- Decision: Phase 1 never dispatches device actions.
  Rationale: a safe dispatcher needs an idempotency key, acknowledgement, timeout, cancellation, result recording, daily limits, and minimum-interval enforcement.
  Date/Author: 2026-07-19 / Codex

- Decision: Planting/repotting, pruning, and harvest remain human-guided until perception, reach, manipulation, and post-work verification are declared and proven.
  Rationale: these are irreversible or quality-sensitive operations; a calendar suggestion is not sufficient evidence for autonomous actuation.
  Date/Author: 2026-07-19 / Codex

## Plan of Work

Add a deterministic operation-readiness builder to the agricultural action service. It merges each calendar action's work-plan conditions with operation-specific safety checks and discovers executor candidates from device definitions and installation-layout target bindings. It returns additive data keyed by action ID, so existing databases and calendar documents require no migration.

Decorate the plant field-bundle response in the Flask boundary using current field, layout, and device records. Add matching TypeScript types and an execution-readiness panel to action details. The panel must state whether a person or connected device is the current executor, show stop and completion checks, and link to device settings in a new tab so calendar edits are preserved.

## Validation and Acceptance

Service tests must prove that an unrelated WTR is not eligible, an explicitly targeted and action-capable WTR is eligible, and pruning/harvest remain human-guided. API tests must prove readiness is additive to the existing bundle. Existing tests must remain green.

Run from `hub`:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_agri_action_service tests.test_web_server_basic_ui
    UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Run from `hub/admin-ui`:

    npm run build

Then start the deterministic demo, open a linked watering action and a human-guided action, capture desktop and mobile screens, and inspect hierarchy, link behavior, clipping, and browser errors.

## Idempotence and Recovery

Readiness is computed at request time and writes nothing. A missing layout binding, device record, or definition degrades to a human-guided explanation. Removing this additive response field restores the previous UI without data migration.

## Outcomes & Retrospective

The field-bundle API now computes `operation_readiness` for every calendar action without changing persisted plant or calendar documents. It merges existing LLM/deterministic work-plan guidance with reviewed operation checks. Repotting, pruning, and harvest explicitly remain human-guided; their UI explains why perception, reach, manipulation, and verification are still required.

Watering readiness discovers only active WTR/WRS devices whose device definition declares an irrigation action and whose installation-layout binding targets the planting placement. The action detail shows the linked device, route placement, start/stop/completion checks, and opens settings in a new tab. A missing route degrades to a human-guided explanation and links to the installation editor.

The older soil-moisture candidate path now follows the same boundary: merely having a WTR/WRS in the field is insufficient, and `can_execute_now` stays false until an acknowledged, idempotent on-demand protocol exists. This avoids presenting runtime-config push as a safe actuator command.

Validation passed 335 Python tests, focused Ruff checks, TypeScript/Vite production build, and the full field-detail browser smoke after restarting the demo with the final backend. Browser assertions covered linked-device selection, new-tab preservation, human-guided irreversible work, desktop/mobile overflow, and absence of console errors. Visual inspection of `/tmp/ina-agentic-watering-readiness.png`, `/tmp/ina-agentic-watering-readiness-mobile.png`, and `/tmp/ina-agentic-human-readiness.png` found and corrected the initial narrow mobile layout; the final panel uses the available width with readable hierarchy and no horizontal overflow.
