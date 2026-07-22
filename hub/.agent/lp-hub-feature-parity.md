# Align Hub behavior with the public LP promises

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The public INAS landing page describes one connected experience: see the current field, build an evidence-backed annual plan, retain work and consultation history, coordinate workers and managers, and manage low-power scheduled irrigation. After this change, each concrete claim has a source-level implementation status and evidence. Air/soil temperatures participate in crop targets and the field overview, recent approved work and question history are supplied to annual-plan generation, and work records retain the authenticated performer and manager decision.

This change does not add an immediate irrigation button or missing-sensor alert. Those are explicit product non-goals: sensor absence is visible in the field UI, and sleeping irrigation devices receive configuration on their next wake and execute a schedule locally to preserve power.

## Progress

- [x] (2026-07-21) Read Hub, Extension, security, and layering instructions and decomposed the LP into verifiable claims.
- [x] (2026-07-21) Traced field, calendar, evidence, record, camera, irrigation, device configuration, and OTA paths through UI, API, repositories, and tests.
- [x] (2026-07-21) Identified three bounded parity improvements and documented the unsafe immediate-dispatch boundary.
- [x] (2026-07-21) Added air and soil temperature targets across persistence, generation, field status, and the target editor.
- [x] (2026-07-21) Included bounded recent work and question snapshots in annual-plan generation context and exposed their use in the care-profile UI.
- [x] (2026-07-21) Attributed completed work to the authenticated Hub user and rendered the attribution.
- [x] (2026-07-21) Added regression coverage, built the admin UI, and visually inspected desktop/mobile results.
- [x] (2026-07-21) Updated the parity audit and this plan with final validation evidence.
- [x] (2026-07-21) Reclassified missing-sensor alerts and immediate irrigation as product non-goals based on operator requirements.
- [x] (2026-07-21) Added the worker-submission and manager-verification foundation described in `field-work-verification.md`.
- [x] (2026-07-21) Updated the public LP to describe next-wake irrigation and the assignment/submission/review flow accurately.

## Surprises & Discoveries

- Observation: Device definitions and device-status pages already carry `air_temperature_c` and `soil_temperature_c`, but crop target normalization and the field dashboard omitted them; the field-specific raw-status extractor also omitted air temperature.
  Evidence: the device definitions expose both values, while `field_status_dashboard.py`, `plant_management_repository.py`, the React target specification, and `_field_latest_sensor_value()` did not complete the field-overview path.

- Observation: Generated-calendar context already includes planting conditions, fertilizer history, reviewed knowledge sources, and prior action state, but not the existing work log or plant Q&A history advertised by the LP.
  Evidence: `PlantCalendarGenerationTask._generation_context()` builds fertilizer and existing-calendar snapshots without querying `recent_work_logs()` or `list_questions()`.

- Observation: Skip decisions retain `decided_by`, while normal completions do not retain a performer even though the completion HTTP route knows the authenticated user.
  Evidence: `complete_action()` persists no actor and the completion route discards `current_user_from_request(request)`.

- Observation: The existing operation-readiness feature deliberately discovers physically linked watering executors without energizing them.
  Evidence: `agentic-farm-operations-phase-1.md` requires request identity, acknowledgement, timeout, cancellation, result recording, daily limits, and minimum intervals before dispatch.

- Observation: The default temporary directory in this WSL session resides on a Windows-mounted filesystem and cannot enforce Unix `0600` permissions.
  Evidence: the first complete test run had six permission-only failures reporting `0777`; rerunning the same 382 tests with `TMPDIR=/tmp` passed.

## Decision Log

- Decision: Treat the LP as a testable product contract, not as proof that a feature exists.
  Rationale: each claim needs a UI/API/data-path implementation and should be marked complete, partial, or future in one audit.
  Date/Author: 2026-07-21 / Codex

- Decision: Add temperature support as optional target ranges with null defaults in generated fallback data.
  Rationale: useful temperature ranges are crop- and stage-specific; inventing a universal backend target would turn missing knowledge into unsafe advice.
  Date/Author: 2026-07-21 / Codex

- Decision: Send only bounded textual snapshots of recent records to plan generation, excluding attachment URLs and image interpretation.
  Rationale: this gives the planner relevant history while constraining prompt size and treating user-entered text as untrusted data rather than instructions.
  Date/Author: 2026-07-21 / Codex

