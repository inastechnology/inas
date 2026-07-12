# INA Device Hub Network Architecture

Japanese version:

- [jp/NETWORK_ARCHITECTURE.md](jp/NETWORK_ARCHITECTURE.md)

The current Tunnel operating model does not host the hub UI on Cloudflare
Workers. Cloudflare Access and Cloudflare Tunnel act as the authenticated entry
point, and traffic is forwarded to the local hub HTTP server running on the
device-side site.

For the current cross-project diagram, see:

- [../../docs/SYSTEM_SPECIFICATION.md](../../docs/SYSTEM_SPECIFICATION.md)
- [../../docs/assets/inas_system_architecture.svg](../../docs/assets/inas_system_architecture.svg)

## Paths

- UI/API path: administrator browser -> Cloudflare Access -> Cloudflare Tunnel
  -> local hub `http://localhost:39151`.
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
- `CLOUDFLARE_TUNNEL_ORIGIN_URL` defaults to `http://localhost:39151`.
- Cloudflare Access public hostnames are for authenticated hub UI/API access.
  They are not used for current OTA firmware download URLs.
- Current firmware accepts only `http://` OTA download URLs. HTTPS OTA requires
  device-side certificate validation first.
- Cloudflare Workers are a separate Cloud app option. They are not required for
  the Tunnel path.
