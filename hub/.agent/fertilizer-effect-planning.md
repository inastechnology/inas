# Add substrate-level fertilizer effect planning

This ExecPlan is a living document and follows `hub/AGENTS.md`.

## Purpose / Big Picture

Ridge and other substrate placements need a fertilizer history that survives calendar regeneration and lets the plan distinguish “fertilizer applied” from “nutrients expected to be plant-available now.” An operator should record the material, applied kilograms, label/analysis N-P-K percentages, and an explicit estimated annual availability and duration. The UI then shows the effect window and estimated available nutrients. AI planning receives this structured balance and must avoid recommending additional fertilizer solely because time has elapsed.

## Progress

- [x] (2026-07-18) Audited planting persistence, layout placement ownership, calendar generation context, and calendar UI.
- [x] (2026-07-18) Added a backward-compatible fertilizer application ledger and deterministic nutrient-effect calculator.
- [x] (2026-07-18) Added APIs and included the placement fertilizer balance in initial, regenerated, follow-up, and question contexts.
- [x] (2026-07-18) Added a substrate-focused fertilizer history and effect UI with safe defaults and validation.
- [x] (2026-07-18) Strengthened AI and fallback instructions against over-application and completed tests, docs, build, and browser validation.

## Decisions

- Store fertilizer applications at field/space/placement level, with an optional planting id. Organic amendments can continue affecting a ridge across crop rotations.
- Preserve the repository schema and normalize a missing `fertilizer_applications` array to an empty list; no destructive migration is required.
- Calculate nutrient quantities from applied material kg and user-entered label percentages for N, P2O5, and K2O. Never treat total product kg as nutrient kg.
- Model effect as a transparent estimate: start delay, annual plant-available percentage, and number of effect years. Spread the estimated available amount across the stated window for planning summaries. This is not a soil analysis or a guarantee.
- Offer material presets only to fill an editable starting estimate. The screen must tell users to prefer product analysis, local guidance, soil tests, EC, crop condition, and harvest quality.
- AI must receive both the original records and a deterministic as-of-date summary. It may recommend measuring or reviewing; it must not invent product composition or add fertilizer when remaining effect or EC risk is uncertain.

## Validation

Unit tests will cover normalization, kg-to-N/P/K conversion, delayed/multi-year effect windows, historic JSON without the new key, placement-scoped retrieval, API validation, and AI prompt inclusion. UI build and browser smoke will verify adding a ridge application, the visible effect summary, safety copy, and calendar regeneration guidance. The full Python suite, Ruff, production UI build, and `git diff --check` must pass.

Validation completed on 2026-07-18:

- `PYTHON_DOTENV_DISABLED=1 UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests`: 271 tests passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff check .`: passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff format --check .`: 114 files already formatted.
- `npm run build`: TypeScript and Vite production build passed.
- `HUB_URL=http://127.0.0.1:39251 npm run smoke:field-detail`: passed, including fertilizer entry, N/P2O5/K2O balance display, caution copy, calendar interactions, and mobile overflow.
- `git diff --check`: passed.

## Outcomes

The calendar now has a placement-scoped fertilizer ledger. An application records product kg separately from nutrient percentages and an explicit annual availability model. The deterministic calculator produces applied, expected-available, released, remaining, and 12-month forecast nutrient kg. Calendar generation, follow-up planning, and plant questions receive this context. Both AI instructions and the non-AI fallback prefer measurement or deferral when remaining effect or EC risk makes another application uncertain. Historic repository JSON without the new array continues to load as an empty fertilizer ledger.
