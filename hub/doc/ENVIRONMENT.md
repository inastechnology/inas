# Environment Variables

Japanese version:

- [jp/ENVIRONMENT.md](jp/ENVIRONMENT.md)

This document summarizes important environment variables for the hub. The
complete source of truth is `src/ina_device_hub/setting.py` and the local
`.env` file.

Do not commit real secrets. Do not print `.env` secret values in logs.

## Core

| Variable | Purpose |
|---|---|
| `WORK_DIR` | Runtime work directory. Stores local JSON, firmware artifacts, and state files |
| `LOCAL_STORAGE_BASE_DIR` | Local storage path for media and generated outputs |
| `HUB_HTTP_PORT` | Local hub HTTP port. Default is `39151` |

For an Internet-reachable production Hub, use `HUB_AUTH_MODE=cloudflare_access`.
`CLOUDFLARE_ACCESS_TEAM_DOMAIN` must be the exact HTTPS
`*.cloudflareaccess.com` team origin, and
`CLOUDFLARE_ACCESS_POLICY_AUD` must be the protected application's audience.
The Hub verifies the JWT signature, issuer, audience, application-token type,
subject, and `nbf`/`iat`/`exp` lifetime. Do not configure an Access Bypass
policy for Hub application or management paths.

## MQTT

| Variable | Purpose |
|---|---|
| `MQTT_BROKER_URL` | MQTT broker host |
| `MQTT_BROKER_PORT` | MQTT broker port |
| `MQTT_BROKER_USERNAME` | MQTT username |
| `MQTT_BROKER_PASSWORD` | MQTT password |

## Hierarchical Parent Sync

Leave `HUB_SYNC_PARENT_BASE_URL` empty for a standalone Local Hub.

| Variable | Purpose |
|---|---|
| `HUB_SYNC_PARENT_BASE_URL` | Upstream Local Hub base URL. HTTPS is required outside explicit loopback development |
| `HUB_SYNC_PARENT_TOKEN_FILE` | Absolute path to the mode-`0600` node bearer-token file |
| `HUB_SYNC_PARENT_CA_FILE` | Optional absolute path to a custom TLS CA bundle |
| `HUB_SYNC_PARENT_CLIENT_CERT_FILE` | Optional absolute path to an additional mTLS client certificate; it does not replace the node bearer token |
| `HUB_SYNC_PARENT_CLIENT_KEY_FILE` | Optional absolute path to its mode-`0600` private key; configure together with the certificate |
| `HUB_SYNC_PARENT_TIMEOUT_SECONDS` | Connect/exchange timeout from 1 to 25 seconds. Default is `20` |
| `HUB_SYNC_PARENT_ALLOW_INSECURE_LOOPBACK` | Development-only HTTP opt-in for `localhost`, `127.0.0.1`, or `::1` |

Do not put credentials in the parent URL or directly in `.env`. The bearer and
private-key paths must be regular, non-symlink files unreadable by group/other;
the bearer must have the canonical `inas_sync_v1_` token shape. A configured
parent does not affect local MQTT readiness. Parent-bound event emission starts
only after the first valid authenticated exchange succeeds.

## Turso

| Variable | Purpose |
|---|---|
| `TURSO_DATABASE_URL` | This Local Hub installation's Turso/libSQL database URL |
| `TURSO_AUTH_TOKEN` | This Local Hub installation's Turso auth token |
| `TURSO_SYNC_INTERVAL` | Local replica sync interval in seconds |

These credentials remain owned by this Local Hub. They are unrelated to the
Cloud Hub directory/customer databases and must not be copied to an Edge
Gateway.

## S3-Compatible Storage

| Variable | Purpose |
|---|---|
| `S3_ENDPOINT_URL` | S3 endpoint |
| `S3_BUCKET_NAME` | Bucket name |
| `S3_BUCKET_REGION` | Bucket region |
| `S3_ACCESS_KEY` | Access key |
| `S3_SECRET_KEY` | Secret key |

Temporary public delivery for Instagram or generated media can use:

- `S3_TMP_ENDPOINT_URL`
- `S3_TMP_BUCKET_NAME`
- `S3_TMP_BUCKET_REGION`
- `S3_TMP_ACCESS_KEY`
- `S3_TMP_SECRET_KEY`
- `S3_TMP_BASE_URL`

## Weather

| Variable | Purpose |
|---|---|
| `WEATHER_RECORD_ENABLED` | Enable weather recording |
| `WEATHER_RECORD_INTERVAL_SECONDS` | Weather polling interval |
| `WEATHER_PROVIDER` | Weather provider |
| `WEATHER_LATITUDE` | Target latitude |
| `WEATHER_LONGITUDE` | Target longitude |
| `WEATHER_TIMEZONE` | Target timezone |
| `WEATHER_BACKFILL_DAYS` | Initial backfill range |
| `WEATHER_OPEN_METEO_ARCHIVE_URL` | Open-Meteo archive URL |
| `WEATHER_FORECAST_URL` | Forecast feed URL |
| `WEATHER_AREA_NAME` | Forecast area |
| `WEATHER_OFFICE_NAME` | Forecast office |
| `WEATHER_FORECAST_TITLE` | Forecast title filter |

## OTA Firmware Delivery

| Variable | Purpose |
|---|---|
| `FIRMWARE_BASE_URL` | Full base URL used for firmware artifact URLs when set |
| `FIRMWARE_HOSTNAME` | Hostname used to build firmware HTTP URLs |
| `FIRMWARE_PORT` | Firmware HTTP port override |
| `HUB_HTTP_PORT` | Fallback port for firmware HTTP URLs |

Current firmware expects `http://` OTA URLs.

## Cloudflare Hosted Option

| Variable | Purpose |
|---|---|
| `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME` | Public hostname for Access/Tunnel |
| `CLOUDFLARE_ACCESS_TEAM_DOMAIN` | Access team domain |
| `CLOUDFLARE_ACCESS_POLICY_AUD` | Access audience tag |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_ACCESS_API_TOKEN` | Factory provisioning token passed only through process environment or hidden input; blank on the shipped appliance |
| `CLOUDFLARE_ACCESS_ALLOWED_EMAILS` | Initial allowed email list |
| `CLOUDFLARE_ACCESS_GROUP_ID` | Access group ID |
| `CLOUDFLARE_ACCESS_APP_ID` | Access application ID |
| `CLOUDFLARE_ACCESS_POLICY_ID` | Access policy ID |
| `CLOUDFLARE_TUNNEL_ID` | Tunnel ID |
| `CLOUDFLARE_TUNNEL_HOSTNAME` | Tunnel hostname |
| `CLOUDFLARE_TUNNEL_ORIGIN_URL` | Local origin URL. Default `http://127.0.0.1:39151` |
| `CLOUDFLARE_TUNNEL_TOKEN_FILE` | Local tunnel token file path |
| `CLOUDFLARE_ZONE_ID` | DNS zone ID |
| `CLOUDFLARE_ZONE_NAME` | DNS zone name |

## Instagram

Instagram posting requires the regular storage and weather settings plus
Instagram Graph API credentials. Publicly reachable temporary media URLs are
required; private bucket URLs cannot be posted.
