# Cloud Hub operations

## Required separation

Use three credential scopes:

- Worker runtime: directory DB token and tenant credential master key.
- Factory provisioning: Turso Platform token plus directory credentials.
- Edge Gateway: only its own parent bearer and local MQTT credentials.

Do not reuse credentials across these scopes.

## Deployment sequence

1. Run `npm ci`, `npm audit`, `npm run typecheck`, `npm test`, and a Wrangler
   dry run.
2. Bootstrap one directory DB or load its existing protected credential file.
3. Set `DIRECTORY_TURSO_DATABASE_URL` in `wrangler.jsonc`.
4. Configure `DIRECTORY_TURSO_AUTH_TOKEN` and
   `TENANT_CREDENTIAL_MASTER_KEY` with `wrangler secret put`.
5. Configure the Access team domain and `/api/*` application audience.
6. Run `npm run security:check`, then deploy with `npm run deploy`. The deploy
   command also verifies that both required Worker secrets exist remotely.
7. Verify `/healthz`, then verify Access login and an authorized
   `/api/tenants` call.

Live deployment is deliberately separate from repository tests and requires
production Cloudflare/Turso authorization.

The security check must report all of the following before deployment:

- exact custom domain, disabled `workers.dev`, and disabled preview URLs;
- exact public HTTPS origin and `libsql://*.turso.io` directory URL;
- valid Access team domain and 64-character application audience;
- node- and source-address Sync rate-limit bindings;
- `/api/*`, `/sync/*`, and `/healthz` routed through the Worker; and
- declarations for both runtime Worker secrets.

In Cloudflare Access, protect `cloud-hub.inas-technologies.com/api/*` with an Allow
policy and no Bypass policy. Enable HttpOnly and Binding Cookie, keep SameSite
`Lax`, and record the application audience in `wrangler.jsonc`.

## Access group separation

`hub.inas-technologies.com` and the Cloud Hub must never use the same Access
group. With `CLOUDFLARE_ACCOUNT_ID` and
`CLOUDFLARE_ACCESS_API_TOKEN` available only in the factory shell, inspect and
apply the idempotent configuration:

```bash
npm run access:separate
npm run access:separate -- --apply
```

The resulting policy boundary is:

- `inas-local-hub-operators` -> `hub.inas-technologies.com`
- `inas-cloud-hub-users` -> `cloud-hub.inas-technologies.com/api/*`

The command clones the current Local Hub rule only when the Cloud Hub group is
first created. Later customer membership changes belong only to the Cloud Hub
group and are not copied back to the Local Hub group.

## Directory deletion protection and recovery drill

Inspect and enable delete protection:

```bash
npm run directory:protect
npm run directory:protect -- --apply
```

Load the protected directory runtime credential and run a PITR drill:

```bash
set -a
. /secure/factory/inas-cloud-directory.env
set +a
npm run directory:recovery-drill
npm run directory:recovery-drill -- --execute
```

The executable drill requires delete protection on the source. It creates an
isolated database from the two-minute-old recovery point, creates a one-day
read-only token for that temporary database, and verifies:

- `PRAGMA integrity_check` on source and recovery;
- an exact SHA-256 match of the SQLite schema; and
- matching row counts for migrations, tenants, memberships, nodes, node
  credentials, and directory audit records.

On success the temporary recovery DB is deleted explicitly. On failure it is
retained and its non-secret name is printed for investigation. Use `--keep`
when a successful recovery must remain available for a manual inspection.

## Security audit and Discord alerts

Set `DISCORD_SECURITY_WEBHOOK_URL` as a Worker secret. Do not put it in
`wrangler.jsonc`, Git, an Edge Gateway, or an audit payload.

Every origin-visible Access or node authentication rejection, insufficient
role, cross-origin mutation, Sync rate limit, and oversized request writes a
structured `cloud_hub_security_audit` event to Workers Observability. The event
contains only event ID, time, event class, bounded method, normalized route,
status, authentication class, and a validated Cloudflare Ray ID. It excludes
email, IP address, query string, request body, Authorization header, and all
tokens.

Discord receives the same sanitized event. A dedicated Cloudflare rate-limit
binding sends at most one card per event class and normalized route per minute;
suppressed attempts remain in the audit log. Cloudflare Access failures blocked
before the Worker are recorded in Cloudflare Access authentication logs rather
than this Worker log.

## Customer and Gateway sequence

```bash
npm run tenant:provision
npm run gateway:kit
```

Apply the generated Gateway overlay only to its labeled appliance. Confirm file
ownership/mode on the target Linux filesystem, validate with
`ina-edge-gateway check-config`, and then perform a first Sync exchange before
shipment. The first exchange must update only the selected tenant and node.

