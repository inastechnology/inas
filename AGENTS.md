# Repository Instructions For AI Developers

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

## AI Search Documentation

When a change affects farmer-facing Hub navigation, settings, troubleshooting,
current-versus-future feature availability, or the community proposal process:

1. Update or add a concise user-facing document under `hub/doc/system-help/`.
2. Register it in `hub/cloudflare/data/system-help-manifest.json`.
3. Add or update retrieval cases in
   `hub/cloudflare/data/system-help-evaluation.json`.
4. Run `npm run system-help:sync -- --dry-run` from `hub/cloudflare`.

Do not index every internal design document directly. Keep AI Search content
focused on what users can do now, what is explicitly planned, and where to find
more detail. Do not present a planned feature as released.

Remote sync must remain low-load: compare remote content and upload only changed
documents, batch related edits, and do not recreate the AI Search instance.
Normally rely on Cloudflare's scheduled incremental indexing. Use one explicit
`--trigger-index` job only when a user-facing correction or requested update
needs prompt indexing; do not poll or trigger jobs in a tight loop.
