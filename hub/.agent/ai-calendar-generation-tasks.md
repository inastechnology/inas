# Run AI calendar generation as persistent background tasks

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This plan follows the ExecPlan requirements referenced by `hub/AGENTS.md`. The referenced `.agent/PLANS.md` is not checked into this repository, so this document records the applicable requirements and all repository-specific context needed to continue the work.

## Purpose / Big Picture

Creating or regenerating a twelve-month cultivation calendar currently keeps the browser request open while the AI call runs. During that time the installation editor treats all plant operations as busy, and leaving the page loses the only visible indication that work is happening. After this change, the server immediately creates a durable generation task and returns control to the browser. The user can continue editing or navigate elsewhere, then return and see that the plan is queued, running, completed, or failed. A completed task automatically makes the generated targets and calendar visible, while a failed task exposes a retry path.

## Progress

- [x] (2026-07-17 05:50Z) Traced the synchronous create and regenerate routes, the JSON-backed plant repository, the Hub startup path, and both React calendar entry points.
- [x] (2026-07-17 05:55Z) Chose a durable task contract and restart behavior that fits the existing single-Hub JSON persistence model.
- [x] (2026-07-17 06:05Z) Added generation-task persistence, claiming, completion, failure, duplicate prevention, and interrupted-task recovery to the plant repository.
- [x] (2026-07-17 06:07Z) Added a background worker that rebuilds generation context, calls the AI service, and commits results through the repository.
- [x] (2026-07-17 06:09Z) Changed HTTP create and regenerate routes to enqueue work and return HTTP 202 without waiting for AI.
- [x] (2026-07-17 06:11Z) Exposed task state in field plant bundles and rendered/polled it in both React entry points.
- [x] (2026-07-17 06:13Z) Added backend and UI-facing tests; 235 Python tests, Ruff checks, the admin UI build, and the browser smoke test pass.
- [x] (2026-07-17 06:15Z) Updated the plant calendar, installation layout, and screen specifications with the asynchronous task contract and UX.
- [x] (2026-07-17 07:05Z) Separated historical planting dates from the effective planning start, tightened the initial prompt, rejected past LLM actions, and made fallback plans start today or later.
- [x] (2026-07-17 07:08Z) Added regressions for an established lychee planting, past LLM output, and worker context date clamping; all 238 Python tests and Ruff checks pass.
- [x] (2026-07-17 07:25Z) Added a reusable 100-point calendar quality evaluator and three representative CLI evaluation cases; deterministic plans score 100 in every case.
- [x] (2026-07-17 07:29Z) Added an administrator-only advanced prompt-template setting with required placeholders, runtime persistence, safe default fallback, and UI/server tests.
- [x] (2026-07-17 07:33Z) Completed validation with 249 Python tests, Ruff lint/format, the three-case evaluation CLI, and the TypeScript/Vite production build.

## Surprises & Discoveries

- Observation: `hub/src/ina_device_hub/web_server.py` and `hub/tests/test_web_server_basic_ui.py` already have unrelated uncommitted tag-support edits.
  Evidence: `git status --short` reports those files as modified, and their diff only concerns field-record tags. New edits must preserve those lines.

- Observation: the existing create route persists the planting before making the synchronous AI call, so an AI failure can already leave a planting without a calendar even though the request fails.
  Evidence: `create_field_planting_api` calls `repository.create_planting` before `generate_plant_calendar`.

- Observation: production starts background tasks from `hub/src/ina_device_hub/serve.py`, while the UI demo starts Flask directly from `hub/scripts/run_admin_demo_server.py`.
  Evidence: both entry points must start the new generation worker for identical behavior.

- Observation: the existing end-to-end smoke flow needs no artificial delay even though generation is now asynchronous.
  Evidence: the demo worker accepted `POST .../plantings` with HTTP 202, completed the fallback plan, and the smoke test reached eight calendar actions and one completed work log.

- Observation: the reported expired-plan example was produced by the deterministic fallback, not by an LLM prompt.
  Evidence: its generation metadata contains `source: "fallback"` and an empty model, while its planning snapshot uses the historical `planted_on` value as `start_date`. Prompt changes alone therefore cannot fix the production symptom.

