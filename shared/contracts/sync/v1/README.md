# INAS Parent/Child Sync Protocol v1

Sync v1 is the storage-independent HTTPS contract between one child node and its immediate parent. A child is an Edge Gateway or a Local Hub, and its parent is a Local Hub. MQTT never crosses this boundary.

The child initiates every exchange:

```text
POST /sync/v1/nodes/{node_id}/exchange
Content-Type: application/json
Content-Encoding: gzip (optional)
```

Authentication happens before payload processing. The authenticated node ID must equal both the path node ID and `body.node_id`; the server must not accept `tenant_id`, a database URL, or a parent override from this payload. A Local Hub may forward events created by its registered descendants, so each event carries an `origin_node_id`. The parent verifies that every origin belongs to the authenticated sender's subtree.

## Delivery rules

- Events and command results are delivered at least once. The child retains them until their IDs appear in the corresponding acknowledgement array.
- `event_id`, `result_id`, and `command_id` are stable lowercase UUIDv4 values. Replaying an identical ID and body is a no-op. Reusing an ID with different content is a conflict and must be audited.
- `sequence` is monotonically increasing per `origin_node_id`. It assists ordering and gap detection; it is not a global sequence.
- Desired resources are durable state. A larger positive `revision` replaces an older revision. The same revision with a different `content_sha256` is a conflict. An older revision is ignored.
- Commands are ephemeral actions. Every command has `expires_at`; an expired command is recorded as expired and is never executed after reconnection.
- The parent may resend a command until it receives a result. The child stores the command before execution and uses `command_id` for idempotency.
- `next_cursor` is opaque to the child. It is committed locally only after the complete response has been durably stored.
- A request contains at most 500 events and 200 command results. A response contains at most 500 desired-resource changes and 100 commands. The HTTP implementation also enforces a 1 MiB decompressed body limit.

`content_sha256` is a revision fingerprint minted and persisted by the configuration authority. A receiver treats it as an opaque 64-character SHA-256 value and also compares the decoded payload when detecting a same-revision conflict. It is not an authentication mechanism and recipients do not recompute it across languages; HTTPS authentication and the node credential protect transport integrity. A retry of the same revision must carry the exact same fingerprint and payload.

`health.outbox_depth` is the total number of unacknowledged events and command results, including items not selected for the current bounded batch.

## Direction of authority

Telemetry, status, audit events, and command results move upward. Desired config, device assignment, firmware target, node policy, and commands move downward. A node has exactly one immediate parent. A managed subtree has one configuration authority at a time; Sync v1 is not a generic multi-master database replication protocol.

The protocol is intentionally independent of Turso. Edge Gateway and Local Hub clients store local state in SQLite and know only their parent HTTPS URL and node credential. The parent Local Hub resolves an authenticated child through its local hierarchy repository; callers cannot choose a database or tenant route.

## Schema and vectors

`sync.schema.json` is a Draft 2020-12 JSON Schema. The root accepts either a request or a response; named definitions `syncRequest` and `syncResponse` are used by conformance tests.

`vectors/manifest.json` lists valid and invalid examples. Runtime implementations in Python and TypeScript must run the same vectors. Payload objects are deliberately extensible, while envelope and routing fields reject unknown properties.

Timestamps are RFC 3339 UTC values. Production implementations normalize them to a `Z` suffix on output and accept valid offset input only at API parsing boundaries.
