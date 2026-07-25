# Docs-site product screenshots and isolated demo states

This ExecPlan is a living implementation record. `hub/AGENTS.md` requires an
ExecPlan for significant Hub work; the referenced repository-root
`.agent/PLANS.md` is not present in this checkout, so this document follows the
existing `hub/.agent/` convention.

## Purpose

Public task guides should show the same Hub or device screen that the reader is
being asked to operate. After this work, docs-site pages for initial device
setup, field/device setup, irrigation, daily work, AI calendar review, firmware
updates, Runtime Config, and troubleshooting contain current screenshots from a
deterministic demo. The capture workflow starts its own Hub work and storage
directories under a temporary directory, never inherits production Turso or AI
credentials, and can be rerun when a UI feature changes.

## Progress

- [x] (2026-07-24) Inspected repository instructions, docs-site content, the
  existing Hub demo fixture, and current screenshot/smoke scripts.
- [x] (2026-07-24) Identified reusable populated states: field dashboard,
  installation layout, device catalog/detail, irrigation settings, firmware,
  and cultivation calendar.
- [x] (2026-07-24) Added documentation-only routes and deterministic state selection to the
  isolated demo server, including the firmware setup portal and AI proposal
  review.
- [x] (2026-07-24) Added a reproducible capture script and generated 13 public
  screenshot assets.
- [x] (2026-07-24) Placed screenshots beside the matching instructions and documented the
  refresh workflow.
- [x] (2026-07-24) Ran focused and full tests, builds, capture validation, docs checks, and visual
  browser inspection.

## Surprises and discoveries

- The existing `run_admin_demo_server.py` already isolates `WORK_DIR`, local
  storage, Turso, and AI settings and seeds a rich strawberry field. Extending
  this fixture is safer and more representative than building a second mock UI.
- The device setup portal is firmware-hosted and therefore is not reachable
  from the Hub demo. A host-renderable documentation fixture must mirror its
  actual markup and be exposed only by the isolated demo runner.
- Device detail tabs already have stable URL parameters. The cultivation
  calendar currently defaults to the work board and does not have a deep link
  for crop-plan or AI-review state, so a generic query-driven initial view is
  needed for reproducible screenshots.
- The new hierarchy sync layer validates production device IDs as
  `INADS-UUIDv4`, while the longstanding demo uses human-readable
  `INADS-DEMO-*` IDs. The isolated demo now bypasses only its local hierarchy
  runtime-config cache; production validation remains unchanged.
- The in-app browser runtime could not attach to this WSL workspace. The same
  browser assertions were completed with the repository's local Puppeteer
  runtime, and representative WebP and rendered docs artifacts were inspected
  directly.
- The worktree contains extensive unrelated edits. This change must remain
  additive and avoid rewriting or reverting those files.

## Decision log

- Use the real Hub application backed by the existing demo repositories for all
  Hub screenshots. Use a firmware-markup fixture only for the ESP32 setup portal
  that cannot run without hardware.
- Add a `/docs-demo` navigator only to `run_admin_demo_server.py`; do not expose
  documentation fixtures from the production Hub server.
- Seed AI review proposals only when
  `HUB_DEMO_SCENARIO=documentation`, preserving existing marketing/video demo
  behavior.
- Allocate fresh temporary work/storage paths in the capture script and pin the
  fixture date. Generated screenshots contain only fictional IDs, locations,
  and documentation-only network values.
- Store web-optimized screenshots in
  `docs-site/public/images/screenshots/` and reference them with descriptive
  alternative text and captions.

## Implementation outline

Add pure HTML helpers for the documentation demo navigator and the device setup
portal, register them in the isolated demo runner, and add focused tests for
state whitelisting and secret-free markup. Extend the demo fixture with an
explicit date override and an optional AI regeneration review proposal.

Let the calendar read `view=crop` and `review=ai` on initial load so a demo URL
can open the exact state without scripted clicks. Preserve the current default
when those parameters are absent.

Add `docs-site/scripts/capture-product-screenshots.mjs`. It starts the Hub demo
in a fresh temporary directory, waits for readiness, opens a manifest of stable
URLs/selectors, checks for browser errors and horizontal overflow, writes named
WebP files, and stops/removes only its own child process and temporary files.
The docs-site package exposes this as a dedicated capture command.

Add screenshot figures to the task pages that describe those screens. Create a
short AI calendar operations page because the requested “AI proposal
immediately after generation” state is a meaningful user workflow that is not
currently documented.

## Validation

Run the demo helper tests and relevant Hub tests, the admin UI typecheck/build,
the new screenshot capture command, and `npm run check` in docs-site. Start the
docs preview and inspect desktop plus narrow layouts in the in-app browser.
Confirm every referenced asset returns 200, captions match the visible screen,
no screenshot contains credentials or production identifiers, and the capture
process uses only its generated temporary directories.

## Outcomes and retrospective

The documentation demo now exposes a `/docs-demo` navigator with stable initial
setup, recovery, populated field/device, calendar workspace, and AI review
states. `npm run capture:product-screenshots` creates a fresh temporary Hub,
scrubs inherited connector and credential settings after `.env` loading,
captures 13 WebP assets, verifies expected content/browser errors/overflow, and
removes its temporary state.

The public site references every generated asset, checks for missing and
orphaned screenshots, and adds an AI cultivation plan and proposal-review
guide. Validation completed with all 441 Hub unit tests, Ruff check and format,
admin UI typecheck/build, Astro check/build/content validation, a 32-page link
and desktop/mobile smoke pass, and manual visual inspection of representative
source and rendered screenshots.