- Observation: a repeatable quality script must not initialize the operator's real Hub work directory in its default, no-cost mode.
  Evidence: the first CLI run attempted to open the configured home-directory lock file in the restricted test environment. The script now uses an isolated `/tmp` work directory unless `--live` is explicitly selected.

## Decision Log

- Decision: Store calendar-generation tasks inside `.plant_management.json` rather than a browser store or an in-memory executor queue.
  Rationale: the status must survive page navigation and Hub restarts, and the generated result and task status can be committed under the repository's existing host/file lock.
  Date/Author: 2026-07-17 / Codex

- Decision: Use one latest visible task per planting and reject a second queued/running task for the same planting.
  Rationale: concurrent replacements could finish out of order and overwrite a newer calendar. A single active task gives deterministic UI state and generation results.
  Date/Author: 2026-07-17 / Codex

- Decision: Recover a task left in `running` as `queued` on worker startup.
  Rationale: this project has no external queue with leases. Requeueing is the simplest at-least-once restart policy, and repository completion is idempotent with respect to one claimed task state.
  Date/Author: 2026-07-17 / Codex

- Decision: Poll the existing field plant-bundle endpoint every two seconds only while a task is queued or running.
  Rationale: this avoids adding a second status endpoint or a websocket dependency and naturally restores state whenever either React page is loaded.
  Date/Author: 2026-07-17 / Codex

- Decision: Keep unrelated layout work, navigation, and plant questions available during generation, but disable mutations to the calendar currently being regenerated.
  Rationale: a completed regeneration replaces planned actions, so allowing simultaneous planned-action edits or additions could silently discard the user's work. This narrower lock preserves data while still achieving the non-blocking workflow.
  Date/Author: 2026-07-17 / Codex

- Decision: Treat `planted_on` as historical context and clamp the effective generation start to the later of the requested date and the server's current date.
  Rationale: an established plant still needs planting age for stage decisions, but a newly generated actionable calendar must never introduce already-expired work. The worker applies the clamp so it also protects queued requests created by older clients.
  Date/Author: 2026-07-17 / Codex

- Decision: Validate every LLM action against the effective planning start and apply the same boundary in fallback generation.
  Rationale: prompt instructions improve model behavior but do not enforce an invariant, and the reported case bypassed the model entirely. Server validation plus constrained fallback covers both paths.
  Date/Author: 2026-07-17 / Codex

- Decision: Make the custom format wrap the required built-in instructions and context instead of replacing the system message.
  Rationale: advanced operators can tune ordering and add local priorities while date boundaries, safety constraints, JSON output, and verified-material rules remain enforceable and testable by the server.
  Date/Author: 2026-07-17 / Codex

- Decision: Keep evaluation deterministic by default and require `--live` for model calls.
  Rationale: the quality suite should be safe to run in CI without cost or credentials, while still supporting explicit before/after comparisons of a configured model and custom prompt.
  Date/Author: 2026-07-17 / Codex

## Outcomes & Retrospective

Initial creation and regeneration now return HTTP 202 with a durable task instead of waiting for AI. The task worker is started in both production and demo entry points, serializes generation per planting, resumes interrupted work after Hub restart, and records failures without removing an existing calendar. Field bundles expose the latest state, so both the installation editor and standalone calendar page restore and poll progress after navigation.

The visible UX changes meet the original goal: the calendar button and generation button become `AI計画を作成中...`, the calendar explains that the user may leave the page, unrelated layout work and questions remain available, and success appears automatically. Mutations to the same calendar are temporarily disabled during regeneration to prevent a newly generated plan from overwriting simultaneous planned-action edits. Failure text and the generation form provide retry behavior.

Validation for the asynchronous worker completed with 235 passing Python tests, successful Ruff lint/format checks, a successful TypeScript/Vite production build, and the full Puppeteer smoke flow. After the date-boundary regressions were added, the complete Python suite increased to 238 passing tests and Ruff still passed. The worker intentionally remains a single in-process daemon suited to this project's one-Hub deployment model; a future multi-process deployment would require a leased database queue rather than the current JSON file task claim.

