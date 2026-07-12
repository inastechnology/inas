# Cloudflare Cloud App Implementation Plan

Japanese version:

- [jp/CLOUDFLARE_CLOUD_APP_IMPLEMENTATION.md](jp/CLOUDFLARE_CLOUD_APP_IMPLEMENTATION.md)

## Positioning

The Cloud app is the Cloudflare Workers + Hono + Turso management API/UI
foundation. It is separate from the Tunnel option. A Tunnel exposes the
device-side local hub; a Worker runs hosted HTTP APIs and a future hosted UI.

The Cloud app does not move every local hub feature to Workers.

## Initial Scope

Included:

- Cloudflare Access JWT validation.
- Role checks through Turso `admin_users`.
- Device event list/read APIs.
- Management event creation.
- Audit log writes.
- Turso schema migration foundation.
- Tests for authentication, authorization, validation, and audit behavior.

Excluded initially:

- MQTT broker hosting.
- Long-running MQTT subscribe/publish loops.
- RTSP camera access.
- ffmpeg and timelapse generation.
- Instagram posting.
- Direct access to local `WORK_DIR` files.
- Direct MQTT publish from Worker to devices.

Device-side immediate effects should be implemented through a Turso command
queue polled by the local hub.

## Architecture

```text
Browser / Admin client
  -> Cloudflare Access
  -> Cloudflare Worker (Hono)
  -> Turso/libSQL
  <- local hub sync / polling
  -> MQTT broker / devices
```

## Repository Layout

```text
hub/cloudflare/
  package.json
  wrangler.jsonc
  tsconfig.json
  vitest.config.ts
  migrations/
    0001_cloud_control_plane.sql
  src/
    index.ts
    access.ts
    db.ts
    routes/
      events.ts
      health.ts
    repositories/
      admin-users.ts
      audit-logs.ts
      device-events.ts
  test/
    access.test.ts
    app.test.ts
    db.test.ts
```

## Authentication And Authorization

Cloudflare Access is the entry source of truth. The Worker also validates
`Cf-Access-Jwt-Assertion` and checks issuer, audience, and email.

Required Worker env:

- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
- `CLOUDFLARE_ACCESS_POLICY_AUD`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

Do not pass `CLOUDFLARE_ACCESS_API_TOKEN` to Workers. It is only for provisioning
scripts.

Roles:

- `reader`: read only.
- `operator`: normal write operations.
- `admin`: future user and destructive operation management.

## URL Separation

Do not use the same hostname for Tunnel and Worker custom domains.

Recommended:

- Tunnel local hub: `hub.example.com`
- Worker cloud app: `hub-cloud.example.com`

## Development

```bash
cd hub/cloudflare
npm install
npm test
npm run typecheck
```

Local dev:

```bash
cd hub/cloudflare
npm run dev
```

Before production deploy, apply Turso migrations and configure Worker
environment variables and secrets.

## Test Policy

- `/api/health` works without Access JWT.
- `/api/me` returns `401` without JWT.
- Valid JWT but missing `admin_users` entry returns `403`.
- `reader` can read events.
- `reader` cannot create events.
- `operator` can create events and audit logs are written.
- Access issuer and payload normalization are unit tested.

## Next Steps

1. Automate Worker deploy from `.env`.
2. Add `admin_users` management CLI.
3. Add device status, config, and firmware target APIs.
4. Add local hub command queue polling.
5. Add hosted management UI.
6. Add Access session revoke operations.
