# Cloudflare hosted options

INAS has two separate deployment modes. Do not merge their databases or
credentials.

## Local Hub with optional Tunnel

The existing Local Hub runs Flask, MQTT, schedules, storage integration, and
its configured Turso/libSQL replica on the customer-controlled host.
Cloudflare Access + Tunnel may expose that same Local Hub remotely:

```text
browser -> Cloudflare Access -> Tunnel -> Local Hub :39151
devices -> local MQTT broker -> Local Hub
```

The Tunnel does not turn the Local Hub into a Cloud Hub and does not change its
database ownership. Local MQTT and direct commands continue when the WAN,
Access, or Tunnel is unavailable.

Configure the existing low-level flow from `hub/.env`:

```bash
bash scripts/cloudflare_hosted_setup.sh --install-cloudflared
bash scripts/cloudflare_hosted_up.sh --install-cloudflared
```

The Local Hub validates `Cf-Access-Jwt-Assertion` when
`HUB_AUTH_MODE=cloudflare_access`. Existing production installations must keep
their current `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`; these values are not
replaced by Cloud Hub credentials.

## Shared Cloud Hub

Customers who do not operate a Local Hub use the separate implementation under
[`../../hub-cloud/`](../../hub-cloud/README.md):

```text
browser -> Cloudflare Access -> one shared Worker
Edge Gateway -> authenticated HTTPS Sync -> one shared Worker
                                      |
                                      +-- directory Turso DB
                                      +-- one dedicated Turso DB per customer
```

Cloud Hub does not create a Worker for every customer. The shared Worker first
authenticates an Access user or Edge node, resolves its tenant in the directory,
and only then opens the dedicated customer DB. Request input cannot select a DB
URL, token, or internal tenant ID.

Cloud Hub has no cloud MQTT broker. MQTT, the Wi-Fi AP, cached runtime config,
and local safe action remain on each Edge Gateway. The Gateway receives only
its node credential and Cloud Hub Sync URL, never a Turso or Cloudflare
administrative credential.

## Security boundary

- Local Hub browser auth and Edge Sync node auth are separate.
- Local Hub Turso credentials are never copied to Cloud Hub or an Edge Gateway.
- Cloud Hub directory and tenant DB credentials are never copied to Local Hub
  or an Edge Gateway.
- An Edge Gateway has exactly one immediate parent, Local Hub or Cloud Hub.
- Billing/trial state may restrict Cloud UI/management features later, but
  cannot disable the local MQTT safety loop.

See [Cloud Hub security](../../hub-cloud/docs/SECURITY.md) and
[hierarchical Sync](jp/HIERARCHICAL_SYNC.md).