The follow-up date-boundary fix now preserves a past planting date only as history. Worker context exposes the requested date, effective current-or-future start, current date, and elapsed planting age separately. Both the model prompt and deterministic fallback use that distinction; model output containing a past action is rejected before persistence. Historical dated work notes and manual-frequency/automation requests are explicitly described to the model, and the fallback honors the common monthly-manual-work request without creating watering tasks.

Calendar generation now records a structured quality report and has a repeatable evaluation CLI covering the reported established-lychee case, a new blueberry, and an automated hydroponic tomato. The fallback was extended across the full planning horizon and produces exactly one monthly suggestion when requested. Administrators can customize the initial calendar user-prompt format from `/settings`; required placeholders and an immutable system contract keep input facts, built-in requirements, and guidance present. Invalid UI input is rejected, and a manually corrupted persisted template safely falls back to the built-in format.

Final validation after these additions is 249 passing Python tests, successful Ruff lint and format checks across source, tests, and the evaluation script, three 100/100 deterministic evaluation cases, and a successful TypeScript/Vite production build.

## Context and Orientation

The Hub is a Python Flask application under `hub/src/ina_device_hub`. `web_server.py` owns HTTP request and response translation. `plant_management_repository.py` owns JSON persistence for plantings, calendars, work logs, and feedback; writes are serialized by `json_repository_io.py`. `ai_content_service.py` performs the potentially slow external AI request. `serve.py` starts the long-running Hub components.

The React admin UI is under `hub/admin-ui/src`. `api.ts` defines HTTP calls, `types.ts` defines the plant bundle contract, `App.tsx` renders the installation editor and registration flow, and `plant-calendar/PlantCalendarPage.tsx` plus `PlantCalendarDrawer.tsx` render the calendar page/modal and regeneration controls. A plant bundle is the JSON response that contains a field's plantings, loaded calendars, suggestions, and logs. It will also contain the latest generation task for each planting.

A generation task is a durable record representing one initial calendar creation or one regeneration. Its state is `queued` before a worker claims it, `running` during the AI call, `succeeded` after the calendar is committed, or `failed` after an error. The record stores the planning start date, user notes, and advice audience snapshot needed to reproduce the request after navigation or restart.

## Plan of Work

Extend `hub/src/ina_device_hub/plant_management_repository.py` with normalized generation-task records and repository methods to enqueue, claim, recover, complete, and fail work. Completion must update growth targets and either create the first calendar or replace the planned portion of an existing calendar while holding the same serialized write lock. Add the latest task per planting to `field_bundle` so every page load can recover UI status.

Create `hub/src/ina_device_hub/plant_calendar_generation_task.py`. Its worker owns orchestration: it retrieves a queued task, resolves the current field and placement, builds the same generation context formerly assembled in the route, invokes `AIContentService.generate_plant_calendar`, and hands the result to the repository. It catches failures, stores a farmer-readable error, logs the exception, and continues processing later tasks. Startup recovers interrupted work and launches one daemon thread. Wire it into both `serve.py` and the admin demo server.

Make the Flask routes thin. `create_field_planting_api` will still validate and persist planting input, then enqueue an initial task and return HTTP 202 with `planting` and `generation_task`. `regenerate_plant_calendar_api` will validate that the planting and placement still exist, enqueue a regeneration task, and return HTTP 202. The routes must not invoke the AI service.

Extend the TypeScript bundle and task types. Both `App.tsx` and `PlantCalendarPage.tsx` will poll while active tasks exist without setting the broad `busy` flag. Registration will clear its draft after the enqueue succeeds and expose the new active planting immediately. The selected planting card and calendar generation section will show an animated working state, success will reveal the refreshed calendar, and failure will retain the error plus allow resubmission. Controls unrelated to generation remain usable.

Add repository lifecycle tests, worker success/failure/recovery tests, and adapt the existing Flask flow test to assert HTTP 202 before explicitly processing the queued task. Build the React UI to validate types and production bundling. Preserve unrelated field-record tag edits already in the worktree.

