# Unify Hub screens around the field-view experience

This ExecPlan is a living document. It follows `hub/AGENTS.md`; `.agent/PLANS.md` is absent from this checkout.

## Purpose / Big Picture

The Hub currently feels like several unrelated applications: the field pages use a restrained green operational design, while device maintenance is a dense blue/gray administrator console with duplicated navigation and low-frequency diagnostics competing with daily decisions. This change makes the field view the visual and information-architecture source of truth. Operators should see device health, current measurements, controlled loads, firmware status, and the next useful action first; advanced configuration and raw diagnostics remain available but recede behind clearly named disclosure controls.

## Progress

- [x] (2026-07-18) Audited route inventory, field templates, settings/preferences, plant calendar/layout shells, and the large device maintenance template.
- [x] (2026-07-18) Loaded the `comfyui-media-generator` workflow instructions and verified the configured ComfyUI server.
- [x] (2026-07-18) Generated four coherent ComfyUI illustrations and wired them into field, device, firmware, settings, preferences, and fallback screens.
- [x] (2026-07-18) Rebuilt device catalog/detail hierarchy, firmware flow, operational readiness, and MOSFET visualization without changing persisted device schemas.
- [x] (2026-07-18) Applied the shared visual language and contextual illustrations to the remaining user-facing Jinja and legacy screens.
- [x] (2026-07-18) Updated the screen specification and passed the 263-test backend suite, Ruff checks, production UI build, and all available browser smoke flows.

## Surprises & Discoveries

- The device catalog/detail is one approximately 2,200-line inline Jinja template embedded in `web_server.py`; it uses a separate blue administrator theme and exposes both list and demo navigation in the global top-right area.
- Device detail already has substantial operational view-model data, so the redesign can prioritize existing values without changing the device protocol or persisted configuration schema.
- Field catalog, field detail, settings, and preferences each define their own large embedded stylesheet. A shared additive stylesheet can unify tokens, typography, headers, cards, and illustration treatments without a risky template migration in one step.
- Full-page browser screenshots make the sticky tab row appear over content at the captured scroll point; in the interactive viewport it remains a useful persistent mode switch and causes no horizontal overflow.

## Decision Log

- Decision: Use the field-view green/earth palette, 1240px content width, restrained borders, and action-first cards as the shared language.
  Rationale: This is the application's primary user workflow and already communicates agronomic context more clearly than the maintenance console.
- Decision: Remove UI Demo from normal navigation and expose it only through an advanced development disclosure on the real catalog.
  Rationale: Demo data is not a normal operational destination and competes with the real-device path.
- Decision: Give each detail tab a single primary job. Firmware begins with current/available version and an adjacent drag-and-drop update area; diagnostics/raw JSON move below advanced disclosures.
  Rationale: The highest-frequency intent must not require scanning unrelated controls.
- Decision: Render MOSFET channels as a controller-to-load flow board with channel state, terminal, role, and target, while retaining the editable form below.
  Rationale: A user should understand what switching a channel affects before reading configuration fields.
- Decision: Use generated illustrations as explanatory landmarks and empty-state help, never as the sole carrier of state or instructions.
  Rationale: UI text and accessible controls remain authoritative; imagery improves recognition without reducing accessibility.

## Plan of Work

Generate four text-free illustrations through the approved ComfyUI workflow: field operations, device family, firmware maintenance, and controller/output flow. Keep dimensions modest, place outputs under `src/ina_device_hub/static/ui-illustrations`, and reference them with accessible alt text.

Add a shared `hub-ui.css` containing common tokens and illustration/card treatments. Link it from all standalone Jinja pages and use compatible classes to harmonize headers, surfaces, buttons, empty states, and page rhythm. Preserve the React installation and calendar bundle behavior while adding illustration hooks only where their shell supports them.

Restructure the device template: one breadcrumb/back location, no duplicate catalog action, normal navigation free of demo links, summary hero with device identity/health/current version, compact operational metrics, simplified tabs, and progressive disclosure. Move firmware upload next to the current version and make its drop zone the primary action. Add a visual MOSFET flow board driven by existing switch view data. Rename technical labels with plain-language primary text and technical terms as secondary text.

Audit every public HTML route and either apply the shared shell directly or document why it is a legacy/deep-link page. Add contextual illustrations to field catalog/detail, device list/detail, settings/preferences, media empty states, and forbidden/empty states where they materially orient the user.

## Validation and Acceptance

Server tests must preserve all routes and actions. Device HTML tests must assert one catalog-back affordance, no normal demo navigation on real pages, the firmware drop zone next to version content, MOSFET visual board, and advanced raw diagnostics. Generated files must exist and be served by Flask. Run the complete Python unittest suite, Ruff lint/format, the admin UI production build, and the existing browser smoke flow if available.

## Idempotence and Recovery

Generated image jobs use fixed seeds and explicit output paths. Existing device protocol fields and persisted settings remain unchanged. The redesign is template/CSS/view-only except for small derived view-model fields, so rollback does not require data migration.

## Outcomes & Retrospective

The device catalog and detail screens now read as part of the field application: one breadcrumb, one field-list destination, field-context cards, operational readiness, and plain-language tabs. Firmware inspection, upload, and update reservation are colocated; controller outputs are readable as a live controller-to-load map before the advanced fields are opened. A shared additive stylesheet harmonizes the remaining Jinja and legacy pages while preserving the existing React bundles and URLs. Four ComfyUI-generated illustrations provide landmarks for field work, device families, firmware care, and controller outputs without carrying authoritative state.

Validation completed on 2026-07-18: `python -m unittest discover -s tests` passed 263 tests; `ruff check .` and `ruff format --check .` passed; `npm run build` passed; browser smoke runs for device detail, fields, field detail, settings, installation layout, and plant calendar all passed, including zero horizontal overflow at 390px.
