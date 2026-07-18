# Place cameras and their monitored areas in the installation view

This ExecPlan is a living document. It follows the ExecPlan requirement in `hub/AGENTS.md`; `.agent/PLANS.md` is not present in this checkout.

## Purpose / Big Picture

Operators can register network cameras, but cannot yet place them on a field installation map. Add a camera preset to the installation editor, expose registered cameras such as `garden` in its device selector, and let the operator associate one camera with one or more existing growing areas. Store those monitored-area relationships as layout placement IDs so the field detail view and future AI image-analysis workflows can resolve the camera image to the relevant crop and physical area.

## Progress

- [x] (2026-07-18) Audited camera registration, layout device options, placement validation, target relationships, canvas rendering, and field-detail projections.
- [x] (2026-07-19) Added registered cameras to layout device options without merging them into the MQTT device lifecycle.
- [x] (2026-07-19) Added the camera placement preset, camera-specific binding, monitored-area selection, and canvas relationship rendering.
- [x] (2026-07-19) Added regression coverage and built the admin UI.
- [ ] Deploy, verify the running Hub, commit, and push the completed implementation.

## Surprises & Discoveries

- The layout schema already supports `resource_type: "camera"` and multiple `target_placement_ids`; only the `camera` placement preset and inventory aggregation are missing.
- Camera records intentionally live outside the MQTT device configuration repository, so the layout option endpoint must aggregate the two inventories at its presentation boundary.
- Existing layout connections already project cross-space relationships and can visualize camera coverage without adding a second geometry model.

## Decision Log

- Decision: Represent the monitored area with `binding.target_placement_ids` pointing to greenhouse, open-field, shade, ridge, tree, pot, or hydroponic placements.
  Rationale: These stable semantic IDs let UI and AI consumers resolve the monitored crop, space, and location; a free-text description or raw polygon would lose that relationship.
- Decision: Keep camera registration in the camera management service and aggregate public camera records only in layout device options.
  Rationale: RTSP cameras remain outside MQTT configuration, firmware, and state management while becoming selectable in the field editor.
- Decision: Use the camera placement coordinates for the physical installation point and connection arrows for its monitored targets.
  Rationale: The existing editor already supports placement, resizing, cross-space targets, save conflicts, undo, and accessible connection summaries.

## Plan of Work

Extend the backend placement allowlist and labels with `camera`. Aggregate redacted camera-management records into the layout device option projection with camera-specific type, group, state, location, resource, and navigation URLs. Ensure field-detail device records can resolve camera names and monitoring targets.

Add a camera palette item to the React editor. Restrict its selector to registered cameras, always save its binding as `resource_type: "camera"`, label target selection as monitored areas, show preview and settings links, and render camera coverage connections distinctly on the canvas.

## Validation and Acceptance

Focused backend tests must prove a registered camera appears in layout options, can be saved as a camera placement with monitored targets, stays unavailable to another field after assignment, and is projected by name into field detail. The admin UI typecheck/build must pass, along with focused and complete Python tests required by deployment.

## Idempotence and Recovery

The change adds no destructive migration. Existing layouts normalize unchanged; camera placements are accepted only after the new code is running. Deployment preserves runtime JSON and credentials. If validation fails, leave the current service and user data untouched and diagnose before rerunning deployment.

## Outcomes & Retrospective

The installation editor now treats a registered network camera as a first-class placement while retaining the separate camera and MQTT lifecycles. A camera placement stores its physical position and the stable IDs of all monitored growing areas, renders those relationships as distinct monitoring arrows, and links directly to preview and settings. The field detail projection resolves the camera name and reports the monitored targets, providing a semantic camera-to-crop mapping for future image-analysis context.

Validation completed on 2026-07-19:

- React TypeScript checking and the production Vite build passed; generated static assets were refreshed.
- Focused camera layout repository and HTTP tests passed.
- The complete Hub unittest suite passed: 298 tests.
- Ruff lint and formatting checks passed for the changed Python layout and web files.