## Concrete Steps

All commands run from `/home/polonity/workspace/ina-technologies/inas/hub` unless noted otherwise.

First implement and format the Python files, then run focused tests:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_plant_management_repository tests.test_plant_calendar_generation_task tests.test_web_server_basic_ui

The new tests prove enqueue responses precede AI execution, one worker pass produces a calendar, a failure is persisted, duplicate active tasks are rejected, and interrupted work is recovered. The observed focused result was `Ran 57 tests ... OK`.

Then validate all Python behavior:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Finally validate the UI from `hub/admin-ui`:

    npm run build

For end-to-end browser validation, start `scripts/run_admin_demo_server.py` on port 39303 and run `npm run smoke`. The completed run reported `calendarActions: 8`, `workLogs: 1`, and no browser errors.

## Validation and Acceptance

An initial `POST /local/api/fields/<field-id>/plantings` with valid data must return HTTP 202 promptly with a persisted planting and a `generation_task.status` of `queued`; the AI fake must not have been called before the response. Loading `GET /local/api/fields/<field-id>/plantings` must include that task. After one worker processing pass, the same bundle must show `succeeded` and include the calendar and generated growth targets.

Posting regeneration while another generation task for that planting is queued or running must return HTTP 409. A worker exception must make the task `failed` without deleting the previous calendar. Posting regeneration again after failure must create a new queued task. Calling worker startup recovery with a persisted running task must return it to queued so it can finish after restart.

In the browser, submitting a planting must stop blocking as soon as the task is accepted. The selected planting view and calendar view must say that AI planning is in progress. Navigation away and back must show the same state because it comes from the server bundle. Other layout and calendar operations that are valid without a completed calendar must remain interactive. When polling observes success, the generated twelve-month calendar must appear without a manual reload. When polling observes failure, the error must be visible and the user must be able to retry.

## Idempotence and Recovery

Repository normalization makes older `.plant_management.json` files valid by supplying an empty task list. Starting the worker repeatedly is safe because it checks whether its thread is alive. Recovery changes only tasks stranded in `running`; succeeded and failed history remains unchanged. The worker processes one task at a time, so retries cannot reorder calendar replacement. Tests use temporary repository paths and do not alter production state.

## Artifacts and Notes

The key response shape will be:

    {
      "planting": {"id": "...", "calendar_id": ""},
      "generation_task": {
        "id": "...",
        "planting_id": "...",
        "kind": "initial",
        "status": "queued"
      }
    }

The field bundle will add:

    "generation_tasks": [{"planting_id": "...", "status": "running", ...}]

## Interfaces and Dependencies

`PlantManagementRepository` will expose methods named `enqueue_calendar_generation`, `claim_next_calendar_generation`, `recover_interrupted_calendar_generations`, `complete_calendar_generation`, and `fail_calendar_generation`. These methods use the existing JSON repository lock and add no new package dependency.

`PlantCalendarGenerationTask` will expose `start()`, `wake()`, and a synchronous `process_next()` used by both its worker loop and deterministic tests. The module-level `plant_calendar_generation_task()` returns the production singleton wired to `field_repository()`, `field_layout_repository()`, `plant_management_repository()`, and `ai_content_service()`.

The public TypeScript interface `PlantCalendarGenerationTask` will mirror safe task fields returned by the server. The UI will not depend on worker-internal thread state.

Revision note (2026-07-17): Created the initial self-contained plan after source inspection. It records the persistent single-worker design and the requirement to preserve pre-existing field-record tag edits.

Revision note (2026-07-17): Marked implementation and validation complete, recorded the same-calendar mutation safety decision, added observed test and smoke evidence, and documented the single-process operational boundary.

Revision note (2026-07-17): Recorded the established-plant date-boundary defect, the fallback-path discovery, and the prompt, validation, worker-context, and deterministic fallback corrections.

Revision note (2026-07-17): Added repeatable calendar-quality evaluation, full-horizon fallback suggestions, and the validated advanced prompt-template setting.
