# Ground AI cultivation plans with public web evidence

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are updated while implementation proceeds.

## Purpose / Big Picture

AI cultivation plans currently fall back to generic observation guidance when no evidence is supplied. After this change, an enabled OpenAI text connection can perform one bounded web search before calendar generation, restricted to Japanese government, local-government, and NARO domains. The provider returns a short structured summary and traceable sources, caches the result by crop and cultivation conditions, and supplies it to the existing planning prompt. The calendar UI shows clickable evidence links and clearly distinguishes evidence-backed output from generic fallback output.

## Progress

- [x] (2026-07-19) Traced the background generation task, prompt construction, care-profile normalization, settings persistence, and calendar evidence UI.
- [x] (2026-07-19) Verified from official OpenAI documentation that Responses API `web_search` supports domain filters and complete source lists.
- [x] (2026-07-19) Added a bounded crop-knowledge provider with trusted-domain validation, OpenAI Responses adapter, and thirty-day default cache.
- [x] (2026-07-19) Fed evidence into plan generation and persisted legacy source labels plus structured evidence without breaking older records.
- [x] (2026-07-19) Added administrator search/cache settings and clickable source presentation.
- [x] (2026-07-19) Passed 331 Python tests, focused Ruff checks, the admin UI build, and the field-detail browser smoke; visually inspected desktop calendar and mobile settings captures.

## Surprises & Discoveries

- Observation: `care_profile.knowledge_sources` is currently normalized as a list of strings, so it cannot preserve publisher, applicability, and retrieval time by itself.
  Evidence: `_normalize_care_profile` calls `_clean_string_list` for this field.

- Observation: `generation.context_snapshot` already preserves arbitrary dictionaries, allowing the exact evidence snapshot used by a generation to be retained without a database migration.
  Evidence: `_normalize_generation` accepts any dictionary for `context_snapshot`.

- Observation: the Hub advertises an OpenAI-compatible Chat Completions endpoint, but provider-hosted web search with domain filtering is specific to the OpenAI Responses API.
  Evidence: the OpenAI web-search guide states domain filtering is available with Responses API `web_search`; compatibility therefore must be detected rather than assumed.

## Decision Log

- Decision: Enable evidence search by default only for an enabled text-AI connection whose base URL is the official OpenAI API (or the existing blank default that resolves there), and expose an administrator toggle.
  Rationale: this makes the requested feature usable without a second search vendor while avoiding repeated failing calls and undefined behavior on generic compatible providers.
  Date/Author: 2026-07-19 / Codex

- Decision: Restrict search to `maff.go.jp`, `naro.go.jp`, `go.jp`, and `lg.jp`, validate returned URL hosts again, and discard summaries with no accepted source.
  Rationale: retrieved page text is untrusted input. Both search-time and persistence-time restrictions reduce unsupported blogs, stores, and fabricated citations.
  Date/Author: 2026-07-19 / Codex

- Decision: Keep the legacy string source list and add `knowledge_evidence` as an optional structured list.
  Rationale: older records and clients remain valid, while new clients can render source title, publisher, URL, applicable region, publication date, and retrieval time.
  Date/Author: 2026-07-19 / Codex

- Decision: Cache provider results in a separate work-directory JSON file for thirty days, keyed by normalized crop, cultivar, category, age, method, substrate, environment, and prefecture.
  Rationale: generation tasks remain durable and deterministic, repeated regeneration avoids search cost, and provider failure does not corrupt plant-management data.
  Date/Author: 2026-07-19 / Codex

## Plan of Work

Create `crop_knowledge_provider.py` as the external-system adapter. It builds a normalized key, reads and writes a bounded cache using the repository file lock, calls `/responses` with the hosted web-search tool, parses output text and complete source metadata, validates URLs, and returns explicit status values without raising into calendar generation.

Inject the provider into `PlantCalendarGenerationTask`. Add the result to `context.crop_knowledge` before calling `AIContentService`. Strengthen the fixed prompt contract so only supplied evidence may be used, then force the persisted source fields from the validated context rather than accepting model-created sources. Improve deterministic fallback assumptions for available, unavailable, disabled, and cached evidence.

Extend repository normalization and TypeScript types with `knowledge_evidence`. Render accepted sources as external links beneath the cultivation basis. Add an advanced administrator toggle and cache-duration input to the AI settings page, preserving runtime defaults for existing databases.

## Validation and Acceptance

Provider tests must prove trusted-domain filtering, structured response parsing, cache reuse without another HTTP request, unsupported compatible-provider behavior, and safe failure. Worker tests must prove evidence is in the AI context. AI service and repository tests must prove evidence-backed assumptions and backward-compatible structured persistence. Settings tests must prove values survive save/load.

Run from `hub`:

    UV_CACHE_DIR=.uv-cache uv run python -m unittest tests.test_crop_knowledge_provider tests.test_plant_calendar_generation_task tests.test_ai_content_service tests.test_plant_management_repository tests.test_web_server_basic_ui
    UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
    UV_CACHE_DIR=.uv-cache uv run ruff check src tests
    UV_CACHE_DIR=.uv-cache uv run ruff format --check src tests

Then run `npm run build` from `hub/admin-ui`, start the local demo, capture the calendar page, and verify evidence links, assumptions, layout, and absence of browser errors.

## Idempotence and Recovery

The provider never mutates plant records and returns a status object on errors. Cache writes are atomic and old or malformed cache files are treated as empty. Existing calendar records gain an empty `knowledge_evidence` list during normalization. Disabling the setting or using a non-OpenAI provider returns immediately and leaves the current deterministic planning path intact.

## Outcomes & Retrospective

Calendar generation now performs a bounded public-evidence lookup when the configured text provider is the official OpenAI API and the administrator toggle is enabled. It restricts hosted search to government, NARO, and prefectural official domains, validates every returned URL again, refuses summaries without accepted sources, and stores at most eight concise sources. Cache keys include crop and cultivation conditions, cache writes are separate and atomic, and a removed AI key can still use a valid prior cache entry.

The worker adds `crop_knowledge` to the generation snapshot before the existing LLM call. The fixed prompt treats it as untrusted external data rather than instructions, and `AIContentService` replaces model-proposed citations with provider-validated evidence. Fallback copy now explains whether evidence was available, not found, disabled, unsupported, or failed. Repository normalization keeps the original string list and adds optional structured evidence, so existing databases load without migration.

The calendar cultivation-basis panel shows clickable public sources with publisher, applicability, publication date, and retrieval date. The demo fixture contains two real official entry points, enabling deterministic browser validation without a paid search call. Final validation was 331 passing Python tests, successful Ruff check and format verification for all touched Python files, a successful TypeScript/Vite build, and a passing field-detail browser smoke. The inspected desktop capture showed the expanded evidence panel without clipping or overlap; the inspected mobile settings capture showed the enable toggle, cache-days input, cost note, and provider limitation in the expected advanced AI section.
