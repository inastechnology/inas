# Camera crop-growth monitoring and AI work suggestions

This ExecPlan is a living document. It follows the ExecPlan requirement in `hub/AGENTS.md`; `.agent/PLANS.md` is not present in this checkout.

## Purpose / Big Picture

Users can register and place a camera, capture time-lapse frames, and compare images, but the Hub does not yet turn those observations into a crop-specific assessment. Add an explicit user-triggered workflow that captures a current image, relates it to the camera's monitored placements and active plantings, compares it with a suitable prior frame, asks the configured image AI for a structured evidence-based assessment, stores the result, and presents growth condition and suggested work with uncertainty and safety limits.

## Progress

- [x] (2026-07-19) Audited camera capture, frame storage, field layout targeting, active plantings, image AI, field monitoring UI, and existing work suggestions.
- [x] (2026-07-19) Defined and implemented the bounded assessment model, repository, AI contract, and monitoring service.
- [x] (2026-07-19) Added authenticated API endpoints and a field growth-monitoring UI.
- [x] (2026-07-19) Added focused regression coverage and ran the complete Hub validation suite.
- [x] (2026-07-19) Committed and pushed `main`, deployed through the standard update workflow, and verified readiness and the live Reolink capture path.

## Surprises & Discoveries

- The installation layout already records camera-to-growing-area relationships in `binding.target_placement_ids`, so assessments can resolve monitored crops without a second mapping model.
- Time-lapse frames and day-based image comparisons already exist, but there is no persistent crop assessment or structured image-analysis contract.
- The current image AI path is limited to an unstructured Instagram caption summary. Local camera URLs cannot be fetched by an external AI provider, so selected JPEG bytes must be sent as bounded data URLs during the explicit analysis request and never persisted in the assessment record or logs.
- Existing action candidates are sensor-rule based. Camera recommendations need a distinct suggestion-only lifecycle so an uncertain visual interpretation cannot silently become an executable calendar task.

## Decision Log

- Decision: Make analysis explicit and user-triggered, and state in the UI that selected camera images are sent to the configured AI service.
  Rationale: Image transfer and model cost should be visible and deliberate; background capture remains independent.
- Decision: Persist structured assessment metadata and results, but reference stored frame paths instead of copying image bytes or credentials.
  Rationale: This provides an auditable history and trend view without creating a second image store or leaking sensitive data.
- Decision: Require a placed registered camera with at least one monitored placement and resolve active plantings from those targets.
  Rationale: Visual findings only become useful crop guidance when the physical area and crop identity are known.
- Decision: Keep proposed work as reviewable recommendations rather than automatically changing the cultivation calendar or controlling devices.
  Rationale: Camera-only evidence is incomplete, and high-impact watering, fertilizer, chemical, pruning, or harvest actions require user confirmation and often another observation.
- Decision: Compare the current capture with a prior frame when one is available and clearly report when comparison evidence is absent.
  Rationale: Growth is a change over time; a single image can describe visible condition but cannot reliably establish a trend.

## Plan of Work

Add a JSON-backed repository with bounded, normalized assessment history. Add an AI content method with a strict JSON schema covering visible observations, comparison, concerns, confidence, limitations, and work suggestions. Add a monitoring service that validates field/layout/camera relationships, captures and saves a bounded current frame, selects a prior frame, builds a minimal crop and field context, invokes image analysis, validates model output, and saves only safe structured results.

Expose list and create endpoints beneath the field API. Add a dedicated field growth-monitoring page showing camera coverage, current/live navigation, latest assessment state, evidence, change history, warnings, and proposed work. Provide recovery guidance for missing camera targets, active plantings, prior images, or image-AI configuration.

## Validation and Acceptance

Repository tests must prove normalization, ordering, filtering, and history bounds. Service tests must prove relationship validation, current/prior image selection, AI context safety, persistence, and unavailable-AI errors. HTTP/UI tests must prove the authenticated field page and APIs expose useful states without credentials or image bytes. Run formatting/linting, the complete Python suite, and the frontend build required by deployment. On the running Hub, verify health/readiness and confirm the existing Reolink camera appears as a growth-monitoring source without triggering a paid AI analysis automatically.

## Idempotence and Recovery

The repository is additive and creates its runtime JSON file atomically on first use. Repeating a user analysis creates a new immutable observation rather than mutating prior evidence. If capture or AI analysis fails, do not save a successful assessment and leave existing images/history unchanged. Deployment must preserve runtime JSON, `.env`, camera credentials, MQTT, HTTP, and Cloudflare settings.

## Outcomes & Retrospective

The implementation now resolves crops inside directly monitored areas and nested child spaces, captures through a bounded ffmpeg process, compares against a frame 12 hours to 14 days old when available, sends no more than two bounded JPEG data URLs to the configured image AI, normalizes the response, and stores a reviewable history without image bytes or camera credentials. The UI makes image transfer explicit and keeps every work item suggestion-only.

Validation completed before deployment on 2026-07-19:

- Focused camera growth, AI contract, web route, and bounded capture tests passed: 18 tests.
- The complete Hub unittest suite passed: 307 tests.
- Ruff lint and formatting checks passed for all changed Python files.
- The React TypeScript check and Vite production build passed.
- Commit `64b45e6` was pushed to `origin/main` and deployed with a pre-start state backup.
- Production `healthz` returned `ok`; `readyz` returned `ready` with MQTT and Web checks true.
- The production growth-monitoring page resolved `garden` as ready for analysis, while the history API remained empty because deployment did not trigger a paid image analysis.
- A bounded production capture from the existing Reolink camera returned a valid 238,047-byte JPEG without saving or sending it to AI.
