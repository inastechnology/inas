# Move fertilizer presets into a shared Hub catalog

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

The annual cultivation calendar currently owns fertilizer reference values inside its React source. After this change, the Hub exposes one fertilizer catalog to the calendar UI, AI planning context, and future soil/fertilizer agents. The catalog contains reviewed built-in references and user-created products. A user can select a catalog entry while recording fertilization, adjust the actual label values, and safely retain the exact values used even if the catalog changes later.

This is the first narrow implementation step toward agentic agriculture. It does not attempt to automate fertilizer recommendations yet; it creates the stable, inspectable data boundary those recommendations require.

## Progress

- [x] (2026-07-19) Traced the current hard-coded React presets, application persistence, API routes, field bundle, and fertilizer-effect calculation.
- [x] (2026-07-19) Added a versioned built-in catalog and backward-compatible custom-material persistence.
- [x] (2026-07-19) Added thin catalog CRUD routes and application snapshot resolution.
- [x] (2026-07-19) Replaced browser-owned presets with the Hub catalog and added a custom-fertilizer management modal.
- [x] (2026-07-19) Added repository, route, generation-context, and browser regression coverage.
- [x] (2026-07-19) Built and ran the demo, captured desktop/mobile cultivation-calendar screens, and visually inspected the results.

## Surprises & Discoveries

- Observation: The current UI already contains useful public reference values, but they exist only in `PlantCalendarDrawer.tsx` and therefore cannot be used by server-side planning.
  Evidence: `FERTILIZER_PRESETS` is a local TypeScript constant and the application API receives only copied numeric fields.

- Observation: Fertilizer applications already store all numeric values required for an immutable historical record.
  Evidence: repository normalization persists nutrient percentages, annual availability, duration, delay, and analysis source.

- Observation: The headless demo environment has no reliable color-emoji font.
  Evidence: initial screenshots rendered fertilizer emoji as missing-glyph squares; environment-independent Lucide SVG icons fixed the issue.

- Observation: Capturing immediately after the modal selector appears can record the backdrop during its 150ms transition.
  Evidence: the first desktop screenshot showed the Gantt grid through a partially faded backdrop; waiting 250ms produced the intended opaque dialog.

## Decision Log

- Decision: Store built-in definitions in a versioned JSON file and store only user definitions in `.plant_management.json`.
  Rationale: reviewed defaults remain reproducible in Git, while users can add products without editing or rebuilding the application.
  Date/Author: 2026-07-19 / Codex

- Decision: Add `fertilizer_materials` as an optional top-level collection and normalize a missing collection to an empty list.
  Rationale: existing Hub databases require no migration and preserve every current planting, calendar, and fertilizer application.
  Date/Author: 2026-07-19 / Codex

- Decision: Persist `material_id` and `material_snapshot` on new applications while retaining all existing flattened fields.
  Rationale: history must not change when a user edits or removes a catalog item, and older clients/data remain valid.
  Date/Author: 2026-07-19 / Codex

- Decision: Treat built-in values as editable starting points, not agronomic truth.
  Rationale: product labels, laboratory analysis, local standards, weather, and crop condition have priority over general reference values.
  Date/Author: 2026-07-19 / Codex

## Plan of Work

Create a small domain module that loads and validates `data/fertilizer_material_catalog.json`, merges built-ins with repository-backed custom materials, and resolves identifiers. Extend `PlantManagementRepository` with list/create/update/delete operations for custom materials. When an application contains `material_id`, resolve the catalog item on the server, use its values as defaults, and persist a snapshot beside the existing flattened application fields.

Expose GET and POST on `/local/api/fertilizer-materials`, plus PATCH and DELETE for custom entries. Keep Flask handlers limited to request parsing and repository/service calls. Include the merged catalog in each field bundle so the existing calendar load obtains its options without another page-specific request.

Add matching TypeScript types and API functions. Refactor the fertilizer panel to receive catalog entries, display built-in and user sections, and manage user-created products in a modal. Recording a fertilization sends the catalog identifier and still sends the visible adjusted values so the server can preserve the actual label used.

## Validation and Acceptance

Repository tests must prove that a legacy document with no material collection loads, built-ins are always present, custom CRUD persists, built-ins cannot be edited or deleted, and application snapshots survive later catalog changes. Route tests must prove catalog listing and custom CRUD behavior. Existing application and field-bundle tests must remain green.

Run from `hub`:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_plant_management_repository tests.test_web_server_basic_ui tests.test_admin_demo_server
    UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Run from `hub/admin-ui`:

    npm run build

Then start the deterministic demo server, open the annual cultivation calendar, add or inspect a custom fertilizer, capture the screen, and verify that source copy, values, modal layout, and responsive behavior are visually correct with no browser errors.

## Idempotence and Recovery

Catalog reads do not mutate the plant-management file. Missing or malformed optional custom collections normalize to empty. Built-in IDs use a reserved prefix and cannot be overwritten. Application snapshots mean deletion of a custom material is safe for history. Atomic repository writes retain the current recovery behavior.

## Outcomes & Retrospective

The Hub now loads seven reviewed built-in fertilizer references from a packaged, versioned JSON catalog and merges them with up to 500 user-created products stored in the existing plant-management document. A missing `fertilizer_materials` collection normalizes to an empty list, so existing databases require no migration. Built-in identifiers are reserved and immutable; user entries support create, update, and delete through thin JSON APIs.

New fertilizer applications may reference a catalog identifier. The server applies catalog values as defaults, accepts the visible user-adjusted label values, and stores both the existing flattened fields and an immutable material snapshot. Editing or deleting a user catalog item therefore does not rewrite past fertilization history. Legacy application payloads without an identifier continue to work.

The annual calendar no longer owns fertilizer presets. It receives the merged catalog in the field bundle, groups common and registered products, and offers a graphical catalog modal. The beginner path asks for the product name and printed N-P-K-Mg values; effect rate, duration, delay, evidence, and URL are collapsed under an advanced disclosure. The same catalog is now included in AI calendar-generation context with a prompt rule that general reference values are editable starts rather than agronomic facts.

Final validation passed 332 Python tests, focused Ruff lint and format checks, TypeScript/Vite production build, wheel packaging verification for the JSON catalog, and the complete field-detail browser smoke. Browser checks exercised catalog rendering, custom-material entry, reference selection, fertilization recording, desktop/mobile layout, and absence of console errors. Visual inspection of `/tmp/ina-fertilizer-catalog-desktop.png`, `/tmp/ina-fertilizer-catalog-mobile.png`, `/tmp/ina-fertilizer-catalog-add.png`, and `/tmp/ina-fertilizer-effect-desktop.png` confirmed readable hierarchy, SVG icons, collapsed advanced inputs, and no clipping or horizontal overflow.
