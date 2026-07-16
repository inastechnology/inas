# Operations Guide

Japanese version:

- [jp/OPERATIONS.md](jp/OPERATIONS.md)

## Local Hub

Start in development:

```bash
uv run python src/ina_device_hub/serve.py
```

Default URL:

```text
http://localhost:39151
```

## systemd

Install or update while preserving the existing `.env` and MQTT settings:

```bash
sudo ./scripts/install_service.sh
```

Install with a custom target:

```bash
sudo ./scripts/install_service.sh --user mysvcuser --target-dir /opt/ina-device-hub
```

Enable Cloudflare Tunnel service support:

```bash
sudo ./scripts/install_service.sh --production --target-dir "$PWD" --enable-cloudflare-tunnel
```

Use `--production` only for the initial Cloudflare production deployment or an explicit reprovision. Omit it after a normal server-side `git pull`; upgrade mode validates the existing external connections, backs up state, updates the unit, restarts the Hub, and verifies `/readyz` without rewriting `.env` or MQTT settings.

Check:

```bash
systemctl status inas-device-hub@main
journalctl -u inas-device-hub@main -f
```

Helper:

```bash
sudo ./scripts/hub_service.sh start
sudo ./scripts/hub_service.sh restart
./scripts/hub_service.sh status
./scripts/hub_service.sh logs
```

## Cloudflare Tunnel

Provision:

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
```

Run local hub and tunnel together:

```bash
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

Run tunnel only:

```bash
bash scripts/cloudflare_tunnel_start.sh
```

Daemon helper:

```bash
bash scripts/cloudflare_tunnel_daemon.sh --install-cloudflared start
bash scripts/cloudflare_tunnel_daemon.sh status
bash scripts/cloudflare_tunnel_daemon.sh logs
```

Cloudflare Error 1033 usually means the Tunnel connector is stopped or cannot
reach the local origin.

## Allowed Emails

```bash
python3 scripts/cloudflare_access_setup.py list
python3 scripts/cloudflare_access_setup.py add user@example.com
python3 scripts/cloudflare_access_setup.py remove user@example.com
python3 scripts/cloudflare_access_setup.py apply allowed_emails.txt --yes
```

Removing an email from the Access group may not revoke existing sessions
immediately. For urgent removal, revoke active Cloudflare Access sessions as
well.

## Local File Migration

```bash
bash scripts/migrate_local_files.sh list
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --overwrite
```

Include `WORK_DIR`:

```bash
bash scripts/migrate_local_files.sh export-zip /tmp/ina-device-hub-local-files.zip --include-work-dir
bash scripts/migrate_local_files.sh import-zip /tmp/ina-device-hub-local-files.zip --include-work-dir --overwrite
```

Move from an old device:

```bash
bash scripts/migrate_local_files.sh move-device \
  --source-dir /mnt/old-device/path/to/ina-device-hub \
  --target-dir /path/to/ina-device-hub \
  --source-work-dir /mnt/old-device/path/to/.ina-device-hub \
  --target-work-dir /path/to/.ina-device-hub \
  --overwrite
```

## OTA Operations

1. Build firmware in the device project.
2. Run `make check-firmware`.
3. Upload/register the firmware from the hub UI.
4. Verify artifact size, sha256, and generated HTTP URL.
5. Offer the target firmware through MQTT.
6. Watch OTA status.

Firmware binaries are delivered by local hub HTTP, not by MQTT.

## NTP

If devices need an explicit NTP server, run it as an OS service on the local
network. The hub only distributes the `ntp_server` value; it does not provide an
NTP server itself.

## Routine Checks

- Local hub service is active.
- MQTT broker is reachable.
- `WORK_DIR` and local storage are writable.
- Cloudflare Tunnel connector is running when remote access is expected.
- OTA firmware URLs are reachable by devices over HTTP.
- Secrets are not present in logs or committed files.
