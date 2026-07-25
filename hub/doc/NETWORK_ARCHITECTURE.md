# INA Device Hub Network Architecture

Japanese version:

- [jp/NETWORK_ARCHITECTURE.md](jp/NETWORK_ARCHITECTURE.md)

This document describes only the optional remote-entry path for an existing
Local Hub. Cloudflare Access and Cloudflare Tunnel forward traffic to that
Local Hub HTTP server and do not change its Turso/libSQL configuration. The
separate shared Cloud Hub/Edge path is documented under
[`../../hub-cloud/`](../../hub-cloud/README.md).

For the current cross-project diagram, see:

- [../../docs/SYSTEM_SPECIFICATION.md](../../docs/SYSTEM_SPECIFICATION.md)
- [../../docs/assets/inas_system_architecture.svg](../../docs/assets/inas_system_architecture.svg)

## Paths

- UI/API path: administrator browser -> Cloudflare Access -> Cloudflare Tunnel
  at the configured `CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME` -> Local Hub
  `http://127.0.0.1:39151`.
- MQTT path: local hub and devices exchange status, config, irrigation control,
  and OTA offer/status through the MQTT broker.
- OTA binary path: devices download `firmware.bin` from the local hub HTTP
  endpoint `/firmware/<device_kind>/<version>/firmware.bin`.
- OTA URL generation path: the hub uses `FIRMWARE_BASE_URL` if set; otherwise it
  builds an HTTP URL from `FIRMWARE_HOSTNAME`, OS `HOSTNAME`, or hostname plus
  `FIRMWARE_PORT` / `HUB_HTTP_PORT`.

## Important Assumptions

- The Tunnel connector runs on the device side. Do not start it from a separate
  development PC unless that PC is the intended origin.
- `CLOUDFLARE_TUNNEL_ORIGIN_URL` defaults to `http://127.0.0.1:39151`.
- Cloudflare Access public hostnames are for authenticated hub UI/API access.
  They are not used for current OTA firmware download URLs.
- Current firmware accepts only `http://` OTA download URLs. HTTPS OTA requires
  device-side certificate validation first.
- Every Local Hub Tunnel and Access application remains scoped to that Local
  Hub and is not reused as Cloud Hub tenant routing.
