# AI Search Documentation Operations

Japanese detailed guide: [jp/AI_SEARCH_OPERATIONS.md](jp/AI_SEARCH_OPERATIONS.md)

The Hub system-help AI Search indexes curated, user-facing Markdown documents
from `hub/doc/system-help/`. It must not ingest every internal design document
or present planned behavior as released.

The manifest and retrieval evaluation live under `hub/cloudflare/data/`.
Validate a change locally with:

```bash
cd hub/cloudflare
npm run system-help:sync -- --dry-run
```

Normal remote sync compares each R2 object and uploads only changed or missing
documents. Cloudflare's scheduled incremental indexing handles routine updates.
For a requested user-facing correction that should be searchable promptly, add
one explicit indexing job after the batched upload:

```bash
npm run system-help:sync -- --trigger-index
```

Do not recreate the AI Search instance, upload unchanged files, trigger jobs
when no file changed, or poll indexing in a tight loop.
