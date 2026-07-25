# Cloud Hub tenant regression

This runbook verifies Cloud Hub changes without reading or mutating a customer
tenant database. It uses two dedicated test boundaries:

- `regression-baseline` is the persistent regression tenant. Its Turso database
  is retained and has delete protection enabled.
- `reg-e-<run-id>` is a newly provisioned ephemeral tenant. Every `run` creates
  a new database, membership, node, and short-lived credentials, then removes
  them after the checks.

The persistent tenant's test node and test records are also run-scoped and are
deleted after every run. Only the persistent tenant, its administrator
membership, database schema, and protected database remain.

## Required factory environment

Run from `hub-cloud/` on a factory/admin workstation. Load:

- `DIRECTORY_TURSO_DATABASE_URL`
- `DIRECTORY_TURSO_AUTH_TOKEN`
- `TENANT_CREDENTIAL_MASTER_KEY`
- `CLOUD_HUB_REGRESSION_ADMIN_EMAIL`

When `CLOUD_HUB_REGRESSION_ADMIN_EMAIL` is omitted, the command accepts exactly
one normalized address from `CLOUDFLARE_ACCESS_ALLOWED_EMAILS`. It fails closed
when zero or multiple fallback addresses exist.

The Turso CLI must be authenticated to the organization that owns the
databases. `TURSO_ORG`, `TURSO_GROUP`, and `TURSO_PLATFORM_TOKEN` may be
provided explicitly; otherwise the command uses the authenticated Turso user,
the `ina-technologies` group, and a token obtained from the CLI. Platform
credentials are used only by this factory process and must never be configured
as Worker secrets.

For example:

```bash
set -a
. /secure/factory/inas-cloud-directory.env
. ../hub/.env
set +a

export CLOUD_HUB_PUBLIC_ORIGIN='https://cloud-hub.inas-technologies.com'
npm run regression:tenant -- status
npm run regression:tenant -- ensure
npm run regression:tenant -- ensure --apply
npm run regression:tenant -- run
npm run regression:tenant -- run --apply
```

`ensure` is idempotent only for the exact fixed tenant definition. It refuses
an ambiguous directory row, a mismatched administrator, or an unregistered
database with the reserved name. It applies current directory and tenant
migrations and verifies delete protection.

`run` prints one final JSON result. A passing result includes the run ID, the
ephemeral public ID, every tested boundary, confirmation that the
non-regression directory snapshot did not change, and completed cleanup.
It refuses to start while any earlier ephemeral regression row or cleanup
manifest remains; finish that cleanup before creating another tenant.

## Checks performed by every run

The command exercises the real application repositories against the live
Directory and the two dedicated Turso databases:

1. Register a fresh, two-hour node credential in each test tenant.
2. Confirm each node token is rejected on the peer node path with `401`.
3. Confirm path/body node mismatch and caller-supplied `tenant_id` are rejected.
4. Sync a unique marker into each tenant, retry the exact marker successfully,
   and reject changed content with the same identity using `409`.
5. Deliver only the node's own desired resource and pending command, then
   complete that command.
6. Confirm each database contains its own marker and not the peer marker.
7. Confirm a database-scoped Turso token cannot open the peer database.
8. Use injected Access identities with the production membership and runtime
   code to confirm both cross-tenant browser API directions return `404`.
9. Exercise the ephemeral tenant's `me`, event creation/listing, dashboard, and
   node listing APIs; also reject a cross-origin mutation with `403`.
10. Call the deployed origin's health endpoint and perform an authenticated
    Sync exchange for each test tenant, requiring each response to acknowledge
    and return only that node's expected records.
11. Hash stable directory routing, membership, node, and credential fields for
    every non-regression tenant before and after the run and require an exact
    match.

The command deliberately does not open any non-regression tenant database.
Cloudflare Access JWT signature/issuer/audience validation remains covered by
the automated unit suite and the deployed Access application. This regression
uses injected identities so it can exercise the real membership-to-Turso data
boundary without storing a browser cookie or binding the persistent membership
to a fabricated Access subject.

After the persistent administrator signs in normally for the first time, the
membership is pinned to the actual Access subject. Later regression runs reuse
that subject only for denial checks; they never reset or replace it.

## Crash-safe cleanup

Before creating the ephemeral database, `run` writes a mode-`0600` manifest
under the current user's persistent state directory:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/inas/cloud-regression/<run-id>.json
```

The state directory is mode `0700`, owned by the current user, outside the
repository, and may not be a symlink. The manifest contains no token or email.
It contains only the run ID and the exact ephemeral internal UUID, public ID,
database name, and customer reference.

Cleanup requires both that manifest and `--apply`:

```bash
npm run regression:tenant -- cleanup \
  --manifest /absolute/persistent/state/inas/cloud-regression/<run-id>.json

npm run regression:tenant -- cleanup --apply \
  --manifest /absolute/persistent/state/inas/cloud-regression/<run-id>.json
```

The destructive guard re-derives every reserved identifier from the run ID and
compares all four identifiers with the live directory row. It cannot accept a
normal customer database name or public ID.

Use `--state-dir <absolute-path>` when factory state belongs on another
persistent encrypted volume. Do not place it under the repository or on a
volatile temporary filesystem.

Cleanup proceeds in this order:

1. Set the ephemeral tenant to `deprovisioning`, immediately removing it from
   membership and node routing.
2. Revoke and delete exact run nodes and remove persistent run fixtures.
3. Delete only the exact ephemeral Turso database.
4. Remove the ephemeral membership and directory row while retaining
   non-secret directory audit entries.
5. Delete the manifest only after every step succeeds.

If the process stops, `status` lists the remaining manifest and any regression
tenant directory rows. Re-run the exact cleanup command. Cleanup is resumable
when the database or directory row has already been removed. Never edit, copy,
or rename a manifest to target another resource.

## Release operation

Run this sequence after migrations or changes to Access membership, directory
routing, Sync, event, command, desired-state, node, or dashboard behavior:

```bash
npm run typecheck
npm test
npm run regression:tenant -- status
npm run regression:tenant -- run
npm run regression:tenant -- run --apply
npm run regression:tenant -- status
```

Do not promote the release when:

- any regression check fails;
- the manifest remains after the explicit cleanup retry;
- an ephemeral directory row or Turso database remains;
- the persistent database has delete protection off; or
- the non-regression directory snapshot changed.
