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
