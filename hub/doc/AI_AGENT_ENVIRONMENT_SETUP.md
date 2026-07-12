# AI Agent Environment Setup Guide

Japanese version:

- [jp/AI_AGENT_ENVIRONMENT_SETUP.md](jp/AI_AGENT_ENVIRONMENT_SETUP.md)

This guide tells an AI agent how to set up or verify the INAS hub environment.
Treat `.env` as the source of truth and never print secrets.

## Rules For Agents

- Read `.env` values, but do not echo secret values.
- Do not invent Cloudflare IDs, hostnames, or account values.
- Use idempotent scripts for Cloudflare resources.
- Reuse existing resource IDs from `.env` when present.
- Stop on ambiguous Cloudflare resources instead of overwriting.
- Do not start the Cloudflare Tunnel on a development PC unless that PC is the
  intended device-side origin.
- Keep local hub behavior working even when Cloudflare setup is incomplete.

## Local Hub Setup

```bash
cd hub
rye sync
cp .default.env .env
rye run db:create
rye run serve
```

Default local URL:

```text
http://localhost:39151
```

## Admin Demo UI

Use the demo when real MQTT/device data is unavailable:

```bash
python scripts/run_admin_demo_server.py
```

Open:

```text
http://127.0.0.1:39251/demo/mqtt-devices
```

## Cloudflare Tunnel Option

Required `.env` values include:

- `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME`
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_ACCESS_API_TOKEN`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`

Optional or generated values:

- `CLOUDFLARE_ACCESS_POLICY_AUD`
- `CLOUDFLARE_ACCESS_GROUP_ID`
- `CLOUDFLARE_ACCESS_APP_ID`
- `CLOUDFLARE_ACCESS_POLICY_ID`
- `CLOUDFLARE_TUNNEL_ID`
- `CLOUDFLARE_TUNNEL_TOKEN_FILE`
- `CLOUDFLARE_TUNNEL_DNS_RECORD_ID`
- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_ZONE_NAME`

Provision resources:

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
```

Start local hub and tunnel together:

```bash
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

Manage allowed emails:

```bash
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
```

Tunnel daemon helper:

```bash
bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start
bash scripts/cloudflare_tunnel_daemon.sh status
```

## Cloud App Option

```bash
cd hub/cloudflare
npm install
npm test
npm run typecheck
```

The Cloud app uses Workers + Hono + Turso. It does not replace local MQTT,
camera, scheduler, or local filesystem features.

## Verification Checklist

- `rye run serve` starts the local hub.
- Admin UI is reachable on `http://localhost:39151`.
- Demo UI works without MQTT.
- Cloudflare provisioning reuses existing IDs from `.env`.
- Cloudflare setup stops on ambiguous resources.
- Allowed email add/remove is idempotent.
- Tunnel status is checked on the device-side origin.
- Secrets are not printed in logs or final reports.