The customer-visible URL uses a random public tenant ID. Internal tenant UUIDs,
DB names, URLs, and tokens do not appear on labels or QR payloads.

## Isolated tenant release regression

Keep one dedicated `regression-baseline` tenant and create a new
`reg-e-<run-id>` tenant for every release check. The ephemeral tenant must be
deprovisioned and deleted after every run; its database credential and node
credential are short-lived.

```bash
npm run regression:tenant -- status
npm run regression:tenant -- ensure --apply
npm run regression:tenant -- run
npm run regression:tenant -- run --apply
npm run regression:tenant -- status
```

The run verifies membership/API isolation, node-token isolation, sync
idempotency and conflicts, desired resources, commands, events, dashboard
summaries, and Turso database-token isolation across the two test tenants. It
also requires a stable pre/post snapshot of every non-regression directory
entry and never opens those tenants' databases.

If a run stops before cleanup, use the exact external manifest printed by the
failure:

```bash
npm run regression:tenant -- cleanup --apply \
  --manifest /absolute/persistent/state/inas/cloud-regression/<run-id>.json
```

The manifest is mode `0600`, contains no credential, and is removed only after
the exact ephemeral database and directory row are gone. See
[`TENANT_REGRESSION.md`](TENANT_REGRESSION.md) for the full procedure and
destructive-operation guards.

## Membership operations

Use `npm run membership:manage -- list --tenant <public-id>` for review. Grant
the least role required. Grant, revoke, and subject reset require an explicit
actor and confirmation, and write a directory audit entry. Access policy
membership and directory membership are two separate gates; change both during
onboarding and offboarding.

The first tenant request binds the membership to the Access subject. Use
`reset-subject` only after independently verifying that the IdP/Access identity
was recreated. The next authenticated request rebinds it and writes a new audit
entry. The database refuses to remove the last active admin.

## Gateway credential rotation

1. Create a second credential with `gateway:credential rotate`; keep its output
   outside the repository and install it mode `0600` on the labeled Gateway.
2. Restart or reload the Gateway, confirm successful Sync, and use
   `gateway:credential list` to verify `last_used_at` on the new credential.
3. Revoke the old credential by its credential UUID.
4. If a token may have leaked, rotate immediately, confirm the new credential,
   revoke the exposed one, inspect authentication logs by Ray ID, and review
   tenant events for the exposure window.

Never print or paste a token into tickets, chat, logs, shell history, or QR
codes. The rotation command returns the token only through a newly created
mode-`0600` file and removes that file if registration fails.

## Partial failures

- Directory bootstrap/customer provisioning never auto-deletes a Turso DB.
  Inspect an orphan, then use `--adopt-existing` only when its purpose and
  contents are known.
- Directory bootstrap refuses to generate a new master key for an adopted
  directory that already contains tenants.
- Gateway kitting atomically reserves a new output directory before writing
  credentials and removes it if node registration fails. If registration
  succeeds, preserve that directory; it contains the only copy of the node
  bearer.
- Retrying an Edge Sync request is safe only with the exact same event/result
  content. Identity reuse with changed content is an operational fault, not a
  recoverable overwrite.
- Development directory DBs created with credential envelope v1 are not
  compatible with this pre-release schema. Recreate them rather than weakening
  the runtime to accept v1.

## Backup and recovery

Back up/export the directory DB and every tenant DB independently. Store the
directory master key in a separate secret backup; a directory DB backup without
that key cannot recover tenant DB tokens. Conversely, never bundle the key
inside the directory DB backup.

Test restoration by:

1. restoring the directory DB under an isolated URL;
2. supplying the matching master key;
3. resolving one test membership and decrypting only its scoped token;
4. reading its restored tenant DB; and
5. confirming another tenant remains inaccessible.

Do not use production Edge credentials in a recovery drill.

## Incident response

- Access account suspected: remove it from the Access policy and revoke the
  directory membership. Reset the subject only for a verified replacement
  identity.
- Gateway token suspected: rotate, prove the new credential through
  `last_used_at`, then revoke the exposed credential.
- Directory token suspected: rotate the Turso directory token and update only
  the Worker secret.
- Tenant DB token suspected: issue a new database-scoped token, re-encrypt it
  with the unchanged authenticated tenant routing context, verify access, then
  revoke the old token.
- Master key suspected: treat every encrypted tenant DB token as exposed.
  Rotate all tenant DB tokens and the master key under a versioned migration;
  do not overwrite the key in place.

For every incident, preserve Cloudflare Ray IDs and directory/tenant audit
records, record the exposure interval, and avoid copying credential material
into the incident record.
