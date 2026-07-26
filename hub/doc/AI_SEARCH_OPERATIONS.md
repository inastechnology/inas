# AI Search Documentation Status

Japanese detailed guide: [jp/AI_SEARCH_OPERATIONS.md](jp/AI_SEARCH_OPERATIONS.md)

The former Hub system-help AI Search experiment is not connected to the current
product. The shared Cloud Hub path and the undeployed Worker, binding, manifest,
evaluation data, and synchronization scripts under `hub/cloudflare` were
removed when the architecture moved to managed Local Hubs.

The curated, user-facing Markdown documents under `hub/doc/system-help/` remain
the source material for system help. Keep them focused on what users can do now,
what is explicitly planned, and where to find more detail. Do not present a
planned feature as released.

Do not recreate the previous synchronization path or operate the unused R2 and
AI Search resources from this repository. Productizing documentation search
requires an explicitly approved redesign with:

- an authenticated standalone service or an optional Local Hub connector;
- authorization and tenant isolation independent of customer operational data;
- an explicit document publication and deletion workflow;
- retention, observability, and low-load indexing rules; and
- retrieval evaluation that distinguishes released and future behavior.

See [the archived experiment record](../.agent/system-help-ai-search.md) for the
original evaluation and the decision to disconnect it.
