# Hub Admin UI UX Implementation Plan

Japanese version:

- [jp/HUB_ADMIN_UX_IMPLEMENTATION.md](jp/HUB_ADMIN_UX_IMPLEMENTATION.md)

## Purpose

`/mqtt-devices` has broad management functionality, but the original screen put
raw JSON, variable names, and API-oriented forms too close to the first view.
The admin UI should behave like an operational panel for growers.

For WTR/WRS devices, the first screen must quickly answer:

- When irrigation ran.
- How much irrigation ran.
- Current soil moisture and thresholds.
- Last communication time and next wake time.
- Scheduled irrigation times.
- Whether OTA is needed, pending, or in progress.

## UX Principles

- Use grower-facing terms in primary views.
- Parse JSON into cards, lists, and histories before showing raw payloads.
- Move raw JSON and technical maintenance actions into detail or maintenance
  sections.
- Keep existing API routes and JavaScript behavior stable.
- Use color only to support state recognition: normal, warning, stopped, or
  maintenance.

## Information Architecture

Device list:

- Show summary cards rather than mixing list and detail in one screen.
- Prefer device display name, then device id.
- Show kind, operational state, last communication, irrigation state, soil
  moisture, next wake, current firmware, and target firmware.
- Open `/mqtt-devices/<device_id>` when a card is selected.

WTR detail:

- Show summary cards first: irrigation state, soil moisture, next wake, and last
  communication.
- Show Plotly time-series charts for irrigation and soil moisture.
- Supported ranges: last 3 days, 2 weeks, 1 month, all time, and custom.
- Keep configuration, OTA, raw status, and MQTT maintenance under detail
  sections.

## Data Handling

- Device status and telemetry are parsed before display.
- Measurement charts use normalized `sensor_measurements` where available.
- Raw payloads remain accessible for maintenance, but are not the primary UI.

## Test Policy

- Keep existing basic UI and OTA tests passing.
- Add focused tests when route output, visible labels, or OTA upload behavior
  changes.
- Demo data should allow UI/UX review without real MQTT devices.