- Decision: Attribute new completions from the server-side authenticated identity and keep old records backward compatible with an empty actor.
  Rationale: a client-supplied actor can be spoofed; existing JSON data must continue loading without migration.
  Date/Author: 2026-07-21 / Codex

- Decision: Keep immediate irrigation dispatch out of this parity patch.
  Rationale: presenting runtime configuration as an on-demand actuator command would overstate safety and violate the already documented action boundary.
  Date/Author: 2026-07-21 / Codex

- Decision: Supersede immediate irrigation as a future parity target; scheduled next-wake delivery is the canonical product behavior.
  Rationale: field devices prioritize battery life, and users can schedule watering for execution after the next wake instead of keeping the device online for an immediate command.
  Date/Author: 2026-07-21 / Codex

- Decision: Do not add a missing-sensor alert solely to satisfy the phrase “current field.”
  Rationale: optional sensors and their absence are already visible, and treating every uninstalled metric as a fault would conflict with incremental hardware adoption.
  Date/Author: 2026-07-21 / Codex

- Decision: Prioritize worker assignment, evidence submission, and manager verification over new device-control features.
  Rationale: workers perform field tasks while administrators verify completion; that verified boundary is also the prerequisite for any future compensation ledger.
  Date/Author: 2026-07-21 / Codex

## Plan of Work

Extend the shared metric set in the plant and field repositories, AI normalizer/fallback, field dashboard, and React target editor. Do not synthesize a range when none is known.

Add compact snapshot helpers to the background calendar task. Supply a capped number of recent work logs and questions, trim free text, count rather than transmit attachments, and explicitly tell the model that these records are historical data and never instructions. Show the input counts in the generated care profile so a user can see which history was considered.

Pass the authenticated email from the completion HTTP route into the repository, persist it on both the work log and action completion snapshot, normalize legacy records, update TypeScript contracts, and render it with the completed action.

Record the complete LP-to-Hub matrix in `doc/jp/LP_FEATURE_PARITY_AUDIT.md`, including explicit non-goals and collaboration gaps. The separate `field-work-verification.md` plan extends the original performer attribution into assignment, pending review, approval, and rejection without adding payments.

## Validation and Acceptance

Run focused Python tests for the dashboard, plant repository, generation task, AI content, field repository, and completion API. Then run the full Hub suite and Ruff checks.

Run from `hub`:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_field_view_models tests.test_field_repository tests.test_plant_management_repository tests.test_plant_calendar_generation_task tests.test_ai_content_service tests.test_web_server_basic_ui
    UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Run from `hub/admin-ui`:

    npm run build

Start the deterministic admin demo and run the field-detail browser smoke. Inspect desktop and mobile captures for the temperature controls, generation-input summary, performer attribution, clipping, and browser errors.

## Idempotence and Recovery

All persisted additions are optional strings or optional metric ranges. Existing plantings, calendars, and work logs normalize without migration. Re-running generation refreshes the bounded context snapshot; it does not mutate historical records. Removing the new display fields restores the prior UI without deleting data. Immediate device state remains unchanged throughout.

## Outcomes & Retrospective

The Hub now carries `air_temperature_c` and `soil_temperature_c` through raw device-status extraction, crop target validation, AI output normalization, field status cards, deep links, and the visual target editor. Unknown crop-specific temperature ranges remain null rather than being invented by the fallback planner.

Every background annual-plan generation now receives up to 12 recent work records and eight recent plant consultations. Free text is trimmed, image URLs are excluded, only attachment counts are retained, and the prompt explicitly treats history as untrusted data. The care-profile dialog makes the generation inputs visible as counts for planting/field conditions, fertilizer history, work records, consultations, Web evidence, and user correction examples.

New work completions persist the server-authenticated email in both the work log and action snapshot. Legacy records normalize to an empty actor and continue loading. The completed-action detail displays the recorder without accepting a spoofable client field.

After the work-verification extension, validation passed all 387 Hub Python tests with `TMPDIR=/tmp`, Ruff checks and formatting, the TypeScript/Vite production build, and the complete field-detail browser smoke. Browser assertions now also cover the fourth `確認待ち` column, assignment scope, manager-only approval controls, the worker waiting state, and desktop/mobile overflow.

Immediate irrigation dispatch and missing-sensor alerts remain intentionally absent because they are not part of the selected product behavior. Low-power WTR/WRS devices receive runtime configuration at the next wake and evaluate watering schedules locally. The Hub now supports optional assignment and a worker-submission/manager-verification workflow; field-scoped membership and any compensation or payout ledger remain separate future work.
