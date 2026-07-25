# Edge Gateway Hardware and Identity

Japanese specification: [jp/EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md](jp/EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md)

This document summarizes the identity namespace and hardware baseline for the hierarchical INAS platform. The Japanese counterpart contains the detailed manufacturing, enrollment, and inventory rules.

## Identity namespace

| Entity | Production ID | Role |
|---|---|---|
| Client Device | `INADS-<lowercase UUIDv4>` | Sensor or actuator using the existing device MQTT contract |
| Edge Gateway | `INAEG-<lowercase UUIDv4>` | Independent field gateway running the Edge Runtime |
| Local Hub | `INALH-<lowercase UUIDv4>` | Local control plane with an embedded Edge Runtime |

The prefix identifies only the entity class. Tenant, site, field, parent, device kind, hardware model, SIM, MAC address, and board serial remain separate attributes. IDs are immutable and are not reused. Existing production `INADS` IDs remain valid; `INADS-DEMO-*` is rejected outside explicit demo/test paths.

UUIDv4 is used for physical identities because a newly imaged field node may not have a trustworthy clock. Cloud-only business records may adopt another identifier format without changing the MQTT contract.

## Enrollment and credentials

Production gateways receive a node ID and asymmetric key pair during manufacturing. The private key should be generated inside a TPM 2.0 or secure element and must not be placed in a claim QR code. Enrollment uses a short-lived, single-use claim followed by proof of possession. Rotating a key does not change the node ID.

Every synchronizing node has one immediate parent and one configuration authority. An Edge Gateway authenticates to either a Local Hub or the shared Cloud Hub with its node credential; it never receives a Turso URL, Turso token, tenant routing override, or Cloudflare administrative credential.

## Hardware profiles

| Profile | Baseline | Intended use |
|---|---|---|
| `egw-rpi5-development-r0` | Raspberry Pi 5, 4 GB, development storage | Pilot and performance measurement only |
| `egw-cm4-standard-r1` | CM4-class, 2 GB RAM, 32 GB eMMC, wireless | Standard MQTT/AP/Sync production candidate |
| `egw-cm4-cellular-r1` | Standard profile plus LTE modem | Field without fixed WAN; SORACOM preferred |
| `egw-cm5-vision-r1` | CM5-class, 4 GB RAM, 32 GB or more eMMC | Camera/ffmpeg candidate after load tests |
| `lhb-cm5-standard-r1` | CM5-class, 4 GB or more RAM and eMMC | Local UI, database, and child-gateway aggregation |

Production Edge appliances use eMMC rather than removable microSD. They provide a dedicated 2.4 GHz device AP, Ethernet and optional LTE WAN, watchdog, power-failure-tolerant storage, protected keys, signed boot/update, and an isolated device network. Wi-Fi WAN requires a second radio; the device AP is not shared with it.

The final module SKU, carrier board, modem, enclosure, power supply, antennas, thermals, certifications, and BOM remain gated by pilot measurements and hardware review. Changing a hardware profile does not change a node ID.

## Runtime boundary

The Edge Gateway runs the local MQTT broker/client, desired-config cache, action/schedule execution, durable SQLite outbox, command inbox, NTP, OTA cache, and health reporting. A Local Hub embeds the same runtime and adds its UI, existing Turso/libSQL business storage, child Sync server, and optional Cloudflare Tunnel. The shared Cloud Hub accepts the same HTTPS Sync envelope and resolves the registered node to a dedicated customer Turso DB.

SORACOM supplies an HTTPS WAN path from the gateway to its parent. MQTT remains inside the field LAN, so a parent outage does not remove the cached local control loop.

## Related material

- [Sync v1 contract](../shared/contracts/sync/v1/README.md)
- [Raspberry Pi Compute Module documentation](https://www.raspberrypi.com/documentation/computers/compute-module.html)
- [Raspberry Pi secure boot](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#secure-boot)
- [SORACOM Onyx setup](https://developers.soracom.io/en/docs/soracom-onyx-lte-usb-modem/software-setup/)
- [Cloudflare client certificates](https://developers.cloudflare.com/ssl/client-certificates/)
