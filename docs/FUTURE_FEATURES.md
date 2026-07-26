# INAS Future Feature Registry

Japanese detailed registry:
[jp/FUTURE_FEATURES.md](jp/FUTURE_FEATURES.md)

## Purpose

This is the visible index of product ideas that have been discussed but are not
fully released. Detailed specifications stay in the documentation tree owned by
the relevant layer; this file records a stable ID, current maturity, and a link
to the governing design.

The registry is product memory, not a release promise or sprint backlog.
Released items move to the history section instead of silently disappearing.

## Status vocabulary

- `concept`: a problem and intended outcome are recorded, but no complete design
  exists;
- `specified`: a reviewable design exists, but the intended feature is not fully
  implemented;
- `partial`: useful foundations exist, while the listed outcome remains
  incomplete;
- `gated`: implementation requires explicit security, safety, legal, or
  operational prerequisites;
- `implementing`: an implementation change is actively tracked;
- `released`: the acceptance conditions are available to users and have been
  verified.

## Current registry

| ID | Future outcome | Status | Governing document |
|---|---|---|---|
| FUT-001 | Per-emitter drip calibration, explainable irrigation proposals, and drain-EC-guided substrate reset | specified | [detailed specification](../hub/doc/HUB_DRIP_IRRIGATION_CALIBRATION_AND_SUBSTRATE_RESET_SPEC.md) |
| FUT-002 | Evidence-backed fertilizer catalog, test records, residual-effect confidence, and material suggestions | specified | [fertilization policy](../hub/doc/jp/HUB_FERTILIZATION_RECOMMENDATION_POLICY.md) |
| FUT-003 | One field TODO list combining calendar work, sensor/image/weather decisions, maintenance, and user-created work | partial | [improvement loop](../hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md) |
| FUT-004 | Public crop knowledge, image observations, and weather/accumulated-temperature adjustments with source and applicability metadata | concept | [plant calendar specification](../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |
| FUT-005 | Authoritative pesticide registration lookup through a permissioned provider adapter | gated | [plant calendar specification](../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |
| FUT-006 | Grower-facing FGT recipe editing, approval, execution, and history UI | specified | [system specification](SYSTEM_SPECIFICATION.md) and [FGT requirements](../client-devices/fertigation-device/docs/requirements.md) |
| FUT-007 | Mist/spray proposals and later execution through a device with explicit safety capabilities | concept | [improvement loop](../hub/doc/jp/AGRI_IMPROVEMENT_LOOP.md) |
| FUT-101 | Field-scoped teams, invitations, roles, assignment, review, and handoff | specified | [work verification design](../hub/doc/jp/WORK_VERIFICATION_AND_COMPENSATION_DESIGN.md) |
| FUT-102 | Append-only compensation ledger separated from work completion and payment execution | gated | [work verification design](../hub/doc/jp/WORK_VERIFICATION_AND_COMPENSATION_DESIGN.md) |
| FUT-103 | Moderated community proposal intake and this public feature registry | specified | [Japanese community process](jp/FUTURE_FEATURES.md#community-proposal-process) |
| FUT-104 | Reviewed sharing of crop-plan corrections, fertilizer entries, calibration examples, and field learnings across users | gated | [fertilization policy](../hub/doc/jp/HUB_FERTILIZATION_RECOMMENDATION_POLICY.md) and [plant calendar specification](../hub/doc/jp/HUB_PLANT_MANAGEMENT_CALENDAR_SPEC.md) |
| FUT-201 | Human approval through Discord for sensitive Operations API requests | specified | [Discord approval policy](../hub/doc/jp/HUB_OPERATIONS_DISCORD_APPROVAL_POLICY.md) |
| FUT-202 | Paginated maintenance search for devices, assignments, and replacement state outside the grower home page | specified | [field resource hierarchy](../hub/doc/jp/HUB_FIELD_RESOURCE_HIERARCHY_SPEC.md) |
| FUT-203 | Shared-state migration and concurrency control for multiple Hub nodes | gated | [user settings and concurrent editing](../hub/doc/jp/HUB_USER_SETTINGS_AND_CONCURRENT_EDITING.md) |
| FUT-204 | Parent-Hub and Cloud Hub synchronization of device state and commands through Sync v1, with complete remote config and firmware operations still in progress | partial | [Cloud Hub](../hub-cloud/README.md) and [hierarchical sync](../hub/doc/jp/HIERARCHICAL_SYNC.md) |
| FUT-301 | Hub Extension settings contributions and named standalone-page slots | gated | [Extension specification](EXTENSION_SPECIFICATION.md) |
| FUT-302 | Signed, permissioned, isolated executable Extensions with revocation | gated | [Extension security review policy](EXTENSION_SECURITY_REVIEW_POLICY.md) |
| FUT-401 | Closed-loop irrigation adjusted from sensors, weather, verified delivery, and outcome history | specified | [agentic farm operations policy](../hub/doc/jp/HUB_AGENTIC_FARM_OPERATIONS_POLICY.md) |
| FUT-402 | Capability-based assignment of planting, pruning, and harvesting work to people, fixed equipment, and future robots | concept | [agentic agriculture vision](AGENTIC_AGRICULTURE_VISION.md) |

## Community principles

Community interest helps discovery and prioritization, but never overrides
device safety, agronomic evidence, privacy, security review, legal constraints,
or maintainer responsibility. A proposal may become:

- a core reusable mechanism;
- device firmware or a Device Definition change;
- a declarative Extension;
- reviewed crop/reference data;
- documentation or an operating practice; or
- an archived or declined proposal with a recorded reason.

Extension submissions remain subject to deterministic validation, explicit
administrator installation, and the
[Extension security review policy](EXTENSION_SECURITY_REVIEW_POLICY.md).
Community proposals do not grant database, device-control, network, filesystem,
or secret access.

## Maintenance

Each new item receives a stable `FUT-nnn` ID. Updates should preserve the
original problem, record duplicate and superseding relationships, link the
detailed design or issue, and update `last_reviewed_at`. Public attribution is
opt-in; personal information, farm coordinates, credentials, device IDs, and
private photos are excluded by default.
