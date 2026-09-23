# Repository Instructions For AI Developers

## Human And Agent Access

The Hub's Cloudflare Access browser login and protected public UI are for
humans. AI agents must not open or probe that human-facing route with a browser,
`curl`, or browser automation, including for screenshots or deployment checks.
Do not run `cloudflared access login`, request human login/OTP completion, or
reuse a person's Access cookies or JWTs for agent work.

- For on-host health checks, use the existing localhost `/healthz` and `/readyz`
  endpoints. For UI verification, use a local development or demo server.
- For remote administration, use the dedicated `/operations/api/v1/*` endpoints
  with a machine Service Token and the clients in `hub/scripts/operations/`.
  This separate machine authentication also uses Cloudflare Access; it does not
  authorize access to the human UI or browser-oriented APIs.
- If machine credentials or an Operations endpoint are unavailable, report the
  limitation. Do not fall back to human login, public `/local/api/*` calls, or
  weakening authentication.

See [AI Agent Environment Setup](hub/doc/AI_AGENT_ENVIRONMENT_SETUP.md) and
[Operations clients](hub/scripts/operations/README.md).

## Hub Extension Work

When a task adds, changes, reviews, or removes a Hub Extension or an Extension
API/UI extension point, read the following files completely before editing:

1. `extensions/AGENTS.md`
2. `docs/EXTENSION_SPECIFICATION.md`
3. `docs/EXTENSION_SECURITY_REVIEW_POLICY.md`
4. `docs/ARCHITECTURE_LAYERING_POLICY.md`

Treat **Hub Extension**, **Device Definition**, and device **Runtime Config** as
different concepts. An Extension packages optional contributions; a Device
Definition describes firmware capabilities; Runtime Config is per-device data
sent by the Hub.

Extension-specific content belongs under `extensions/<extension-name>/`. Do not
add Extension IDs, labels, device-specific branches, or presentation text to Hub
core when a declarative contribution can express the behavior.

Other project-local `AGENTS.md` files may add more specific rules for their
subtrees.

## User-Facing System Help

When a change affects farmer-facing Hub navigation, settings, troubleshooting,
current-versus-future feature availability, or the community proposal process:

1. Update or add a concise user-facing document under `hub/doc/system-help/`.
2. Clearly distinguish currently available behavior from planned behavior.
3. Link detailed design documents instead of copying internal specifications
   into the user-facing document.

The former `hub/cloudflare` AI Search integration is not connected to the
current product. Do not recreate its manifest, synchronization scripts, Worker,
or remote indexing path without an explicitly approved redesign.
