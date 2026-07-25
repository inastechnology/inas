# Cloud Hub multi-tenant security boundary

## Invariants

1. A URL, query, header, or JSON body supplied by a caller never directly
   chooses a Turso URL or token.
2. Browser access requires a valid Cloudflare Access application JWT with the
   configured issuer and audience, `type=app`, an Access subject, normalized
   email, and valid `nbf`/`iat`/`exp` claims. Membership requires both email and
   the pinned Access subject for the requested public tenant ID.
3. Edge Sync requires a registered active node and one of its unexpired,
   independently revocable random bearer tokens. Browser/Access credentials
   cannot substitute for node credentials.
4. The directory-selected internal tenant record is the only input to tenant
   DB client creation.
5. Every customer receives a separate Turso DB and a database-scoped token.
   Tenant DB tables contain no cross-tenant routing column.
6. Edge and Local Hub devices never receive directory or tenant DB
   credentials.

## Request resolution

| Request | Authenticated principal | Tenant resolution | Rejected input |
|---|---|---|---|
| `/api/tenants` | Access JWT email + subject | active memberships for identity | caller roles or tenant IDs |
| `/api/t/:publicId/*` | Access JWT email + subject | active membership for identity + public ID | internal tenant ID, DB URL/token |
| `/sync/v1/nodes/:nodeId/exchange` | registered node bearer | active node record -> internal tenant | `tenant_id`, DB URL/token, path/body mismatch |

Unknown and unauthorized tenant URLs return the same `404` response. Node
authentication runs before content type, decompression, JSON parsing, or tenant
DB access. Sync accepts only strict JSON, optionally gzip encoded, and limits
both declared/compressed input and decompressed input to 1 MiB.

The first successful tenant resolution binds a pre-created email membership to
the current Access `sub`. A later token with the same email but another subject
cannot use the membership. An administrator must use the audited
`reset-subject` recovery operation after independently verifying an identity
recreation.

Browser mutation requests additionally require an exact
`Origin: https://cloud-hub.inas-technologies.com`. This is defense in depth for the
Access application cookie and is not a replacement for Access authentication.

## Stored credentials

- Directory Turso token: Worker secret.
- Tenant credential master key: independent 32-byte Worker secret.
- Tenant DB token: AES-256-GCM v2 ciphertext in the directory DB, authenticated
  with the internal tenant UUID, database name, and normalized Turso URL.
- Node token: 256 random bits encoded as exactly 43 URL-safe characters,
  delivered once in the factory overlay; only a random salt and SHA-256
  verifier are stored.
- Turso Platform token: factory process environment only.

Only exact `libsql://*.turso.io` database origins are accepted. Because the
encrypted token is also bound to the stored tenant UUID/name/URL, changing a
directory row cannot redirect the decrypted token to another host or database.
Compromise of only the directory DB does not reveal plaintext tenant DB or node
credentials. Compromise of both the directory DB and Worker master key can
reveal tenant DB tokens, so Cloudflare secret access and Turso directory access
must be separated operationally and audited.

The printed AP QR may contain only the local setup SSID/password, and the
customer URL QR may contain only the public Cloud Hub path. A QR must never
contain a node bearer, internal tenant ID, database routing value, or
Cloudflare/Turso administrative credential.

`credential_key_version=2` is enforced. Do not replace
`TENANT_CREDENTIAL_MASTER_KEY` in place: a planned rotation must decrypt each
tenant credential with its authenticated routing context, encrypt it with a new
version/key, verify it, and only then retire the old key. Version 1 is rejected.

## Persistence, replay, and input safety

Sync event identity is unique by both event UUID and
`(origin_node_id, sequence)`. Exact retries are acknowledged without another
insert. Reusing either identity with different canonical content returns `409`
before health or other request data is written. Command result IDs use the same
exact-retry rule. A command result is accepted only when its referenced command
belongs to the authenticated node.

Only desired resources and unexpired pending commands targeting the
authenticated node are returned. The current Cloud Hub accepts direct Edge
Gateway origins only; forwarding arbitrary descendants requires an explicit
directory route model and is intentionally rejected.

Nested JSON payloads have bounded depth, node count, collection size, key
length, and string size. Prototype-mutating keys and non-JSON object types are
rejected before canonicalization or persistence.

## Cloudflare controls

- One exact Worker custom domain: `cloud-hub.inas-technologies.com`.
- One browser Access application on `/api/*`.
- No per-customer Worker or Cloudflare secret.
- No Access Bypass policy for `/sync/*`; the endpoint is outside the browser
  application and enforces node auth itself.
- Worker rate-limit bindings fail closed and constrain both each node ID
  (20/minute) and each source address (120/minute) before directory lookup.
  The source limit prevents random node IDs from bypassing the node bucket.
- Security events are written as sanitized structured Worker audit logs. A
  separate binding limits Discord delivery to one event per normalized class
  and route per minute without suppressing the underlying audit record.
- WAF rules should additionally constrain malformed traffic and volumetric
  attacks before Worker execution.
- `workers.dev` and preview URLs are disabled.

Static assets are public but contain no customer data. API responses use
`Cache-Control: no-store`, including failures. The Worker emits restrictive
CSP, HSTS, cross-origin isolation, frame denial, no-sniff, referrer, and
permissions headers even when authentication fails.

Configure the Access application token with HttpOnly, SameSite `Lax`, and a
Binding Cookie, then choose a short session lifetime suitable for agricultural
operations. Never configure a Bypass policy for `/api/*` or `/sync/*`.

## Authorization and recovery invariants

- `reader` can view; `operator` can create management events; `admin` is
  reserved for membership and future tenant administration.
- Directory triggers prevent removal, deletion, or demotion of the final active
  admin.
- A node may have up to two usable credentials during rotation. Expired
  credentials do not authenticate and do not consume the overlap allowance.
- Directory triggers prevent revoking or deleting the final unexpired active
  node credential.
- Authentication rejection logs contain only the auth class, normalized route,
  bounded method, status, event ID, timestamp, and Cloudflare Ray ID. They do
  not contain email addresses, IP addresses, query strings, tokens, or request
  bodies. Discord receives only the same sanitized fields.

## Availability and billing

MQTT, cached configuration, and safety-critical action remain on the Edge
Gateway or Local Hub. WAN, Cloud Hub, trial, or subscription failures must not
disable local safe operation. Future entitlement enforcement belongs at Cloud
view/management operations and must never be inserted into the field MQTT
control loop.
