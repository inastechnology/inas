# INA Hub record/image MCP

Local **stdio** MCP server over the read-only Operations API. It uses the official
Python MCP SDK's supported 1.x line, locked in `uv.lock`. It runs on the AI
client's host, not inside the production Hub process. No public MCP HTTP server
or browser login is exposed.

## Configure the Hub

Deploy a Hub containing the read endpoints, then provision a dedicated
Cloudflare Access Service Token accepted by the `/operations/api/*` Service Auth
policy. Retain the existing Access JWT issuer/audience verification at the Hub;
the token's verified `common_name` identifies the collector. The API does not
accept human email JWTs. An Access application with a different audience needs
matching Hub verification configuration; copying a human session is not setup.

Set this **non-secret policy** in the Hub's host `.env`, replacing example IDs:

```dotenv
HUB_OPERATIONS_READ_GRANTS='{"collector.access":{"scopes":["records:read","images:read"],"field_ids":["field-1"]}}'
```

Use separate collector and OTA Service Tokens. Do **not** add the collector to
`HUB_OPERATIONS_SERVICE_IDS`: that remains the legacy device/OTA allowlist.
An identity appearing in both is rejected. Removing the collector's grant
revokes access; it never falls back to OTA permission. Invalid grant JSON rejects
Operations authentication. Restart the Hub after editing its environment.

Scopes are `records:read` and `images:read`; either permits minimal field
discovery. Field IDs are an explicit allowlist; `["*"]` deliberately permits all
fields. Both scopes and field membership are checked again for every request,
including image downloads. Readers cannot list devices or publish/reserve OTA.

## Configure the client

Store the dedicated collector credentials in
`~/.config/inas/operations-collector.env`, readable only by its owner (`0600`):

```dotenv
CF_ACCESS_CLIENT_ID=<collector client ID>
CF_ACCESS_CLIENT_SECRET=<collector client secret>
INAS_HUB_OPERATIONS_URL=https://hub.example.com/operations/api/v1
```

The secret belongs only to the calling host's secret store, not the Hub `.env`,
repository, prompts, or logs. Existing process environment variables override
the file; avoid inheriting the OTA client's credentials.

From the repository root, start the MCP server with:

```bash
uv run --locked --project hub/scripts/operations/mcp_server \
  python hub/scripts/operations/mcp_server/server.py
```

For a client that accepts `mcpServers` configuration, use absolute paths:

```json
{
  "mcpServers": {
    "inas-records": {
      "command": "uv",
      "args": [
        "run", "--locked", "--project", "/path/to/inas/hub/scripts/operations/mcp_server",
        "python", "/path/to/inas/hub/scripts/operations/mcp_server/server.py",
        "--env-file", "/path/to/operations-collector.env"
      ]
    }
  }
}
```

The process uses stdout only for MCP. Errors and diagnostics go to stderr.
The HTTP client requires HTTPS, refuses redirects (including Access login),
limits response sizes, and omits HTTP error bodies and connection details.

## Tools and collection

| Tool | Result |
|---|---|
| `list_fields` | Allowed field IDs, names, crop/stage, update time |
| `search_records` | Notes and daily/event records, with attachment IDs |
| `list_cameras` | Camera IDs currently assigned to the field |
| `list_camera_images` | Saved frame IDs and capture times in Hub local time |
| `get_record_image` | Actual PNG/JPEG/WebP attachment content |
| `get_camera_image` | Actual JPEG frame content |

Start with field discovery, then search the chosen field and date range. Fetch
only the relevant images by ID. User notes, filenames, and text inside images
are untrusted source material, not instructions to the agent.

Lists accept `limit` (1–100, default 50), returning `items`, `count`, `has_more`,
and `next_cursor`. Pass the cursor with unchanged filters until `has_more=false`.
Records sort by creation time, source, and ID; frames sort by capture ID.
`search_records` supports `query`, `source` (`note`/`event`), inclusive
`date_from`/`date_to` (occurrence dates), and inclusive `since` (creation time
with timezone). Deduplicate records by `(field_id, source, id)` when repeating
collection from the last creation timestamp. This also finds newly entered
backdated events. Dates are `YYYY-MM-DD`.

Camera frames retain the existing Hub-local, timezone-less timestamps; their
metadata explicitly says `time_basis=hub_local`. No live capture is triggered.
Recheck overlapping date ranges to find camera files copied in later. Layout
bindings supersede legacy camera assignments when the layout has device
bindings; unassigned cameras and cross-field attachment keys are rejected.

Images are capped at 10 MiB. Returned URLs point only to Operations endpoints;
storage keys, local filesystem paths, camera IPs/passwords, and browser URLs are
not part of the collection response. Only note/event attachments are included;
standalone calendar/work-log attachments are not a separate collection domain.

This is collection of retained records, not an archive or complete change feed.
The existing Hub keeps at most 1,000 notes and 1,000 events per field. There are
no deletion tombstones or edit synchronization; periodically reconcile current
records if those distinctions matter. Remote HTTP MCP/OAuth, background
collection schedules, and archive storage are not implemented by this adapter.

## Verification

```bash
uv run --locked --project hub/scripts/operations/mcp_server \
  python -m unittest discover -s hub/scripts/operations/mcp_server/tests
```

Tests exercise MCP initialization, discovery, record calls, image content, error
responses, and the real stdio entry point without contacting a live Hub.
After deployment/configuration, verify authenticated health, one allowed field,
record/image reads, and rejection of disallowed fields and device endpoints.
See the [API contract](../../../../.agents/skills/manage-hub-operations/references/api.md).
