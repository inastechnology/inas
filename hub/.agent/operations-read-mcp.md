# Read field records and images through Operations and MCP

This living ExecPlan follows `hub/AGENTS.md` and the architecture layering
policy. The referenced `.agent/PLANS.md` is absent; this file records the plan,
decisions, validation, and remaining operational steps.

## Purpose

Let an AI collect field notes/records, captured camera frames, and record
attachments through Cloudflare machine authentication without using the human
UI, browser APIs, or human credentials. Provide a local stdio MCP adapter over
the same read-only HTTP client.

## Progress

- [x] Inspect existing authentication, Operations routes, field repositories,
  frame storage, attachment storage, clients, and tests.
- [x] Add explicit per-service read grants and deny collector writes.
- [x] Add field/record/camera/image read services and thin Operations routes.
- [x] Add a bounded HTTP read client and a stdio MCP server using the official SDK.
- [x] Verify authorization boundaries, pagination, media delivery, and MCP.
- [x] Update API reference, configuration documentation, and system help.

## Decisions

- Keep `HUB_OPERATIONS_SERVICE_IDS` as the existing device/OTA identity allowlist.
  Add a separate `HUB_OPERATIONS_READ_GRANTS` allowlist mapping collector service
  IDs to scopes and field IDs. Reject identities appearing in both. Removing a
  read grant then revokes access instead of accidentally enabling legacy writes.
  Legacy identities gain no field/image access implicitly. Invalid grants fail closed.
- Reuse repository/storage services rather than proxying browser routes. Never
  return storage keys, camera credentials, or browser image URLs.
- Camera reads are limited to saved frames from cameras currently assigned to
  the authorized field. No live capture or camera control is exposed.
- Return bounded paginated metadata and fetch image bytes separately. Use
  stable IDs and explicit timestamps for incremental collection. Document
  existing history retention limits and deletion-sync limitations.
- Keep MCP dependencies isolated from the running Hub and expose stdio only.
  The adapter holds the Service Token, rejects HTTP redirects, and returns
  actual image content rather than a human-only URL.
- Preserve pre-existing edits in `web_server.py`, device UI, OTA tests, and
  installation help. No production reconfiguration or deployment is needed
  to build and test this change; activation requires a deployed API and a
  configured collector identity.

## Validation

Use temporary repositories and mocked storage/JWT verification, never real
farm data or secrets. Test reader write denial, legacy compatibility, field
isolation, scope enforcement, malformed grants, safe paths, sanitized metadata,
pagination/filtering, image bytes, client redirect refusal, and a real MCP
initialize/list-tools/call-tool exchange. Run focused tests, the full Hub
unittest suite with dotenv disabled, and Ruff. Verify document links and diff
whitespace. Record actual results here.

## Discoveries

- Notes and daily records use separate `notes` and `events` arrays, each capped
  at 1,000 records. Existing search normalizes both.
- Record attachments live in R2; timelapse camera frames live on the Hub disk.
- Field layout bindings and legacy `camera_device_ids` both exist.
- The existing client follows redirects and echoes HTTP error bodies; the
  shared transport needs bounded responses and redacted errors before MCP use.
- Hub environment keys must also appear in `configuration_cli.FIELDS`; the full
  suite caught the initial omission and the catalog was updated.
- Run Hub discovery from `hub/` so tests importing `tests.*` resolve correctly.
- The sandbox stalls the SDK's subprocess stdio transport; the same four tests
  passed outside the sandbox with a 45-second timeout and fake credentials.
  No test called a live Operations endpoint.

## Validation results (2026-09-23)

- Focused Operations/API/client tests: 33 passed, including legacy OTA behavior.
- `cd hub && PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest discover -s tests`:
  594 tests passed. No production credentials or data were used.
- MCP SDK 1.30.0, installed in a separate locked project environment: 4 tests
  passed, including a real stdio subprocess initialize/tools-list exchange,
  record calls, image contents, and tool errors.
- Ruff 0.16.8 checks passed on new/changed code; `field_repository.py` retains
  the pre-existing PLR0917 warning on `_record_search_match`, so that file was
  checked with only PLR0917 ignored. Formatting passed for all 13 Python files.
- All 36 relative links in changed/new Markdown documents resolve.

## Outcomes

The implementation includes read-only per-field grants, paginated note/event
collection, saved camera frame discovery/download, note/event attachment
download, an HTTPS client, and six stdio MCP tools. Reader revocation cannot
turn into writer permission. Host configuration, setup instructions, API
contracts, and Japanese system help describe both current scope and limits.

Production activation remains an operational step: deploy the Hub, create a
dedicated collector Service Token/Service Auth policy, configure allowed field
IDs and scopes, then connect the caller's MCP with its own protected credential
file. No live settings, Cloudflare resources, or production services were changed.
