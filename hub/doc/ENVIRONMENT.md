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

## MQTT

| Variable | Purpose |
|---|---|
| `MQTT_BROKER_URL` | MQTT broker host |
| `MQTT_BROKER_PORT` | MQTT broker port |
| `MQTT_BROKER_USERNAME` | MQTT username |
| `MQTT_BROKER_PASSWORD` | MQTT password |

## Turso

| Variable | Purpose |
|---|---|
| `TURSO_DATABASE_URL` | Turso/libSQL database URL |
| `TURSO_AUTH_TOKEN` | Turso auth token |

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
| `CLOUDFLARE_ACCESS_API_TOKEN` | Provisioning token for local scripts only |
| `CLOUDFLARE_ACCESS_ALLOWED_EMAILS` | Initial allowed email list |
| `CLOUDFLARE_ACCESS_GROUP_ID` | Access group ID |
| `CLOUDFLARE_ACCESS_APP_ID` | Access application ID |
| `CLOUDFLARE_ACCESS_POLICY_ID` | Access policy ID |
| `CLOUDFLARE_TUNNEL_ID` | Tunnel ID |
| `CLOUDFLARE_TUNNEL_HOSTNAME` | Tunnel hostname |
| `CLOUDFLARE_TUNNEL_ORIGIN_URL` | Local origin URL. Default `http://localhost:39151` |
| `CLOUDFLARE_TUNNEL_TOKEN_FILE` | Local tunnel token file path |
| `CLOUDFLARE_ZONE_ID` | DNS zone ID |
| `CLOUDFLARE_ZONE_NAME` | DNS zone name |

## Instagram

Instagram posting requires the regular storage and weather settings plus
Instagram Graph API credentials. Publicly reachable temporary media URLs are
required; private bucket URLs cannot be posted.
