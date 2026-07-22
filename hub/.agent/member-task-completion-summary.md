# Show low-cost member task completion summaries

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The Hub already stores the authenticated worker on each submission and allows an administrator to approve it. After this change, an administrator can see, in the field-wide work board, how many approved tasks each identified member completed and how many submissions still await review. Workers see only their own progress. Approved counts unlock lightweight achievement titles and show progress toward the next milestone, while selecting a member narrows the current task board to work assigned to or performed by that identity.

This is deliberately a read-only aggregation over existing task and work-log data. It adds no member directory, time clock, wage calculation, escrow balance, or payment state. Its purpose is to make the evidence needed before an escrow phase inexpensive to inspect.

## Progress

- [x] (2026-07-22) Confirmed that approved work logs already retain `performed_by`, `performed_on`, `review_status`, `reviewed_by`, and `reviewed_at`.
- [x] (2026-07-22) Confirmed that the field bundle already exposes normalized work logs, so no repository or API schema change is required.
- [x] (2026-07-22) Added an administrator team summary and an operator personal-achievement summary derived from work logs.
- [x] (2026-07-22) Added dynamic member filtering to the existing assignment scope, including automatic reset when a crop scope no longer contains that member.
- [x] (2026-07-22) Seeded deterministic approved and pending demo records for two members.
- [x] (2026-07-22) Added desktop/mobile and administrator/operator browser regression coverage and visually inspected all three achievement views.
- [x] (2026-07-22) Updated the LP, parity audit, and work-verification/compensation design with the final boundary and validation evidence.

## Surprises & Discoveries

- Observation: The existing assignment filter offers only the current user, unassigned, or all work; an administrator cannot select another identified member directly.
  Evidence: `AssignmentScope` contains `recommended`, `all`, `mine`, and `unassigned` only.

- Observation: `PlantBundle.work_logs` is a better source for historical completion counts than current calendar actions.
  Evidence: work logs are append-only up to the repository limit and retain rejected/resubmitted evidence, while calendar actions represent the current plan.

- Observation: a member selected at field scope may have no task or work log after switching to a single crop.
  Evidence: dynamic member options are recalculated from the selected crop scope; preserving an unavailable member value would otherwise leave a hidden, empty filter active.

## Decision Log

- Decision: Count only work logs whose `review_status` is `approved` as completed.
  Rationale: “完遂” must mean manager-confirmed work, not a submission or assignment.
  Date/Author: 2026-07-22 / Codex

- Decision: Show pending submissions as a separate count and never combine them with completed totals.
  Rationale: managers need to see the review queue without overstating completed work.
  Date/Author: 2026-07-22 / Codex

- Decision: Build the summary client-side from the existing field bundle, with team visibility for administrators and self-only visibility for operators.
  Rationale: this is the lowest-cost implementation and adds no persistence or API. Administrators see the team; operators see only their own identity.
  Date/Author: 2026-07-22 / Codex

- Decision: Attribute completion to `performed_by`, not `assigned_to`.
  Rationale: the authenticated performer is the evidence of who did the task; assignment describes intent and may differ from actual execution.
  Date/Author: 2026-07-22 / Codex

- Decision: Use private milestone titles and next-goal progress, without a leaderboard, completion-speed score, or streak penalty.
  Rationale: the UI should create a sense of progress without encouraging unsafe speed, public comparison, or attendance pressure in paid field work.
  Date/Author: 2026-07-22 / Codex

## Plan of Work

Derive a sorted member list from authenticated performer identities in field work logs plus current task assignments. For the selected crop scope, calculate approved and pending counts and the most recent approved work date. Map approved counts to deterministic milestone titles and next-milestone progress. Render compact member buttons before the Kanban filters: administrators see the team, operators see their own card only. State explicitly that the values come from existing records and do not calculate money.

Extend the assignment scope with `member:<email>` values. A selected member includes current actions assigned to that email or whose latest completion was performed by that email. Keep the existing operator default of self plus unassigned work. Toggle the member button back to the recommended scope when selected again.

Create deterministic demo evidence with one approved record and one pending record across two identities. Extend the browser smoke to prove the approved and pending counts, member filtering, manager-only visibility, compact mobile layout, and no overflow.

## Validation and Acceptance

Run from `hub`:

    TMPDIR=/tmp UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Run from `hub/admin-ui`:

    npm run build
    HUB_URL=http://127.0.0.1:<demo-port> npm run smoke:field-detail

The administrator page must show each identified member with separate approved and pending counts, a milestone title, and progress toward the next title. The worker page must show only that worker's personal achievement card and must not reveal other member summaries. Selecting a member must narrow the current board and remain usable at 390 pixels without horizontal overflow.

## Idempotence and Recovery

The summary writes nothing and recalculates whenever the field bundle changes. Legacy approved work without a performer is omitted from per-member totals rather than guessed. Removing the component restores the existing work board without data migration. Demo seeding runs only when creating a fresh demo calendar.

## Outcomes & Retrospective

The field work board now exposes a lightweight achievement layer without adding payment state or a member database. Administrators can compare approved and pending counts and use each member card as a task filter. Operators receive one private card for their authenticated identity. Approved work unlocks deterministic titles at 1, 3, 5, 10, and 20 tasks and shows progress to the next milestone; pending submissions never advance the title.

Validation completed on 2026-07-22:

- 387 Python tests passed.
- Ruff check and format check passed for 132 files.
- TypeScript checking and the Vite production build passed.
- The field-detail browser smoke passed with explicit administrator, operator, desktop, and 390-pixel mobile assertions.
- The LP build, worker test, JavaScript checks, and responsive browser smoke passed.

The result intentionally stops before a formal member directory, long-term aggregate API, wage calculation, escrow ledger, or payment integration. Those remain separate follow-on phases.
