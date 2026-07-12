# Cloudflare Hosted Option Design

Japanese version:

- [jp/CLOUDFLARE_HOSTED_OPTION.md](jp/CLOUDFLARE_HOSTED_OPTION.md)

## Conclusion

The Cloudflare hosted option is feasible, but Workers should initially host only
management HTTP APIs/UI backed by Turso. Long-running MQTT, RTSP camera streams,
ffmpeg, systemd, local filesystem processing, and scheduler work remain in the
local hub.

Recommended modes:

- Default: operate through the local hub.
- Tunnel option: expose the local hub through Cloudflare Access + Tunnel.
- Cloud app option: provide a Workers + Hono + Turso hosted management API/UI.

## Goals

- Let authorized administrators access device state, MQTT events, runtime
  config, and OTA targets without entering the field LAN.
- Keep local operation intact.
- Manage allowed email addresses through scripts, not manual dashboard edits.
- Record authenticated user email in audit logs for write operations.

## Non-goals

- Hosting an MQTT broker in Workers.
- Long-running MQTT subscribe loops in Workers.
- RTSP preview or multipart camera streams in Workers.
- Timelapse generation, ffmpeg, Instagram posting, or AI caption generation in
  Workers.
- Direct Worker access to local `WORK_DIR` files.
- Direct MQTT publish from Worker to devices.

Immediate device effects should go through a Turso command queue that the local
hub polls and publishes to MQTT.

## Environment Source Of Truth

`hub/.env` is the source of truth for local setup and provisioning scripts.
Secrets must not be printed or committed.

Existing shared keys:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `S3_ENDPOINT_URL`
- `S3_BUCKET_NAME`
- `S3_BUCKET_REGION`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`

Cloudflare hosted option keys:

- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
- `CLOUDFLARE_ACCESS_POLICY_AUD`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_ACCESS_GROUP_ID`
- `CLOUDFLARE_ACCESS_APP_ID`
- `CLOUDFLARE_ACCESS_POLICY_ID`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`
- `CLOUDFLARE_ACCESS_API_TOKEN`
- `CLOUDFLARE_TUNNEL_NAME`
- `CLOUDFLARE_TUNNEL_ID`
- `CLOUDFLARE_TUNNEL_HOSTNAME`
- `CLOUDFLARE_TUNNEL_ORIGIN_URL`
- `CLOUDFLARE_TUNNEL_TOKEN_FILE`
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID`
- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_ZONE_NAME`

`CLOUDFLARE_ACCESS_API_TOKEN` is for local scripts or CI only. Do not pass it to
Workers.

## Access And Authorization

Cloudflare Access is the coarse-grained entry gate. The Access group containing
allowed email addresses is the source of truth.

Worker-side validation:

- Read `cf-access-jwt-assertion`.
- Fetch JWKS from
  `${CLOUDFLARE_ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`.
- Validate issuer and audience.
- Normalize payload email to lowercase `actor_email`.

Application roles are stored in Turso:

- `reader`: GET only.
- `operator`: device config and firmware target writes.
- `admin`: future user and destructive operation management.

## Provisioning Scripts

Primary scripts:

```bash
python3 scripts/cloudflare_access_setup.py provision --write-env
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
python3 scripts/cloudflare_access_setup.py apply allowed_emails.txt --yes
```

Tunnel setup and startup:

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
bash scripts/cloudflare_tunnel_start.sh
```

Behavior requirements:

- `add` and `remove` are idempotent.
- `apply` treats the file as the allowlist source of truth.
- Group JSON backups are stored under
  `hub/.data/cloudflare-access-backups/`.
- Resource IDs in `.env` are reused.
- Existing resources found by exact name/hostname are reused only when a single
  safe match exists.
- Duplicate resources, conflicting DNS records, or locally-managed tunnels stop
  the script instead of being overwritten.
- Tunnel tokens are stored with `0600` permissions and are never printed.

## Required Cloudflare Permissions

The provisioning token needs:

- Account read.
- Access groups read/write.
- Access applications and policies read/write.
- Cloudflare Tunnel edit.
- Zone DNS read/write for the target hostname.

Account-owned tokens are acceptable. Verify behavior through the setup script
instead of relying only on `/user/tokens/verify`.

## Tunnel Assumptions

- The Tunnel connector runs on the device-side host that can reach the local
  hub.
- `CLOUDFLARE_TUNNEL_ORIGIN_URL` defaults to `http://localhost:39151`.
- The Tunnel hostname is for UI/API access, not current OTA firmware downloads.
- Current firmware downloads use `http://` URLs generated from
  `FIRMWARE_BASE_URL` / `FIRMWARE_HOSTNAME` / host name values.

## Turso And Hosted API Direction

Move hosted shared state toward Turso:

- `device_records`
- `device_configs`
- `firmware_artifacts`
- `firmware_targets`
- `device_commands`
- `audit_logs`

Hosted API prefix is `/api`. Existing local hub APIs under `/local/api` remain
local-only.

Workers do not directly publish MQTT. For push operations, Workers write a
command row and the local hub polls and publishes it.

## Implementation Phases

1. Confirm design and initial API scope.
2. Add `hub/cloudflare` Worker app, Hono, Turso client, Access JWT middleware,
   and tests.
3. Provision Access group, Access app, policy, Tunnel, token, and DNS
   idempotently from `.env`.
4. Add read APIs for device events and records.
5. Move config and OTA target metadata to Turso.
6. Add write APIs, command queue polling, and audit logs.
7. Add hosted UI screens.
8. Add session revoke operations.

## Test Policy

- Worker unit tests for JWT validation, role checks, input validation, and audit
  logs.
- Script tests for idempotent add/remove/apply and invalid email handling.
- Python hub tests for command polling and repository backend behavior.
- Manual smoke tests for allowed email login, removed email rejection after
  session expiration/revoke, and runtime config propagation.
