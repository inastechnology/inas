# INAS Hub Cloud

`hub-cloud` is the shared Cloudflare Workers frontend/API for customers who use
INAS Edge Gateways without operating a Local Hub. It uses one Worker deployment
and one small directory database, while assigning one dedicated Turso database
to every customer.

```text
browser -- Cloudflare Access --> shared Worker
                                  |
                                  +-- directory Turso DB
                                  |     membership -> tenant DB credential
                                  |
                                  +-- customer A Turso DB
                                  +-- customer B Turso DB

Edge Gateway -- HTTPS + node bearer --> shared Worker
                                         |
                                         +-- node registry -> customer DB
```

The browser never selects a database. The Worker verifies the Cloudflare Access
JWT signature, issuer, audience, token type, subject, and lifetime, then
resolves the public tenant ID with an active membership. On first use, that
membership is pinned to the Access subject as well as the normalized email.
An Edge Gateway is resolved from its registered `INAEG-<UUIDv4>` identity and
an independently revocable bearer credential. Request bodies containing
`tenant_id`, a database URL, or a database token are rejected.

The Local Hub under `../hub/` remains a separate product and keeps its existing
per-installation Turso/libSQL configuration. Edge Gateways do not receive any
Turso credential.

## Cloudflare layout

The initial low-cost URL is:

```text
https://cloud-hub.inas-technologies.com/t/<public-tenant-id>/
```

`wrangler.jsonc` deploys one Worker and its static assets on the exact custom
domain. It does not create a Worker, hostname, or Cloudflare account resource
per customer.

Create one Cloudflare Access self-hosted application for:

```text
cloud-hub.inas-technologies.com/api/*
```

Its Allow policy should contain only approved identities or identity-provider
groups. Put that application's audience tag in
`CLOUDFLARE_ACCESS_POLICY_AUD`. The static HTML/CSS/JS shell contains no
customer data; all data APIs require the verified Access assertion. The shell
starts an Access navigation through `/api/session/start` when there is no
session.

The Cloud Hub and INAS-operated Local Hub must use different Access groups.
Apply and verify the split with factory-only Cloudflare credentials:

```bash
npm run access:separate
npm run access:separate -- --apply
```

The command keeps `inas-local-hub-operators` on `hub.inas-technologies.com`
and binds only `inas-cloud-hub-users` to the Cloud Hub Allow policy. It is
idempotent and refuses an unexpected multi-selector Allow policy.

In the Access application:

- enable HttpOnly on the application token;
- keep SameSite at `Lax` unless a reviewed integration requires another value;
- enable a Binding Cookie to make copied application tokens harder to reuse;
- use the shortest session duration compatible with the operational workflow;
- do not add a Bypass policy; and
- review policy membership whenever a Hub membership is granted or revoked.

Do not place `/sync/*` in that browser Access application and do not create an
Access Bypass policy for it. Sync is a machine API and is independently
authenticated in the Worker with a random per-node token. Worker rate-limit
bindings restrict both requests per node and requests per source address.
Apply Cloudflare WAF rules to `/sync/v1/nodes/*/exchange` as an outer
denial-of-service control; they do not replace node authentication.

## Database layout

- Directory DB: tenant status, Access email/subject memberships, Edge node
  registry, salted node-token digests, credential expiry/usage metadata, and
  encrypted per-tenant DB tokens. It contains no telemetry or field operation
  records.
- Tenant DB: one Turso DB per customer. It contains that customer's events,
  node health, desired state, commands, and audit records. It intentionally has
  no `tenant_id` column because the database itself is the isolation boundary.
- Tenant DB token: Turso database-scoped token, encrypted in the directory DB
  with AES-256-GCM. Credential envelope v2 authenticates the internal tenant
  UUID, database name, and exact `libsql://*.turso.io` URL as additional data.
  Changing any routing field makes decryption fail.

See [docs/SECURITY.md](docs/SECURITY.md) for the full boundary and
[docs/OPERATIONS.md](docs/OPERATIONS.md) for provisioning and recovery.
Use [docs/TENANT_REGRESSION.md](docs/TENANT_REGRESSION.md) for the isolated
persistent-plus-ephemeral tenant release regression.

## Development

```bash
npm ci
npm audit
npm run typecheck
npm test
npm run security:check
npx wrangler deploy --dry-run
```

Copy `.dev.vars.example` to the untracked `.dev.vars` for local Worker
development. Never commit real tokens. `security:check` intentionally fails
until the production Access team, audience, and directory URL have been filled
in.

## One-time directory bootstrap

Set factory-only Turso Platform credentials in the process environment:

```bash
export TURSO_ORG='your-organization'
export TURSO_GROUP='default'
read -rsp 'Turso Platform token: ' TURSO_PLATFORM_TOKEN
export TURSO_PLATFORM_TOKEN
npm run directory:bootstrap -- \
  --output /secure/factory/inas-cloud-directory.env
```

The output is mode `0600` and contains the directory DB URL/token plus the
tenant credential master key. Keep it outside the repository and outside every
shipped device. Configure `DIRECTORY_TURSO_DATABASE_URL` in `wrangler.jsonc`,
then set the three Worker secrets without placing their values on the command
line:

```bash
read -rsp 'Directory Turso token: ' DIRECTORY_TURSO_AUTH_TOKEN
printf '%s' "$DIRECTORY_TURSO_AUTH_TOKEN" | npx wrangler secret put DIRECTORY_TURSO_AUTH_TOKEN

read -rsp 'Tenant credential master key: ' TENANT_CREDENTIAL_MASTER_KEY
printf '%s' "$TENANT_CREDENTIAL_MASTER_KEY" | npx wrangler secret put TENANT_CREDENTIAL_MASTER_KEY

read -rsp 'Discord security webhook: ' DISCORD_SECURITY_WEBHOOK_URL
printf '%s' "$DISCORD_SECURITY_WEBHOOK_URL" | npx wrangler secret put DISCORD_SECURITY_WEBHOOK_URL
```

The Turso Platform token is provisioning-only and must never be configured as a
Worker secret.

Before the first deployment, set the Access team domain, 64-character
application audience, exact production origin, and directory URL in
`wrangler.jsonc`. `npm run deploy` runs a fail-closed preflight and confirms the
three required Worker secrets already exist remotely before publishing.

Protect the directory from accidental deletion and run the isolated recovery
drill before customer onboarding:

```bash
npm run directory:protect
npm run directory:protect -- --apply

set -a
. /secure/factory/inas-cloud-directory.env
set +a
npm run directory:recovery-drill
npm run directory:recovery-drill -- --execute
```

The recovery drill restores a two-minute-old PITR snapshot under a unique
temporary name, uses a short-lived read-only token, checks database integrity,
schema identity, and core table counts, and deletes only the verified temporary
database. A failed drill retains its temporary database for investigation.

## Provision a customer

Load the protected directory credentials into the factory shell, keep the
Platform token in the environment, and run:

```bash
set -a
. /secure/factory/inas-cloud-directory.env
set +a
npm run tenant:provision
```

The interactive command:

1. creates a dedicated Turso DB and database-scoped token;
2. applies the tenant schema;
3. encrypts the token into the directory DB;
4. creates the first Access email membership; and
5. returns the non-secret Cloud Hub URL.

It never deletes a DB automatically after a partial failure. An already-created
orphan must be inspected and explicitly adopted with `--adopt-existing`.

The current directory schema is a pre-release initial schema. Development
directory databases created with credential envelope v1 must be discarded and
re-provisioned; the Worker deliberately does not accept v1 routing credentials.

## Isolated tenant regression

Create or verify the protected persistent regression tenant, then create and
delete a fresh ephemeral peer for every run:

```bash
npm run regression:tenant -- status
npm run regression:tenant -- ensure
npm run regression:tenant -- ensure --apply
npm run regression:tenant -- run
npm run regression:tenant -- run --apply
```

The run verifies node-token, membership, API, and database credential isolation
in both directions. It refuses normal tenant identifiers, does not open any
customer tenant database, and requires an external mode-`0600` manifest for
resumable cleanup. See the regression runbook before using `--apply`.

## Kit an Edge Gateway

After the customer exists:

```bash
npm run gateway:kit
```

The interactive command selects the customer, registers a new
`INAEG-<UUIDv4>`, stores only its salted token digest, and writes a protected
appliance overlay to a new absolute path outside the repository. The overlay
contains:

- `/var/lib/inas/identity.json`;
- `/etc/inas/edge-gateway.json`;
- mode-`0600` parent and MQTT credential files;
- a factory AP setup card, Wi-Fi QR, and customer Cloud Hub URL QR; and
- a non-database-routing shipment manifest.

The AP QR contains only its short-lived local AP credential. The URL QR contains
only the public customer path. Neither QR nor the rest of the overlay has a
directory credential, tenant DB URL/token, Turso Platform token, or Cloudflare
administrative token.

## Membership and node credential lifecycle

List, grant, revoke, or explicitly reset an Access subject binding:

```bash
npm run membership:manage -- list --tenant <public-id>
npm run membership:manage -- grant --tenant <public-id> \
  --email user@example.com --role operator --actor operator@example.com
npm run membership:manage -- revoke --tenant <public-id> \
  --email user@example.com --actor operator@example.com
```

The database refuses to demote, revoke, or delete the final active tenant
administrator. Resetting a subject is a recovery action for a recreated Access
identity and must be followed by a fresh authenticated login.

Rotate a Gateway token with overlap, verify use of the new credential, then
revoke the old credential:

```bash
npm run gateway:credential -- rotate --node <INAEG-id> \
  --output /secure/factory/new-parent-token --actor operator@example.com
npm run gateway:credential -- list --node <INAEG-id>
npm run gateway:credential -- revoke --node <INAEG-id> \
  --credential-id <old-credential-uuid> --actor operator@example.com
```

At most two unexpired credentials may overlap, and the database prevents
revocation of the final usable credential. The Gateway accepts only a regular,
non-symlink, mode-`0600` token file containing the exact 43-character token.
