# Daily plant-task notifications and safe device removal

This ExecPlan is a living document. It follows the ExecPlan requirement in `hub/AGENTS.md`; `.agent/PLANS.md` is not present in this checkout.

## Purpose / Big Picture

Cultivation work should become prominent only when it is actionable, and stale device identities must be removable without erasing historical measurements or breaking field bindings. After this change, plant suggestions start seven days before their work window, the Hub sends one visual Discord digest at 04:00 JST for newly added and currently actionable work, and operators can delete unreferenced device identities from the device list.

## Progress

- [x] (2026-07-18) Inspected plant suggestion dates, calendar persistence, Discord delivery, scheduler startup, device inventory persistence, and device-list UI/API.
- [x] (2026-07-18) Added seven-day suggestion behavior and a persistent 04:00 JST Discord embed digest.
- [x] (2026-07-18) Added reference-aware inventory deletion, audit events, a DELETE API, and per-card list controls.
- [x] (2026-07-18) Added focused regressions and documentation; all 263 Python tests and Ruff lint/format checks pass.

## Surprises & Discoveries

- Existing calendar actions do not contain per-action creation timestamps. A migration would fabricate dates, so the digest will keep a persistent set of known action IDs instead.
- Device detail GET currently calls `get_or_create`, so requesting a deleted ID would recreate it. Read-only detail endpoints must use the non-creating lookup.

## Decision Log

- Decision: Keep future winter actions in the calendar but expose them as suggestions only from seven days before `window_start`.
  Rationale: The full calendar remains useful for planning, while the current-work surface no longer presents seasonal work months early.
- Decision: On the digest task's first run, seed existing action IDs without classifying them as newly added. Later unseen IDs remain pending until a successful Discord delivery.
  Rationale: This is backward compatible with existing JSON data and avoids a one-time flood after upgrade.
- Decision: Schedule at 04:00 in `Asia/Tokyo`, independently of the host OS timezone.
  Rationale: The Hub is operated in Japan and the requested wall-clock time must not shift on UTC-configured runners or hosts.
- Decision: Deleting a device removes only the inventory/config identity. Historical telemetry and events remain. A device referenced by a field or layout is rejected with HTTP 409.
  Rationale: Old firmware identities can be cleaned up without corrupting agronomic history or leaving broken field relationships.

## Plan of Work

Change the repository suggestion default to seven days and expose a read-only action inventory for notification orchestration. Add a scheduled task with a small JSON state file, grouping new, upcoming, and in-window actions. Extend Discord delivery with embeds and a success result so state advances only after successful delivery. Start the task from production startup and document its settings.

Add repository deletion, a service that checks all field and layout references, a DELETE API, and per-card device-list controls with confirmation and conflict feedback. Ensure deleted detail reads do not recreate a record. Preserve measurement/event history.

## Validation and Acceptance

Focused tests must prove that an action eight days away is absent while one seven days away is present; first digest initialization does not report old actions; a later new action is reported once; due work is reported daily; Discord payloads use embeds; scheduler uses a 04:00 JST cron trigger; unreferenced devices delete; referenced devices return 409; and a deleted detail URL returns 404 without recreation. The full Python unittest suite and Ruff checks must pass.

## Idempotence and Recovery

The notification state is atomically stored in the Hub work directory. Re-running on the same local date does not duplicate the digest. Failed webhook delivery does not mark newly added actions as delivered. Device deletion is idempotent at the repository boundary; a missing device returns 404 at the API.

## Outcomes & Retrospective

The calendar remains a complete long-range plan, while the actionable suggestion surface now begins seven days before each window. A dedicated scheduler produces one 04:00 JST Discord embed with separate in-window, upcoming, and newly-added groups; it is backward compatible with existing calendar JSON because it tracks known IDs in a separate state file. Device maintenance cards now expose deletion with an explicit history/reconnection warning. The server blocks deletion while a field or layout still references the ID, retains telemetry/event history, audits successful deletion, and no longer recreates missing IDs on read-only detail requests.
