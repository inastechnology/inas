# Operations API reference

Base URL: `${INAS_HUB_OPERATIONS_URL}`. Cloudflare Access clients send `CF-Access-Client-Id` and `CF-Access-Client-Secret`; the origin validates the resulting Access JWT and its allowlisted `common_name`.

## Security alerts

The Hub sends a Discord alert when an Operations request reaches the origin but fails Hub authentication, including a missing or invalid Access JWT or a `common_name` outside `HUB_OPERATIONS_SERVICE_IDS`. Alerts include only method, path without query, connecting IP, Cloudflare Ray ID, User-Agent, and rejection reason. They never include JWTs, Client IDs, Client Secrets, request bodies, or query strings. Identical fingerprints are suppressed for `DISCORD_SECURITY_ALERT_COOLDOWN_SECONDS`, default 300 seconds.

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

No Operations endpoints are implemented yet. Add endpoints under `/operations/api/v1/fields/`; do not expose the public client to `/local/api/fields` as a workaround.

## Work

No Operations endpoints are implemented yet. Add endpoints under `/operations/api/v1/work/`; do not expose the public client to local field-event or record APIs as a workaround.
