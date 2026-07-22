---
name: manage-hub-operations
description: Operate the INA Hub through its Cloudflare Access-protected Operations API. Use when Codex needs to inspect registered Hub devices, publish or verify firmware artifacts, preview or apply OTA firmware targets, check Operations API authentication, or add reusable Operations API clients for device, field, or farm-work domains. Also use for requests such as registering WTR firmware, marking devices for next-boot updates, querying remote Hub state, or automating Hub administration without browser login.
---

# Manage Hub Operations

Use the Service Token-protected Operations API for remote Hub administration. Prefer the repository's deterministic clients over ad hoc HTTP commands.

## Establish context

1. Resolve the INA repository root with `git rev-parse --show-toplevel`.
2. Read `hub/scripts/operations/README.md`.
3. Read [references/api.md](references/api.md) only for the domain and endpoint needed.
4. Use `~/.config/inas/operations-api.env` unless the user provides another env file.
5. Never print, log, commit, or paste `CF_ACCESS_CLIENT_SECRET`. When checking configuration, show variable names only with values redacted.

Required client settings:

- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`
- `INAS_HUB_OPERATIONS_URL`, including `/operations/api/v1`

## Choose the domain

- Device registration, runtime config, firmware, and OTA: use `hub/scripts/operations/devices/`.
- Fields, sections, and installation layouts: use `hub/scripts/operations/fields/`.
- Work plans, work results, and cultivation records: use `hub/scripts/operations/work/`.
- Authentication and HTTP behavior: use `hub/scripts/operations/common/`.

Do not call a browser-oriented `/local/api/*` endpoint through the public hostname to bypass a missing Operations endpoint. If the requested domain endpoint is absent, implement it under `/operations/api/v1/<domain>/`, add tests and a domain client, then require deployment before live verification.

## Inspect before mutating

1. Call the authenticated health endpoint.
2. Read the exact remote resources in scope.
3. Report the resolved device IDs, kinds, states, current versions, and current targets without exposing secrets.
4. Exclude retired resources unless the user explicitly requests an investigation; never mutate retired devices.

Treat an explicit user request to upload firmware and schedule registered devices as authorization for artifact publication and target assignment. Do not infer authorization for disabling, retiring, deleting, or broadening the target set.

## Publish firmware and schedule OTA

Use the checked-in client:

```bash
hub/.venv/bin/python hub/scripts/operations/devices/publish_firmware.py \
  path/to/firmware.bin \
  --device-kind WTR \
  --version 0.0.4 \
  --device-id DEVICE_ID
```

The default publishes the artifact and performs a rollout dry-run. Add `--apply` only when the user authorized update scheduling:

```bash
hub/.venv/bin/python hub/scripts/operations/devices/publish_firmware.py \
  path/to/firmware.bin \
  --device-kind WTR \
  --version 0.0.4 \
  --device-id DEVICE_ID \
  --apply
```

Before applying:

1. Build the firmware successfully.
2. Confirm the embedded manifest kind and version through the Hub response.
3. Confirm local and remote SHA-256 values match.
4. Review the dry-run candidates and skipped resources.
5. Keep explicit `--device-id` filters when the user named or implied a bounded set.

After applying, query the device again and confirm `target_firmware_version`. Distinguish a scheduled target from a completed OTA: completion requires a later device status showing the new `firmware_version` and a successful OTA state.

## Implement new Operations capabilities

Keep Flask routes thin and delegate to existing Hub services or repositories. Add the endpoint to `hub/src/ina_device_hub/operations_api.py`, place its client under the matching domain directory, and update [references/api.md](references/api.md).

Preserve these invariants:

- Service Token JWT authentication and `HUB_OPERATIONS_SERVICE_IDS` allowlisting.
- No browser same-origin requirement for Operations API calls.
- Explicit dry-run for bulk mutations.
- Idempotent repeated calls where practical.
- Audit events for mutations, including actor and resolved resource IDs.
- Validation of device kind, version, artifact state, resource state, and request shape.
- No secrets in source, fixtures, command output, or audit payloads.

Run focused tests, the full Hub test suite for API changes, and Ruff. After deployment, forward-test health, a scoped read, dry-run, apply when authorized, and a verification read.
