# Operations API reference

Base URL: `${INAS_HUB_OPERATIONS_URL}`. Cloudflare Access clients send `CF-Access-Client-Id` and `CF-Access-Client-Secret`; the origin validates the resulting Access JWT and its allowlisted `common_name`.

## Security alerts

The Hub sends a Discord alert when an Operations request reaches the origin but fails Hub authentication, including a missing/invalid JWT, a `common_name` in neither the legacy device allowlist nor the collector grants, malformed grants, or overlapping reader/writer identities. Alerts include only method, path without query, connecting IP, Cloudflare Ray ID, User-Agent, and rejection reason. They never include JWTs, Client IDs, Client Secrets, request bodies, or query strings. Identical fingerprints are suppressed for `DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS`, default 300 seconds. Authenticated scope/field denials return 403; they are not authentication-alert events.

Invalid Client ID or Client Secret requests rejected by Cloudflare before origin delivery are not visible to the Hub. Monitor those with Cloudflare Access authentication logs or Logpush; do not claim that the Hub Discord alert covers them.

## Common

### `GET /health`

Returns `status`, `actor`, and `api_version`. Use before other operations.

## Devices

### `GET /devices`

Optional query parameters:

- `device_kind`: three-character kind such as `WTR`
- repeated `state`: state filter such as `active`

Returns `items` keyed by device ID and `count`. History arrays are omitted.

### `POST /devices/firmware-artifacts/<device_kind>/<version>`

Send the raw `firmware.bin` with `Content-Type: application/octet-stream`. The Hub validates the embedded manifest against the URL, calculates SHA-256, stores the binary in the Hub firmware directory, and returns artifact metadata.

Repeated publication of identical version content is safe and retains the original creation time. A different binary at the same kind and version replaces that artifact; therefore use a new version for changed firmware.

### `POST /devices/firmware-rollouts`

Request:

```json
{
  "device_kind": "WTR",
  "version": "0.0.4",
  "device_ids": ["DEVICE_ID"],
  "dry_run": true
}
```

`device_ids` is optional. Omission targets every non-retired device of the kind, so prefer explicit IDs unless the user clearly requested all registered devices. `dry_run` defaults to true. The response contains `candidate_device_ids`, `updated`, and `skipped`.

The artifact must exist and have `rollout_state=active`. Applying sets `target_firmware_version`; it does not prove that the device has downloaded or booted the firmware.

## Fields

Read-only endpoints are implemented. Use `hub/scripts/operations/fields/read_client.py`
or the stdio MCP in `hub/scripts/operations/mcp_server/`. Do not call browser APIs.

`HUB_OPERATIONS_READ_GRANTS` is a JSON object keyed by verified Service Token
`common_name`, for example:

```json
{"collector.access":{"scopes":["records:read","images:read"],"field_ids":["field-1"]}}
```

This grants access separately from `HUB_OPERATIONS_SERVICE_IDS` (legacy
device/OTA operations). An identity in both is rejected; removing a collector
grant revokes access. Legacy services gain no field/image access implicitly.
Malformed configuration rejects Operations authentication. `field_ids: ["*"]`
explicitly allows every field. Readers cannot call device endpoints or mutate.

Human administrators may also issue scoped collectors through the dedicated
settings GUI. Managed grants live in `WORK_DIR/operations_collectors.json`, not
general editable runtime settings. They are read on each request, have explicit
expiry, and deny pending/revoked identities before any legacy fallback. An ID in
both managed grants and host grants is rejected. Secrets are returned only at
issuance and never persisted. Machine callers cannot access the management GUI
or its browser API. See [GUI setup](../../../../hub/doc/jp/MCP_USAGE.md#gui-で接続と権限を管理する).

| Method/path relative to the base URL | Required scope |
|---|---|
| `GET /fields` | Either read scope; returns only allowed field summaries |
| `GET /fields/<field_id>/records` | `records:read` |
| `GET /fields/<field_id>/cameras` | `images:read` |
| `GET /fields/<field_id>/cameras/<camera_id>/images` | `images:read` |
| `GET /fields/<field_id>/cameras/<camera_id>/images/<image_id>` | `images:read` |
| `GET /fields/<field_id>/record-images/<attachment_id>` | `images:read` |

Lists accept `limit` (1–100, default 50) and `cursor`; responses contain `items`,
`count`, `has_more`, `next_cursor`. Continue with unchanged filters. Records
accept `q`, `source` (`note` or `event`), occurrence `date_from`/`date_to`, and
inclusive creation `since` (ISO 8601 with timezone). Records sort oldest-first by
creation timestamp, source, and ID. Deduplicate `(field_id, source, id)` when
repeating collection from the previous creation timestamp, including ties.
Camera image lists accept inclusive `date_from`/`date_to`, sort oldest-first,
and identify timestamps as `time_basis=hub_local` (existing timezone-less filenames).

Image endpoints return JPEG/PNG/WebP bytes, at most 10 MiB. Attachment IDs are
resolved only inside the selected field's notes/events and its storage-key
namespace. Cameras must currently belong to the field; populated layout bindings
supersede legacy camera assignments. No live capture occurs. Metadata excludes
storage keys, filesystem paths, camera credentials, and browser URLs. Responses
use `Cache-Control: private, no-store`.

There is no archive, edit/deletion change feed, or tombstone stream. Existing
retention is 1,000 notes and 1,000 events per field. Reconcile snapshots as needed.
Read the MCP README for separate collector credentials and setup.

## Work

No Operations endpoints are implemented yet. Add endpoints under `/operations/api/v1/work/`; do not expose the public client to local field-event or record APIs as a workaround.
