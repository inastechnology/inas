# Field Weather, Cultivation Research, and Work-Decision Specification

Updated: 2026-07-30

Status: specified, not yet implemented. The current weather recorder remains
available. The first delivery phase is limited to research, explanation, and
human-reviewed guidance; weather alone must not change device Runtime Config or
execute an actuator.

Japanese specification:
[HUB_WEATHER_CULTIVATION_RESEARCH_SPEC.md](jp/HUB_WEATHER_CULTIVATION_RESEARCH_SPEC.md)

## Goal

Connect field-level weather history and forecast snapshots to sensor
measurements, irrigation, fertilization, calendar work, human observations,
images, growth stages, yield, and quality. A grower should be able to examine
field-specific relationships and save a testable hypothesis without presenting
correlation as causation.

## Governing distinctions

- Keep field observations, external analysis/reanalysis, forecast snapshots,
  derived metrics, model estimates, and human observations as separate source
  types.
- Preserve the spatial scope of every value. External weather represents a
  field area; an ENV sensor may represent a greenhouse; an SOI sensor may
  represent one bed or point; work and growth outcomes belong to a placement or
  planting.
- Never rewrite a forecast into an observation after the forecast period.
  Preserve every issued-at snapshot so the system can reconstruct what was
  known when a work decision was made.
- Compute aggregation, accumulated temperature, VPD, water-balance features,
  Pearson correlation, Spearman correlation, lag comparisons, sample counts,
  and missingness in deterministic services. An LLM may explain results but
  must not invent statistics or causal conclusions.
- Phase 1 does not modify work dates, irrigation schedules, or Runtime Config.
  Later guidance, approved changes, and closed-loop control require separate
  gates.

## Planned domain additions

Each field gains a confirmed `weather_location` with coordinates or an
approximate municipality-level location, timezone, elevation, source, and
accuracy. Exact field coordinates remain protected field settings and are
excluded from ordinary exports and public content.

Normalized append-only records are split into:

- weather observations with field ID, period, granularity, source type,
  normalized metrics, location resolution, quality, and source record ID;
- forecast snapshots with issue time, fetch time, validity window, forecast
  horizons, provider, area or grid, quality, and source record ID;
- derived metrics with field, placement, planting, calculation version, input
  references, assumptions, and quality.

The initial normalized metrics include precipitation, rain duration, sunshine,
solar radiation, ET0, temperature, humidity, wind, and later derived metrics
such as accumulated temperature, VPD, effective rainfall, soil-moisture decline
rate, and irrigation response.

## Research dataset

A deterministic research-dataset service aligns data by field timezone and
returns daily rows for a selected field, placement, planting, period, and
metric list. Rows retain nulls, quality flags, and references to their source
records. Multiple sensors measuring the same metric are not silently averaged;
the user selects the representative scope.

Initial exploratory tools include:

- aligned time-series lanes and work-event markers;
- scatter plots;
- Pearson and Spearman correlation;
- 1, 3, 7, 14, and 30-day lag comparisons;
- moving averages;
- before/after work comparisons;
- growth-stage and equipment-change segmentation;
- sample count, missingness, and outlier-candidate display.

Small samples are presented as weak evidence. Even with sufficient samples, the
UI must not label a correlation as a cause.

## Research workspace

The field page receives a separate research or reflection workspace rather than
placing dense statistics on the ordinary overview. The user selects field,
placement, planting, and period, then views weather, field environment, root
zone, work, growth, yield, and images in aligned lanes.

An analysis can be saved as a field-scoped hypothesis containing the observed
relationship, alternative explanations, selected metrics, period, analysis
snapshot, next observation, next comparison, status, author, and reviewer.
`supported` means supported under the recorded field conditions; it does not
promote the result to general agronomic knowledge.

## Delivery phases

1. **Research and visualization:** field weather locations, observation and
   forecast history, aligned datasets, exploratory analysis, exports, and saved
   hypotheses.
2. **Explained advisories:** deterministic reminders to inspect irrigation,
   spray timing, heat or frost risk, root-zone response, and fertilizer
   residual-confidence changes. Advisories identify evidence and unknowns.
3. **Approved plan changes:** show before/after work windows and apply changes
   only after approval, with forecast issue time and audit history.
4. **Limited closed loop:** only reversible work such as irrigation, under a
   separate safety specification with local measurement feedback, limits,
   approval policy, and fail-safe behavior.

## Migration

The existing `weather_records.jsonl` is not deleted. Legacy records without a
field ID remain unassigned until an administrator confirms their field and
period. Coordinate proximity alone must not assign them. Forecast records are
never converted to observations. Migration supports dry-run, a manifest,
counts, checksums, and safe retries.

## Layering

- provider-specific retrieval belongs to weather connectors;
- observations and forecasts belong to a weather repository;
- sensor time series remain in measurement repositories;
- placements, plantings, work, and outcomes remain in their owning
  repositories;
- alignment belongs to a cultivation research dataset service;
- statistics and quality assessment belong to a deterministic analysis service;
- advisories belong to a weather decision service that cannot operate devices;
- Flask routes handle validation, authorization, service calls, and responses;
- React renders the research workspace and does not duplicate statistics.

See the Japanese specification for the complete schemas, API proposal,
validation rules, privacy requirements, test plan, and Phase 1 acceptance
criteria.
