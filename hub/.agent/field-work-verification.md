# Add worker submission and manager verification to field tasks

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The cultivation calendar already acts as a field-wide task board, but recording work currently makes it final immediately. After this change, an authenticated worker can submit evidence that a task was performed, the task moves to a visible manager-review queue, and an authenticated administrator can approve it or return it for correction. Only approved work becomes official field history or influences generated follow-up work.

Tasks may optionally be assigned to an authenticated email identity. Operators can act on unassigned tasks or tasks assigned to themselves; administrators can assign, review, and act across the field. Existing completed records remain valid as legacy-approved work.

This phase deliberately does not transfer money. It establishes the actor, evidence, assignment, review decision, and timestamps that a future compensation ledger can reference without coupling task state directly to a payment provider.

## Progress

- [x] (2026-07-21) Confirmed that the current calendar already provides a cross-crop field task board and records the authenticated performer.
- [x] (2026-07-21) Confirmed that current completion is terminal and that the Hub has only global `admin` and `operator` roles, with no assignment or manager review state.
- [x] (2026-07-21) Added backward-compatible assignment, pending review, approval, and rejection persistence.
- [x] (2026-07-21) Added thin APIs and authorization checks using the authenticated identity and role.
- [x] (2026-07-21) Added a fourth Kanban column, assignment filtering, manager review controls, and worker-facing review state.
- [x] (2026-07-21) Added repository, API, build, and browser regression coverage.
- [x] (2026-07-21) Updated the public LP, parity audit, product decisions, and future compensation design with final evidence.

## Surprises & Discoveries

- Observation: The existing completion route already knows the authenticated email and stores it as `performed_by`, so the worker identity does not need to be accepted from a client field.
  Evidence: `complete_plant_calendar_action_api()` passes `current_user_from_request(request).email` to the repository.

- Observation: Completion currently creates official field history and AI-generated follow-up tasks before any manager review is possible.
  Evidence: the completion HTTP route calls `field_repository().add_event()` and `generate_follow_up_tasks()` immediately after `complete_action()`.

- Observation: Sleeping watering devices already receive retained or request/reply runtime configuration at wake and evaluate schedules locally.
  Evidence: the device config service publishes retained configuration and replies to `config/request`; WTR/WRS firmware evaluates due schedules after time synchronization.

- Observation: Four fixed desktop columns at a 280-pixel minimum made the new review state fall outside the useful workspace at common laptop widths.
  Evidence: the first browser capture clipped the fourth column; reducing the column minimum to 230 pixels preserved all four states while the compact breakpoint still stacks them on narrow screens.

- Observation: `generate_follow_up_tasks()` already catches AI transport and validation failures and returns deterministic rule-based actions.
  Evidence: the content service wraps the AI path and returns `source: fallback`, so an approved work record does not depend on AI availability.

- Observation: The general field calendar and recent-activity builders consumed every raw work log, including new pending or rejected submissions.
  Evidence: both iterated `field_bundle.work_logs` without checking `review_status`; they now include legacy or explicit `approved` records only, while task detail retains review evidence.

## Decision Log

- Decision: Treat “record work” as a submission, not final completion.
  Rationale: the worker and manager have distinct business responsibilities, and future compensation must be based on a manager-confirmed record.
  Date/Author: 2026-07-21 / Codex

- Decision: Add `awaiting_review` between `in_progress` and `completed`; a rejection returns the task to `in_progress` while retaining the rejected work log.
  Rationale: the task remains actionable after correction, while each submitted evidence set and decision remains auditable.
  Date/Author: 2026-07-21 / Codex

- Decision: Add optional email assignment and enforce it on mutable task actions server-side.
  Rationale: hiding tasks in the UI is not authorization. Unassigned tasks remain available for backward compatibility and flexible field work.
  Date/Author: 2026-07-21 / Codex

- Decision: Only approved work creates official field events, enters AI planning history, or triggers follow-up generation.
  Rationale: pending or rejected work must not affect agronomic decisions or future compensation.
  Date/Author: 2026-07-21 / Codex

- Decision: Preserve legacy completed work as approved during normalization.
  Rationale: existing installations must not require a migration or lose historical meaning.
  Date/Author: 2026-07-21 / Codex

- Decision: Do not add immediate irrigation dispatch or missing-sensor alerts to the roadmap in this phase.
  Rationale: the product prioritizes low-power scheduled irrigation and considers missing sensors visually apparent; manager-verifiable field operations provide more value.
  Date/Author: 2026-07-21 / Codex

## Plan of Work

Extend action and work-log normalization with optional `assigned_to` and review metadata. Submission creates a pending work log and moves the action to `awaiting_review`. Repository review updates the referenced work log, approves to `completed`, or rejects back to `in_progress`. Filter AI-facing recent work logs to approved records while continuing to expose pending records in the task bundle.

Add a small domain service for completion submission and manager review. It validates dates and evidence, enforces assignment against the authenticated actor, uploads images, and creates official events and follow-up actions only on approval. Flask routes remain responsible for HTTP parsing, status codes, and the administrator-role gate.

Expose the current viewer in the field bundle. Update the React contracts and task board with an assignment scope, a dedicated `確認待ち` column, explicit submission wording, pending/rejected/approved review records, and administrator approve/return controls. Assignment editing is visible only to administrators; the server remains authoritative.

## Validation and Acceptance

Repository tests must prove pending submission, approval, rejection/resubmission, legacy normalization, approved-only planning history, and assignment rules. API tests must prove that operators cannot review or act on another assignee’s task, administrators can review, pending work creates no official event or follow-up, and approval creates each exactly once.

Run from `hub` with a Linux-native temporary directory:

    TMPDIR=/tmp UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_plant_management_repository tests.test_plant_action_review_service tests.test_web_server_basic_ui
    TMPDIR=/tmp UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Run from `hub/admin-ui`:

    npm run build

Run the deterministic field-detail browser smoke and inspect desktop and mobile screenshots for the fourth column, assignment filter, pending review record, administrator controls, clipping, and browser errors.

## Idempotence and Recovery

All added fields are optional and normalized at read time. Legacy completed records become approved in memory and on the next save. A review is accepted only while the action is awaiting review, preventing duplicate official events and follow-up tasks. Rejected evidence remains in the append-only work-log list, and resubmission creates a new log rather than overwriting the rejected evidence.

## Outcomes & Retrospective

The task lifecycle is now `planned → in_progress → awaiting_review → completed`, with manager rejection returning the action to `in_progress`. Administrators can optionally assign an authenticated email; operators can act only on unassigned work or work assigned to themselves. The server derives performer and reviewer identities from authentication rather than accepting them from the client.

Submission stores the work details, rating, notes, attachments, performer, and submitted time without creating official field history. Administrator approval records the reviewer and time, creates the field event, and then generates rule-based or AI follow-up work. Rejection requires a note, preserves the rejected evidence, and allows a new submission. AI planning, the general field record calendar, recent crop activity, and field record counts use approved work logs only, while legacy completed logs normalize as approved.

The React work board now has `未完了`, `作業中`, `確認待ち`, and `完了・見送り` columns, assignment scope filtering, assignment controls for administrators, explicit submission wording for workers, and manager-only approve/return controls. The public LP describes the implemented flow without promising automatic wage transfer.

Validation passed 34 repository/service tests, 51 web-server tests, all 387 Hub Python tests with `TMPDIR=/tmp`, Ruff checks and formatting, the TypeScript/Vite production build, and the complete field-detail browser smoke. Browser assertions and visual inspection covered the four-column desktop board, stacked mobile review controls, performer attribution, manager approval controls, the operator-only waiting state, and absence of horizontal clipping.
