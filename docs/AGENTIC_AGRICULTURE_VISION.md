# INAS Agentic Agriculture Vision

Japanese version: [jp/AGENTIC_AGRICULTURE_VISION.md](jp/AGENTIC_AGRICULTURE_VISION.md)

## Purpose

This document records the long-term product philosophy behind agentic agriculture in INAS. It is a decision framework for future sensors, tools, AI features, and user experiences rather than an API specification.

In one sentence:

> Build an open cultivation foundation that observes a field, explains its reasoning, safely assigns work to people and machines, verifies the outcome, and keeps learning—rather than a machine that farms without the grower's agency.

## Why Agentic Agriculture

Agriculture is not a timer-controlled sequence of equipment switches. Weather, soil, substrate, cultivar, growth stage, past work, and available equipment continually change the appropriate next action. A useful system must observe, assess, propose, execute, verify, and learn.

INAS does not assume that an existing farm should be rebuilt around rails or one universal robot. A rail system may be an excellent executor where it fits, but it is one option among people, fixed pumps and valves, cameras, external services, mobile equipment, and future robots. The Hub composes the executors available at each field.

## Principles

1. **Improve decisions before automating motion.** Guidance about timing, reasons, methods, stop conditions, and completion is valuable even when a person performs the work.
2. **Verify outcomes, not only commands.** “Pump ran for 30 seconds” is not proof that water reached the root zone. Record expected effects and confirm them when possible.
3. **Treat people as first-class executors.** People remain the best executor for complex and irreversible work. The system should reduce cognitive and recording burden, not use people as undocumented exception handlers.
4. **Expand autonomy per task and field.** Irrigation may be autonomous while fertilization requires approval and pruning remains guided. This mixed state is intentional.
5. **Separate capability from reach.** A device definition states what a device can do; installation data states where it can act. Both must match before assignment.
6. **Respect existing farms and incremental adoption.** A useful system can start with records, then add one sensor, actuator, or camera without discarding previous investments.
7. **Make the beginner path simple and the expert path deep.** Show agricultural purpose before terminals, protocols, identifiers, thresholds, and prompt details. Put necessary complexity behind advanced settings.
8. **Show evidence and uncertainty together.** General references are starting points. Product labels, local standards, laboratory analysis, field history, and current observations take priority.
9. **Enforce safety structurally, outside the model.** Limits, intervals, timeouts, physical stops, idempotency, acknowledgement, completion checks, and audit history must not depend on an LLM behaving correctly.
10. **Keep the system open, repairable, and user-owned.** Users should be able to build hardware, buy supported assemblies, export data, replace components, and understand decisions without vendor lock-in.

## Common Work Loop

Every cultivation task should move toward the same loop:

1. Observe current state and history.
2. Assess objectives, timing, start/skip/stop conditions, and safety policy.
3. Propose an action with evidence, expected effect, risk, and time window.
4. Obtain approval according to the task's autonomy level.
5. Assign an executor that has both the required capability and physical reach.
6. Execute with bounded, traceable state transitions.
7. Verify that the expected result occurred.
8. Feed the result into the next timing, quantity, method, and executor choice.

Generated prose alone does not complete this loop. Action state, approval, capabilities, target bindings, execution results, and verification evidence must be structured and auditable.

## Maturity Levels

| Level | Hub responsibility | Human and machine responsibility |
|---|---|---|
| L0 Record | Store work and observations | A person decides and acts |
| L1 Guide | Explain timing, method, stop, and completion conditions | A person decides and acts |
| L2 Propose | Build evidence-backed candidates from field data | A person accepts, changes, or rejects |
| L3 Approved execution | Send bounded work to a physically linked executor and record the result | A person approves and handles exceptions |
| L4 Conditional autonomy | Decide, execute, and verify defined tasks in a bounded context | A person manages policy and exceptions |
| L5 Cooperative cultivation | Coordinate multiple people, devices, and seasonal tasks | A person owns goals, quality, business, and ethics |

Maturity belongs to each task, field, and installation—not to the product as one global “automatic” switch.

## What INAS Will Not Do

- Send free-form LLM output directly to an actuator.
- Present general references as field-specific facts when evidence is missing.
- Hide physical risk or human recovery work behind a “fully automatic” claim.
- Create crop-specific devices when reusable capabilities and Hub policy are sufficient.
- Expose internal electrical and protocol choices as mandatory beginner settings.
- Reject rails or robots; they remain optional executors rather than universal prerequisites.

## Measures of Success

Success is not only unattended runtime or command count. INAS should help growers notice necessary work, understand why it matters, reduce missed and duplicate tasks, avoid excessive water and fertilizer, stop safely during faults, preserve evidence for diagnosis, improve resource use without sacrificing yield or quality, and expand from a small installation without discarding data or equipment.

## Related Documents

- [Cultivation System Orchestration](CULTIVATION_SYSTEM_ORCHESTRATION.md)
- [Device Definition Specification](DEVICE_DEFINITION_SPECIFICATION.md)
- [Architecture Layering Policy](ARCHITECTURE_LAYERING_POLICY.md)
- [Hub Agentic Farm Operations Policy](../hub/doc/jp/HUB_AGENTIC_FARM_OPERATIONS_POLICY.md) (Japanese)
