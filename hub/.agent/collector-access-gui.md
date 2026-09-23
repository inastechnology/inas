# Manage AI collector access from the Hub GUI

This ExecPlan follows hub/AGENTS.md and ARCHITECTURE_LAYERING_POLICY.md.
The referenced .agent/PLANS.md is absent, as noted by the existing MCP plan.

## Purpose

Allow a human Hub administrator to select fields, read scopes, and expiration,
issue a dedicated Cloudflare Service Token, and revoke access from settings.
Use the existing hostname, Tunnel, Access JWT verification, and Operations API.

## Decisions

- Work on a separate worktree; do not change production or existing edits.
- Use a dedicated host-owned Cloudflare management API token and explicit Access
  application ID. Check the application audience against the Hub audience before
  provisioning. Add only a per-collector Service Auth policy; never rewrite human
  policies or create a bypass rule.
- Keep Cloudflare HTTP in a connector, issuance/revocation in a service, persistent
  non-secret grants in a repository, and admin routes thin.
- Show Client Secret only in the issuance response. Never persist it. Persist
  pending/active/revoked metadata, expiry, and actor. Incomplete issuance grants
  no Hub access; revocation denies locally before remote cleanup.
- Existing host read grants continue to work. GUI records must never overlap
  host grants or writer identities. Revoked records deny rather than fall back.
- Human admin and same-origin protections cover all GUI mutations. Machine
  credentials cannot administer grants. Explicit field selection is the default.
- Read current grants on every authenticated Operations request so edits and
  revocation do not require a restart. Corrupt managed storage fails closed.

## Progress

- [x] Inspect authentication, settings, persistence, and official Cloudflare APIs.
- [x] Implement connector, repository, grant service, and auth integration.
- [x] Implement admin GUI and update current-versus-future user help.
- [x] Test permission boundaries, failure recovery, secret handling, and UI flows.
- [x] Run full tests and relevant checks; prepare the change for review.

## Validation

Use temporary directories and mocked Cloudflare responses. Test admin-only and
same-origin access, scope/field validation, expiry, revoked-token rejection,
writer/reader separation, partial failures, no secret persistence, HTTP redirect
refusal, and current human authentication. Run the full Hub suite with dotenv
disabled. No live token issuance or production Access policy changes for tests.

## Operational prerequisites

An administrator must configure the dedicated management credential and Access
application ID on the host before issuance is enabled. This implementation does
not assume those credentials are already present or deploy automatically.

## Validation results

- Focused collector/read/JWT suite: 49 tests passed.
- Full Hub suite on the isolated implementation: 623 tests passed.
- Ruff checks and formatting: all nine changed/new Python files passed.
- The legacy `rye run lint` entry point could not initialize its worktree virtual
  environment in the sandbox. Direct Ruff checks/format and the full unittest
  suite were run with existing tool environments instead.
- JavaScript syntax check passed. Chromium against a loopback-only Flask fixture
  with a mocked Cloudflare connector passed issuance, one-time secret handling,
  field/scope editing, revocation, and 390px layout checks without browser errors.
- No production tokens, policies, host settings, or human Access routes were
  used in the checks. Production remains on the previously deployed JWT fix.
- Unknown issuance responses remain denied and flagged for manual Cloudflare
  reconciliation using the generated Token/policy name. Restore of old grant
  backups requires checking Cloudflare revocation state, as documented.

## Production setup follow-up

On 2026-09-24, the user authorized deployment and host configuration. Live checks
with the existing Access management credential verified the application audience,
temporary Service Token creation, and a policy limited to that temporary token.
Cloudflare rejected deletion of a token while the policy referenced it (HTTP 400).
Removing the policy first allowed token deletion; both temporary resources were
removed. Cleanup now removes the policy before the credential, while retaining
the existing local-denial-first ordering. Regression coverage checks this order.
