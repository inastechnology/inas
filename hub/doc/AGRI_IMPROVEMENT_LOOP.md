# Crop Context And Agricultural Improvement Loop

Japanese version:

- [jp/AGRI_IMPROVEMENT_LOOP.md](jp/AGRI_IMPROVEMENT_LOOP.md)

## Purpose

The hub should not be only a device management screen. It should connect crop
context, field conditions, sensor data, images, work logs, and human evaluation
so that observations can become better agricultural actions.

Current executable action:

- WTR/WRS irrigation.

Future candidate actions:

- Liquid fertilizer.
- Misting or humidity control.
- Image-assisted crop state evaluation.
- External research data references.

## Field Data Model

Field data is stored under `WORK_DIR/.fields.json`. Legacy `crop` and `stage`
fields remain for compatibility, while detailed data is normalized into:

- `crop_profile`: crop name, cultivar, growth stage, sowing date, transplant
  date, target harvest date.
- `growth_targets`: target ranges for soil moisture, EC, pH, humidity, and
  light.
- `cultivation_context`: cultivation method, soil/media, house information,
  mulch, irrigation method, water source, area, plant count, notes.
- `control_policy`: objective, automation level, allowed actions, irrigation
  limits, safety notes.
- `knowledge_context`: research topics, reference URLs, image observation
  points, knowledge notes.
- `areas`: sections, beds, ridges, zones, or measurement points.
- `device_placements`: links devices to field, section, ridge/bed, or point.
- `action_plans`: proposed, approved, executed, and evaluated actions.

## Field Units

- `field`: whole field. Good for ENV, wide cameras, and broad weather context.
- `section`: area with different crop or cultivation conditions.
- `ridge` / `bed`: useful for soil moisture and irrigation target mapping.
- `point`: specific measurement point.

One ENV device can represent a small field. Split into smaller units only when
field size, crop differences, sunlight, or drainage makes it necessary.

## Improvement Loop

1. Observe: collect WTR/WRS/SOI/ENV measurements, wake history, images, weather, and
   work events.
2. Align context: record crop, cultivar, growth stage, cultivation method, soil
   or media, and plant count.
3. Interpret gaps: compare latest values with target ranges.
4. Record action candidates: keep expected effect, risk, target, and context.
5. Execute and evaluate: store work result and human evaluation.
6. Feed back: adjust target ranges, timing, or control policy.

## Automation Levels

- `observe_only`: observe and record only.
- `suggest_only`: show and record candidates; no execution.
- `manual_approval`: execute only after human approval.
- `auto`: execute when safety conditions pass. Use with irrigation limits and
  minimum intervals.

## External Information

The hub currently records weather information. Future external context can
include crop research data, pest/disease warnings, leaf color or wilt
observation from images, and field-specific historical patterns.

External information is not a direct command. Store source, assumptions,
confidence, and human review before using it for automation.
