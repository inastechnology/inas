# Build the hierarchical Edge, Local Hub, and Cloud Hub platform

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

`hub/AGENTS.md` requires an ExecPlan for this work. The referenced repository-root `.agent/PLANS.md` is not present in this checkout, so this plan follows the existing `hub/.agent/` convention and embeds all instructions and decisions needed to continue safely.

## Purpose / Big Picture

INAS supports existing Local Hubs, a shared Cloud Hub, and small Edge Gateways
without changing the MQTT contract used by field devices. A Local Hub directly
controls devices, aggregates optional child Gateways, and keeps its existing
per-installation Turso/libSQL configuration. Cloud Hub runs one Cloudflare
Worker/frontend and assigns one dedicated Turso DB to each customer.

After this plan is complete, an operator can use either Local Hub or Cloud Hub
to see the Edge Gateways and devices under that Hub. A disconnected Edge
Gateway answers config requests from local cache and uploads its SQLite backlog
after HTTPS returns. An Edge has one parent and receives no Turso credential.
Existing `INADS-<UUIDv4>` IDs and MQTT topics continue to work.

## Progress

- [x] (2026-07-23 11:15+09:00) Inspected the current Hub startup, MQTT handling, device configuration persistence, Turso connector, Cloudflare Worker prototype, firmware ID generation, and Raspberry Pi/SORACOM constraints.
- [x] (2026-07-23 11:37+09:00) Published the entity-ID and hardware-profile specification, including compatibility rules for existing devices.
- [x] (2026-07-23 11:37+09:00) Added versioned Sync v1 JSON Schema plus valid and deliberately invalid conformance vectors, including rejection of caller-selected tenant/database routing.
- [x] (2026-07-23 11:37+09:00) Added the standard-library-only `ina-edge-runtime` Python package with identity validation, MQTT topic parsing, durable SQLite outboxes, desired-resource revision handling, expiring command intake, and Sync request construction.
- [x] (2026-07-23 11:37+09:00) Ran 21 Edge Runtime/contract tests and 25 focused existing Hub MQTT/config tests without modifying the existing wire behavior.
- [x] (2026-07-23 11:42+09:00) Added a locked Python 3.11 Edge Runtime CI job that lints, checks formatting, runs the shared contract tests, and builds both wheel and source distributions.
- [x] (2026-07-23 11:50+09:00) Added the locked `ina-edge-runtime` Hub dependency, a repository symlink to its canonical source, and installer materialization so copied production deployments do not depend on that symlink.
- [x] (2026-07-23 11:50+09:00) Delegated Local Hub MQTT topic parsing to the shared Runtime without changing topics, payload dictionaries, QoS, retain behavior, or configuration reply timing.
- [x] (2026-07-23 11:52+09:00) Hardened the SQLite store for concurrent MQTT/Sync threads, resumable accepted commands, activation-time expiry checks, and entity-typed desired-resource IDs; 23 shared tests pass.
- [x] (2026-07-23 13:28+09:00) Added the persistent Local Hub `INALH` identity and an embedded Edge Runtime adapter that mirrors effective runtime config into revisioned SQLite while retaining the existing JSON fallback and short MQTT reply path.
- [x] (2026-07-23 13:31+09:00) Exposed restart-safe event enqueue/list/ack operations through the same Local Hub adapter; parent-bound emission remains gated until a Sync client exists so standalone Hubs cannot accumulate an unbounded outbox.
- [x] Integrate `ina-edge-runtime` into the Local Hub behind existing service interfaces.
- [x] (2026-07-23 15:28+09:00) Built the standalone `edge-gateway/` service with provisioned identity loading, local MQTT control, persistent outboxes, bounded authenticated Sync transport, expiring commands, sanitized maintenance health, and systemd watchdog notification.
- [x] (2026-07-23 15:28+09:00) Added Raspberry Pi/Compute Module appliance fixtures for isolated Wi-Fi, DHCP, NTP, Mosquitto credentials/ACLs, nftables, disabled forwarding, persistent state, optional SORACOM, and a non-destructive manifest-producing bundle stage.
- [x] (2026-07-23 15:28+09:00) Validated 26 shared Runtime tests, 21 Edge Gateway tests, both Python distributions, a 48-file staged frozen install, and all 411 existing Hub tests.
- [x] Build the standalone `edge-gateway/` service and appliance configuration.
- [x] (2026-07-23 17:23+09:00) Added one-time child enrollment, salted credential digests, revocation, explicit subtree routes, idempotent child event/result intake, downstream desired-state and command routing, and the separately authenticated bounded Sync v1 HTTP endpoint.
- [x] (2026-07-23 17:23+09:00) Added the outbound Local Hub parent client, first-success emission gate, child backlog forwarding with original origin identity, authoritative parent runtime config for direct devices, and multi-hop Local Hub-to-Local Hub-to-Edge coverage.
- [x] (2026-07-23 17:34+09:00) Validated 28 shared Runtime tests, 23 Edge Gateway tests, 433 Hub tests, all three Python distributions, a materialized frozen Hub deployment, and a secret/cache-free Hub source distribution.
- [x] Make the Local Hub a Sync v1 parent for child Edge Gateways and an optional child of another Local Hub.
- [x] (2026-07-23) Replaced the retired single-DB Worker prototype with
  `hub-cloud/`: one shared Worker, Access JWT plus membership authorization, a
  directory Turso DB, and one encrypted/scoped Turso credential and dedicated
  DB per customer.
- [x] (2026-07-23) Added separately authenticated Cloud Sync v1 intake with
  auth-before-body parsing, strict 1 MiB gzip/JSON bounds, caller-routing-field
  rejection, idempotent event/result persistence, node health, desired state,
  and command delivery.
- [x] (2026-07-23) Added interactive directory bootstrap, tenant provisioning,
  and Edge Gateway shipment tools. Gateway output contains only its identity,
  parent bearer, local MQTT credentials, appliance configuration, an AP Wi-Fi
  QR, and a non-secret customer URL QR.
- [x] (2026-07-23) Restored Local Hub's required, independent Turso settings and
  removed the mistaken managed-Local-Hub shipment/local-only DB workflow.
- [x] (2026-07-23) Validated 32 Cloud Hub tests, a zero-vulnerability npm
  audit, TypeScript, Wrangler dry-run packaging, 28 shared Runtime tests, 23
  Edge Gateway tests, and all 433 Local Hub regressions.
- [x] (2026-07-23) Split the live Local Hub and Cloud Hub Cloudflare Access
  groups, enabled Directory DB delete protection, and added idempotent
  inspection/apply scripts for both controls.
- [x] (2026-07-23) Completed a live Directory DB PITR drill: the isolated
  two-minute recovery passed integrity, exact schema hash, and core table-count
  checks, then the verified temporary database was removed.
- [x] (2026-07-23) Added sanitized structured security audit events and
  rate-limited Discord alerts for origin-visible authentication,
  authorization, CSRF, oversized-request, and rate-limit rejections.
- [x] (2026-07-23) Added the protected persistent Cloud Hub regression tenant
  and crash-safe per-run ephemeral tenant lifecycle, including exact-manifest
  cleanup guards, deprovisioning-aware database triggers, and the operator
  runbook.
- [x] (2026-07-23) Passed three live isolated tenant regressions. The final run
  covered both token-crossing directions, routing-field rejection, Sync
  retry/conflict/desired-state/command behavior, deployed-origin Sync for both
  tenants, bidirectional Access membership denial, and Turso database-token
  isolation. The non-regression Directory snapshot was unchanged and the
  ephemeral DB, Directory rows, run nodes, fixtures, and manifest were removed.
- [ ] Add subscription/trial entitlements outside the safety loop, signed appliance updates, fault-injection tests, and hardware-in-the-loop release checks.

## Surprises & Discoveries

- Observation: the current runtime-config path must remain entirely local to the MQTT controller.
  Evidence: `hub/doc/spec/jp/mqtt-server-spec.md` says firmware waits only about five seconds for a config reply, while `hub/src/ina_device_hub/device_config_service.py` deliberately publishes before remote event persistence.
- Observation: current Hub persistence is split across JSON files, JSONL fallback logs, and libSQL/Turso, so raw database replication cannot be a safe parent-child protocol.
  Evidence: device config lives in `.device_configs.json`; measurements and events use `InaDBConnector`; event logging falls back to JSONL.
- Observation: existing firmware uses the same historical `INADS-` prefix for sensors and actuators and carries the actual product role separately in `APP_DEVICE_KIND`.
  Evidence: `client-devices/common/lib/ina-client-common/src/app/inc/app_config.h` generates `INADS-<UUIDv4>`, while each `platformio.ini` defines `APP_DEVICE_KIND` such as `WTR`, `ENV`, `SOI`, `WRS`, or `FGT`.
- Observation: the MQTT specification still mentions a 512-byte management warning, while firmware and Hub validation currently accept payloads below 4096 bytes.
  Evidence: `APP_MQTT_INBOUND_PAYLOAD_MAX_SIZE` is 4095 and `validate_device_config` rejects payloads at 4096 bytes. The older 512-byte wording must be reconciled before changing the wire contract.
- Observation: the worktree already contains unrelated user changes, including Hub UI and documentation changes.
  Evidence: `git status --short` was non-empty before this plan. All work under this plan must avoid overwriting or formatting unrelated files.
- Observation: the current Hub production installer copies only the `hub/` subtree, while the common Runtime currently lives at repository-level `shared/edge-runtime/`.
  Evidence: `hub/scripts/install_service.sh` computes its copy root as `hub/` and then runs `uv sync --frozen` in the copied target. Adding a naive `../shared/edge-runtime` path dependency would pass in the monorepo checkout but fail on deployed appliances.
- Observation: existing Local Hub installations have a historical `inahub-*` machine label but no production `INALH` synchronization identity.
  Evidence: `setting.get_device_id()` derives the historical label from CPU or MAC information. The embedded adapter now creates one immutable UUIDv4 `INALH` identity in `WORK_DIR/edge-runtime/identity.json`; manufactured appliances will provision the same identity class before shipment.
- Observation: automatically copying every Local Hub event into an outbox before a parent Sync client exists would grow storage forever on standalone installations.
  Evidence: Edge Store events remain pending until their stable IDs are explicitly acknowledged. Milestone 2 therefore exposes and tests the durable adapter but does not turn ordinary Local Hub audit logging into parent-bound events; enrollment and emission are activated together in Milestone 4.
- Observation: WSL's inherited default temporary directory is backed by a Windows mount that reports files as mode `0777`, even after `chmod(0600)`.
  Evidence: the identity permission test failed only with the inherited temporary directory and passed with `TMPDIR=/tmp`; the same filesystem behavior was already observed in the full Hub suite. Production Edge state uses a Linux filesystem, systemd `StateDirectoryMode=0700`, and `UMask=0077`.
- Observation: an MQTT root wildcard does not reliably cover `$SYS` topics, so the trusted Gateway service account needs an explicit broker-log read ACL.
  Evidence: the Gateway subscribes to `$SYS/broker/log/#`; the appliance ACL now lists that topic separately and has a regression assertion.
- Observation: this development container can validate appliance policy but cannot perform a real AP/broker integration run.
  Evidence: Mosquitto, NetworkManager, dnsmasq, and chrony executables are absent. `systemd-analyze verify` parses the unit and reports only the intentionally uninstalled `/opt/inas/.../ina-edge-gateway` executable; `nft --check` cannot initialize netlink without the required container capability. Hardware-in-the-loop validation remains a Milestone 6 release gate.
- Observation: adding new `.default.env` fields without adding them to the configuration CLI catalog fails an existing full-suite consistency test.
  Evidence: the first 429-test Milestone 4 run failed only `test_configure_catalog_covers_default_env`; adding the optional `上位Hub Sync` section and all seven fields made the focused and full suites pass.
- Observation: the descriptive `reg-ephemeral-<run-id>` public ID exceeded the
  Cloud Hub's 32-character public-route contract.
  Evidence: the run ID itself is 25 characters, so the public prefix was
  shortened to `reg-e-` while the Turso DB name and customer reference retain
  their descriptive `regression-ephemeral` forms. The resulting 31-character
  ID passes the same production route parser.
- Observation: the Hub source-distribution builder was traversing the Hub-local `.uv-cache` because the repository-root VCS ignore rules did not exclude that nested cache.
  Evidence: the first `uv build` produced an invalid 177 MB tarball containing cached virtual-environment symlinks. An explicit Hatch sdist `only-include` boundary reduced it to 8.1 MB, successfully rebuilt a wheel from the sdist, retained `shared/edge-runtime`, and excluded `.env`, `.data`, `.venv`, and `.uv-cache`.

## Decision Log

- Decision: keep Local Hub and Cloud Hub as separate control-plane
  applications over the same Edge Sync contract. Local Hub retains its current
  Turso/libSQL configuration; Cloud Hub uses one Worker plus a dedicated Turso
  DB per customer.
  Rationale: existing Local Hub operation remains stable while customers who
  cannot run one receive a managed view without cloud MQTT.
  Date/Author: 2026-07-23 / Codex and user.
- Decision: every synchronizing node has exactly one immediate parent, and every managed subtree has exactly one configuration authority at a time.
  Rationale: dual parents or dual writers create configuration conflicts and unsafe duplicate commands.
  Date/Author: 2026-07-23 / Codex and user.
- Decision: Sync v1 is an application-level HTTPS protocol. Edge Gateway and Local Hub nodes never receive Turso URLs, Turso tokens, or Cloudflare administrative credentials.
  Rationale: this keeps the Edge independent of cloud storage, limits credential exposure, and lets an Edge synchronize with either Local Hub or Cloud Hub.
  Date/Author: 2026-07-23 / Codex and user.
- Decision: preserve `INADS-<UUIDv4>` as the production client-device identity. Add `INAEG-<UUIDv4>` for physical Edge Gateways and `INALH-<UUIDv4>` for Local Hub nodes. Prefixes identify entity class only; hardware, tenant, site, region, and device kind remain separate fields.
  Rationale: existing firmware and MQTT topics remain compatible, and devices can be moved, upgraded, or reassigned without changing identity.
  Date/Author: 2026-07-23 / Codex.
- Decision: physical identities use UUIDv4 because they can be generated safely without a valid clock. Cloud-created business records may use UUIDv7 later, but they never appear in the device MQTT contract.
  Rationale: a new field device or Gateway may boot before NTP is available.
  Date/Author: 2026-07-23 / Codex.
- Decision: separate the farming hierarchy (`organization`, `site`, `field`, placement) from the synchronization hierarchy (`node`, `parent_node_id`).
  Rationale: one Gateway may serve multiple fields, and changing network topology must not rewrite agronomic history.
  Date/Author: 2026-07-23 / Codex.
- Decision: use at-least-once event and command delivery with stable IDs, deduplication, monotonically increasing desired-resource revisions, and command expiry. Do not claim exactly-once delivery.
  Rationale: retries after network failure are unavoidable; idempotent application is testable and safe.
  Date/Author: 2026-07-23 / Codex.
- Decision: the production Edge baseline is an eMMC Compute Module appliance. A Raspberry Pi 5 development kit is allowed for pilots, but removable microSD is not the production persistence target. Standard Edge uses a CM4-class 2 GB/32 GB eMMC wireless module; camera-heavy Edge and Local Hub use a CM5-class 4 GB/32 GB or larger module. LTE is an option attached to the same logical profile.
  Rationale: the standard Edge is a low-compute data pipe, while eMMC, a dedicated device AP, Ethernet or cellular WAN, hardware watchdog, protected key storage, and power-failure tolerance matter more than peak CPU.
  Date/Author: 2026-07-23 / Codex.
- Decision: subscription expiry never enters the local safety loop and never turns an actuator off or on. It may make cloud administration read-only after a grace period, but cached automation continues.
  Rationale: billing state must not create unsafe field behavior.
  Date/Author: 2026-07-23 / Codex.
- Decision: do not integrate the shared Runtime through `PYTHONPATH`, an undeclared import, or a development-only path dependency. Milestone 2 must first make the package part of the locked Hub deployment artifact, then delegate MQTT parsing.
  Rationale: Local checkout success is insufficient if `install_service.sh` produces an appliance that cannot run `uv sync --frozen`.
  Date/Author: 2026-07-23 / Codex.
- Decision: keep `shared/edge-runtime/` as the canonical reusable source, expose it to Hub tooling through `hub/shared/edge-runtime`, and materialize only that verified package into copied Hub deployments.
  Rationale: the common mechanism remains outside the Hub product layer, while the historical Hub-only target layout and frozen production install continue to work.
  Date/Author: 2026-07-23 / Codex.
- Decision: during Milestone 2, `.device_configs.json` remains the Local Hub business-record source of truth and the embedded Edge Store is a revisioned, locally repairable runtime-config cache. Cache failure is logged but falls back to the validated JSON config without contacting Turso or a parent.
  Rationale: this preserves existing installations and the firmware reply deadline while the common offline runtime is introduced incrementally.
  Date/Author: 2026-07-23 / Codex.
- Decision: Local Hub and Cloud Hub may have different frontend implementations
  but should converge on shared contracts and farmer-facing behavior. The
  optional Android product remains a thin shell for QR enrollment, Gateway AP
  setup, kiosk operation, and diagnostics.
  Rationale: Local Hub cannot be destabilized by Cloud multi-tenancy, while
  customers still receive a consistent workflow.
  Date/Author: 2026-07-23 / Codex and user.
- Decision: Local Hub event emission into the Sync outbox starts only after a parent is enrolled and a working Sync client owns acknowledgement and retry. Edge Gateway capture starts locally even in its short-lived unclaimed setup state so device observations survive the claim/restart boundary; production provisioning must claim it before field attachment.
  Rationale: an outbox without a consumer is an unbounded disk leak for indefinitely standalone Local Hubs, while an Edge Gateway is a parent-bound product and must not discard observations during setup or WAN loss.
  Date/Author: 2026-07-23 / Codex.
- Decision: an Edge Gateway may start with `parent: null` only as an explicit unclaimed/setup state. It keeps its MQTT control and cached state local, while authenticated parent claiming and credential delivery belong to the Hub enrollment flow rather than the read-only maintenance API.
  Rationale: initial AP setup must work before WAN or Hub registration, but a mutation-capable unauthenticated setup endpoint would weaken the field-LAN boundary.
  Date/Author: 2026-07-23 / Codex.
- Decision: Milestone 3 executes only `device.runtime_config_push`; all other parent commands produce a durable `rejected` result. A command that was `running` across restart is failed as `execution_interrupted` instead of replayed.
  Rationale: actuator operations need product-specific safety and idempotency definitions before an at-least-once transport may execute them.
  Date/Author: 2026-07-23 / Codex.
- Decision: reject MQTT payloads above 256 KiB before parsing, reject credentials embedded in parent URLs, require private permissions on bearer/MQTT/mTLS-key files, reject HTTPS redirects, and limit both decompressed Sync directions to 1 MiB.
  Rationale: the Gateway is a security boundary exposed to field devices and a remote parent; bounded parsing and non-forwardable credential handling reduce memory, disk, and credential-exfiltration risk.
  Date/Author: 2026-07-23 / Codex.
- Decision: Local Hub child credentials are random one-time bearer values whose salted SHA-256 digests are the only persisted verifier; node Sync authentication is evaluated before reading the request body and is never interchangeable with browser or Cloudflare Access authentication.
  Rationale: a stolen hierarchy database must not reveal usable child credentials, revoked credentials must stop immediately, and attacker-controlled bodies must not consume parsing resources before node authentication.
  Date/Author: 2026-07-23 / Codex.
- Decision: an Edge Gateway may receive only self-targeted desired state and commands, while a Local Hub may receive targets only for descendants explicitly registered to its next-hop route.
  Rationale: node prefixes alone do not establish authority. Explicit routing prevents an authenticated child or compromised parent response from silently crossing managed subtrees.
  Date/Author: 2026-07-23 / Codex.
- Decision: configuring an upstream parent does not activate Local Hub event emission. The first completely validated, durably applied parent response activates emission and backfills already accepted child events/results.
  Rationale: standalone Hubs must not accumulate an unconsumed outbox, while a configured but unreachable or malicious parent must not create data loss or prematurely change local behavior.
  Date/Author: 2026-07-23 / Codex.
- Decision: a parent-delivered direct `device.runtime_config` is authoritative in the embedded Runtime until authority is explicitly changed by a future protocol operation; local business-record edits remain recorded but cannot silently overwrite the effective MQTT reply cache.
  Rationale: hierarchical configuration needs one writer at a time, and WAN loss must retain the last accepted safe field configuration.
  Date/Author: 2026-07-23 / Codex.
- Decision: the Hub sdist traverses only `src`, `shared/edge-runtime`, `README.md`, and `pyproject.toml`.
  Rationale: the package must contain the path dependency needed to build from source while making local databases, credentials, virtual environments, caches, demos, and unrelated workspace artifacts impossible to publish accidentally.
  Date/Author: 2026-07-23 / Codex.
- Decision: a node bearer token is always required for Sync v1; mTLS is an optional additional transport defense and cannot replace the application-level node credential.
  Rationale: the current Local/Cloud Sync endpoint binds authorization to a one-time-enrolled node token. Accepting certificate-only client configuration would create a configuration that can establish TLS but can never authenticate at the Sync application boundary.
  Date/Author: 2026-07-23 / Codex.
- Decision: the first exchange with a newly configured parent contains health but no event/result records. A successful correlated response binds the normalized parent base URL; a changed URL clears the old cursor and requires the empty handshake again before backlog upload.
  Rationale: persisted activation from an earlier parent must not send field data to a replacement endpoint before the new TLS and node-credential boundary is proven, and parent cursors are not portable across endpoints.
  Date/Author: 2026-07-23 / Codex.
- Decision: parent desired-resource revisions are monotonic in both the hierarchy repository and the embedded direct-device cache.
  Rationale: ignoring a stale revision in the control-plane database is insufficient if the MQTT-facing cache can still be rolled back independently.
  Date/Author: 2026-07-23 / Codex.
- Decision: release regression uses one delete-protected persistent test
  tenant and one unpredictable, newly provisioned ephemeral tenant per run.
  The ephemeral tenant is set to `deprovisioning` before credential/data
  cleanup and may be deleted only from a mode-`0600` external manifest whose
  internal UUID, public ID, DB name, and customer reference all match.
  Rationale: two real database boundaries are required to prove bidirectional
  isolation, while fixed production-like test data or name-only cleanup would
  make destructive mistakes and cross-run contamination possible.
  Date/Author: 2026-07-23 / Codex and user.

## Outcomes & Retrospective

Milestones 0 and 1 are complete. Production ID validation, Sync v1 envelopes, negative tenant-routing vectors, thread-safe SQLite retry/deduplication, desired-revision conflicts, resumable command intake, command expiry at execution activation, cursor persistence, and schema-conformant request construction are implemented. The shared suite passes 23 tests on Python 3.11, and the package builds as a wheel and source distribution.

Milestone 2 is complete with a production-safe package boundary, MQTT-parser delegation, persistent Local Hub identity, runtime-config caching, and durable event-outbox adapter operations. A temporary copied deployment successfully completed `uv sync --frozen --no-dev` and imported the materialized Runtime. The shared suite passes 23 tests, the Local Hub cache/outbox/MQTT focus passes 31 tests, and the full Hub suite passes 411 tests when the Linux `/tmp` filesystem is selected. An earlier run against the WSL-mounted Windows temporary directory produced six expected permission-mode failures because that filesystem reports created files as `0777`. Automatic Local Hub event emission intentionally begins with the parent Sync client in Milestone 4.

Milestone 3 is complete at the software and appliance-fixture level. The standalone process preserves the current device-facing config reply contract during parent outages, persists telemetry and command results, validates correlated/targeted Sync responses before acknowledgement, retries without deleting unacknowledged data, and never treats WAN or subscription state as local readiness. The shared suite passes 26 tests, the Gateway suite passes 21 tests, both packages build wheel and source distributions, a staged 48-file bundle installs from its frozen locks and imports both packages, and all 411 Hub regressions remain green. Actual radio/AP, Mosquitto, NetworkManager, SORACOM, watchdog, and power-failure behavior still requires the planned Compute Module hardware-in-the-loop gate; no claim of that physical validation is made here.

Milestone 4 is complete at the API, persistence, routing, and software-integration level. Local Hub now accepts separately authenticated Sync v1 exchanges from registered Edge or Local Hub children, retains stable origin identities through multiple hops, routes state only through explicit next hops, and may itself synchronize upward without placing WAN state in the local MQTT readiness path. Parent runtime config remains available locally and cannot be rolled back by a stale revision; acknowledgements remove only named durable records; an invalid target/correlation cannot advance the cursor; and a changed parent cannot receive backlog before a fresh empty handshake. The shared suite passes 28 tests, the Gateway suite passes 23 tests, and the full Hub suite passes 433 tests. All three packages build, the materialized Hub layout installs with `uv sync --frozen --no-dev` and imports both Hub and Runtime modules, and the Hub sdist excludes local secrets/state/caches. Physical AP setup, QR scanning, the optional Flutter console, real TLS/reverse-proxy interoperability, and power/network fault testing remain explicit later gates rather than claims of this milestone.

Milestone 5 is complete at the repository and dry-run level. The obsolete
single-DB prototype under `hub/cloudflare/` was replaced by `hub-cloud/`.
Browser requests verify Cloudflare Access before directory access, require an
active email membership, and derive the tenant DB only from the resulting
internal record. Direct Edge Sync authenticates before body parsing and
resolves its customer from the node registry; Cloud Hub rejects Local Hub
origins and caller-selected routing. Customer DB tokens are database-scoped and
AES-GCM encrypted in the directory. Directory/tenant migrations, interactive
bootstrap/provisioning/kitting, protected AP and URL QR output, CI, and the
initial responsive frontend are present. The Cloud suite passes 32 tests,
`npm audit` reports zero vulnerabilities, and Wrangler packaging succeeds
without production credentials. The shared Runtime passes 28 tests, Edge
Gateway passes 23, and Local Hub passes all 433 regressions. Live
Cloudflare/Turso provisioning and physical reboot/WAN-loss checks remain
production acceptance steps because this environment has no production account
authorization or target appliance.

The Cloud Hub release boundary now also has a live, repeatable two-tenant
regression. `regression-baseline` remains active with one administrator and a
delete-protected, empty Turso DB. Each run creates a `reg-e-<run-id>` tenant
before testing and deletes it afterward. The 2026-07-23 final transcript passed
65 local tests and the deployed-origin checks, left zero baseline run records
or nodes, left no cleanup manifest, confirmed both ephemeral databases were
deleted, and recorded no stable Directory change outside regression tenants.

## Context and Orientation

The current Local Hub is the Python package under `hub/src/ina_device_hub/`. `hub/src/ina_device_hub/serve.py` starts Flask, a Paho MQTT client, data-processing threads, camera and weather tasks, and schedulers in one process. `hub/src/ina_device_hub/hub_mqtt_client.py` parses existing MQTT topics. `hub/src/ina_device_hub/device_config_service.py` validates and publishes runtime config, and `hub/src/ina_device_hub/device_config_repository.py` stores device records in a JSON file. `hub/src/ina_device_hub/ina_db_connector.py` stores events and measurements in a local libSQL database and can synchronize it to Turso.

The previous TypeScript/Hono/Turso hosted prototype under `hub/cloudflare/` was
retired because it used one DB without a complete tenant boundary. Its
replacement is the top-level `hub-cloud/` application. Local Hub
Access/Tunnel support remains independent under `hub/` and does not share
Cloud Hub directory or customer DB credentials.

Client firmware shares networking and identity code under `client-devices/common/lib/ina-client-common/`. It generates `INADS-<UUIDv4>`, speaks MQTT 3.1.1 over the field LAN, and requests runtime config from `/<device_id>/kinds/config/request`. The direct MQTT controller always replies locally; Cloudflare is never in this timing path.

An Edge Runtime is the reusable Python code that faces field devices: it parses MQTT topics, serves cached desired config, records reported state, queues outbound events, deduplicates inbound commands, and exposes health. An Edge Gateway is a Raspberry Pi/Compute Module appliance that runs this Runtime with Mosquitto and an isolated Wi-Fi access point. A Local Hub embeds the same Runtime and can additionally accept Sync v1 calls from child Gateways. Sync v1 is a batched, outbound HTTPS exchange between a child node and its one parent.

## Plan of Work

Milestone 0 establishes contracts before extracting behavior. Add `docs/jp/EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md` for production identity and H/W profiles. Add `shared/contracts/sync/v1/` containing a JSON Schema, examples, invalid vectors, and a short protocol specification. Add contract tests that validate every vector. The milestone is complete when the documented identifiers validate consistently in Python and the request/response examples pass Draft 2020-12 JSON Schema validation.

Milestone 1 creates `shared/edge-runtime/` as an independently testable Python 3.11 package using only the standard library at runtime. It must define identity parsing, the existing MQTT parser, value objects for Sync v1, and an SQLite store. The store writes events before network transmission, returns ordered batches, acknowledges only explicit event IDs, ignores exact duplicates, rejects same-revision/different-content desired state, and does not return expired commands for execution. This package initially runs beside the Hub implementation so existing behavior remains available for comparison.

Milestone 2 integrates the package into the Local Hub without changing external behavior. First delegate only MQTT topic parsing, then config cache access, then event storage. Preserve all existing topics, payloads, QoS, retain behavior, and the fast config reply. Add adapters rather than making shared code import Flask, Cloudflare, Turso, camera, Discord, or farmer-facing UI code. The existing focused Hub tests must stay green after each small move.

Milestone 3 creates `edge-gateway/`. Its Python process uses `ina-edge-runtime`, connects only to the local Mosquitto broker and its configured parent Sync v1 URL, and exposes a local health/maintenance endpoint. Appliance files configure the dedicated device Wi-Fi AP, LAN firewall, NTP, Mosquitto ACLs, persistent `/var/lib/inas`, watchdog, and optional SORACOM modem. All children initiate connections; no inbound WAN port is required.

Milestone 3 acceptance scenarios are:

1. With the parent unreachable, a cached `device.runtime_config` request receives the existing MQTT reply topic, QoS, and retain behavior entirely from local SQLite, and telemetry remains in the outbox across process restart.
2. A successful Sync response is accepted only when its correlation ID matches the request, every acknowledgement names an item in that request, and every desired resource and command targets this Gateway. Desired state and commands are durable before the cursor advances; retrying the response is idempotent.
3. Parent HTTP failure, malformed JSON, oversized response, mismatched target, and partial acknowledgement leave unacknowledged events available for retry.
4. Expired commands are never published. The initial supported command, `device.runtime_config_push`, activates only after an expiry recheck, publishes the cached config locally, and records one durable terminal result. Unsupported commands are rejected durably.
5. `/healthz`, `/readyz`, and `/maintenance/v1/status` expose no credential material. Readiness depends on the local MQTT/control loop, not WAN reachability.
6. Appliance fixtures bind Mosquitto to the device LAN with per-device credentials, isolate Wi-Fi clients, deny device-to-WAN forwarding, retain outbound HTTPS/NTP/DNS for the Gateway host, use `/var/lib/inas`, and run the Gateway under a hardened systemd unit with a watchdog.

Milestone 4 makes Local Hub hierarchical. Add `nodes` and `parent_node_id`,
expose Sync v1 from the Local Hub, retain original event origin IDs while
forwarding child data, and route commands down to their target child. Directly
connected devices are owned by the Local Hub node’s embedded Edge Runtime.
A Local Hub may itself synchronize upward to another Local Hub; only successful
parent enrollment enables its event-log-to-outbox adapter.

Milestone 4 acceptance scenarios are:

1. An authenticated Hub administrator can enroll an `INAEG` or `INALH` child and receives its bearer token exactly once. The repository stores only a salted digest, binds the child to this Local Hub as `parent_node_id`, rotates the credential on re-enrollment, and rejects revoked, unknown, path/body-mismatched, or wrong-prefix nodes before reading their Sync body.
2. The Sync endpoint accepts only `application/json`, optionally gzip encoded, with both compressed and decompressed limits of 1 MiB. It rejects unknown routing fields such as `tenant_id`, malformed envelopes, and origins outside the authenticated child’s registered subtree. No browser/Cloudflare Access credential can substitute for the node bearer credential.
3. Identical event and command-result retries are acknowledged without duplication. Reuse of an ID or `(origin_node_id, sequence)` with different content fails without acknowledging the conflicting item. Locally persisted child events keep their original event ID, origin node, sequence, timestamp, and device ID; parent acknowledgement does not depend on WAN availability.
4. Desired resources and uncompleted commands are selected by the registered next-hop child. A direct Edge Gateway receives only self-targeted items. A Local Hub child may receive items for its explicitly registered descendants and routes them onward without rewriting stable IDs, target IDs, revisions, or expiry. Expired commands are not delivered.
5. A Local Hub configured with an upstream parent sends only outbound authenticated HTTPS Sync requests. A malformed, mismatched, or partially acknowledging response leaves unacknowledged outbox records durable. The first fully valid successful exchange activates the local device-event adapter and backfills already persisted child events/results; merely configuring a parent does not activate emission.
6. Parent desired runtime config for a directly connected device becomes the embedded Runtime’s authoritative cached reply without changing the MQTT topic/QoS/retain contract. Parent outage does not block config replies or Local Hub direct commands. Child data and node health are queryable without exposing bearer tokens, token digests, certificate paths, or database routing material.

Milestone 5 builds Cloud Hub. Deploy one shared Worker/frontend on the exact
Cloud Hub custom domain. Use a directory Turso DB for tenants, Access
memberships, Edge nodes, and encrypted tenant credentials; assign every
customer one dedicated Turso DB. Authenticate and resolve the principal before
opening a tenant DB. Add interactive one-time directory bootstrap, customer DB
provisioning, and Edge Gateway kitting. Preserve the existing Local Hub Turso
configuration and never place any Turso or Cloudflare administrative
credential on an Edge Gateway.

Milestone 5 acceptance scenarios are:

1. An Access-verified email can list only active memberships and cannot open a
   tenant DB for an unrelated public ID. API output contains no internal tenant
   ID, DB URL, or encrypted token.
2. An Edge node is authenticated before its body is read. Unknown/revoked
   credentials, path/body mismatch, and `tenant_id`/DB routing fields fail
   without tenant DB writes.
3. Exact Sync retries are acknowledged once; ID or origin-sequence reuse with
   changed content returns a conflict before health is updated.
4. Directory bootstrap refuses to replace a master key for a populated
   directory. Tenant provisioning creates/adopts only explicitly selected
   databases and stores a scoped encrypted credential.
5. Gateway kitting stores only the node-token digest in the directory and emits
   credentials to a new protected path outside the repository. The output
   contains no Turso or Cloudflare administrative credential.
6. Local Hub still requires its original per-installation
   `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`, and its full regression suite
   remains green.

Milestone 6 completes product behavior. Keep one responsive Local Hub UI, show
child data freshness and sync backlog, add trial and subscription entitlements
outside the safety loop, use signed object-storage URLs when external media is
enabled, add signed A/B appliance updates, and run network-partition,
disk-pressure, appliance-isolation, and hardware-in-the-loop tests. Add an
optional Flutter Android shell only for QR enrollment, Gateway AP setup,
offline network handoff, kiosk/device-owner operation, and diagnostics;
ordinary browsers remain supported and the shell must not fork the Hub UI.

## Concrete Steps

Work from `/home/polonity/workspace/ina-technologies/inas`. Inspect changes before every edit with `git status --short` and preserve pre-existing modifications.

For Milestone 0 and the first part of Milestone 1, create the specification, schemas, vectors, package, and unit tests with `apply_patch`. Validate them with:

    cd shared/edge-runtime
    .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

The expected result is a successful test run covering identity, MQTT parsing, SQLite outbox retry/deduplication, desired revision conflicts, command expiry, and JSON Schema vectors. Then run the focused existing Hub regressions from `hub/`:

    .venv/bin/python -m unittest tests.test_local_edge_runtime tests.test_hub_mqtt_client tests.test_mqtt_device_config_service

If the package is integrated into Hub, run Ruff against only touched Python files first, then run the full Hub test suite if focused tests pass. Do not run formatting over the entire dirty worktree.

For Milestone 3, validate the transport-neutral response application first:

    cd shared/edge-runtime
    .venv/bin/ruff check src tests
    .venv/bin/ruff format --check src tests
    .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

Then validate and build the standalone service:

    cd edge-gateway
    uv sync --python 3.11 --frozen
    uv run ruff check src tests scripts
    uv run ruff format --check src tests scripts
    TMPDIR=/tmp uv run --python 3.11 python -m unittest discover -s tests -p 'test_*.py'
    uv build

The expected test transcript includes offline config reply, restart-safe outbox, rejected mismatched Sync responses, retry after partial acknowledgement, command expiry/rejection, sanitized health output, and static appliance-policy checks. `systemd-analyze verify` and `nft --check` may be added when templates have been rendered into a temporary root; they must never modify the host.

For Milestone 4, validate the shared subtree-aware envelope rules without weakening the Gateway default:

    cd shared/edge-runtime
    uv run --python 3.11 ruff check src tests
    uv run --python 3.11 ruff format --check src tests
    TMPDIR=/tmp uv run --python 3.11 python -m unittest discover -s tests -p 'test_*.py'

Then validate the Local Hub repository, service, HTTP boundary, direct-device behavior, and full regression:

    cd hub
    .venv/bin/ruff check src/ina_device_hub/local_edge_runtime.py src/ina_device_hub/hierarchy_repository.py src/ina_device_hub/hierarchy_service.py src/ina_device_hub/hierarchy_api.py src/ina_device_hub/parent_sync_client.py tests/test_hierarchy_repository.py tests/test_hierarchy_service.py tests/test_hierarchy_api.py tests/test_parent_sync_client.py
    .venv/bin/ruff format --check src/ina_device_hub/local_edge_runtime.py src/ina_device_hub/hierarchy_repository.py src/ina_device_hub/hierarchy_service.py src/ina_device_hub/hierarchy_api.py src/ina_device_hub/parent_sync_client.py tests/test_hierarchy_repository.py tests/test_hierarchy_service.py tests/test_hierarchy_api.py tests/test_parent_sync_client.py
    TMPDIR=/tmp .venv/bin/python -m unittest tests.test_hierarchy_repository tests.test_hierarchy_service tests.test_hierarchy_api tests.test_parent_sync_client tests.test_local_edge_runtime tests.test_mqtt_device_config_service
    TMPDIR=/tmp .venv/bin/python -m unittest discover -s tests -p 'test_*.py'

The focused transcript must include one-time credential enrollment, revoked and mismatched-node rejection, gzip/size bounds, subtree-origin rejection, duplicate/conflict handling, original-origin forwarding, descendant command routing, expiry, first-success event activation, partial-ack retry, and unchanged local MQTT replies. Future milestones must add their exact commands and short expected transcripts here before implementation. Gateway image commands must default to writing a temporary image or loopback target and must never infer a destructive block-device target.

For Milestone 5, validate the shared Worker without using production
credentials:

    cd hub-cloud
    npm ci
    npm audit
    npm run typecheck
    npm test
    npx wrangler deploy --dry-run

The transcript must cover Access-before-directory initialization, membership
isolation, node-auth-before-body parsing, caller-routing-field rejection,
AES-GCM tenant binding, salted node verifiers, gzip expansion limits, exact
Sync retries, conflicting identity reuse, and node-targeted desired
state/commands. Then run the full Local Hub and Edge Gateway suites to prove the
new top-level application did not alter their runtime contracts.

## Validation and Acceptance

Milestone 0 is accepted when production `INADS`, `INAEG`, and `INALH` IDs pass validation; malformed, wrong-prefix, non-v4, uppercase-UUID, and demo IDs fail production validation; every valid Sync v1 vector passes its intended schema; and every invalid vector fails for the documented reason.

Milestone 1 is accepted when killing a mock parent after an event is queued leaves the event durable across store reopen, acknowledging a batch removes only acknowledged IDs, replaying the same event or command does not duplicate it, an older desired revision cannot overwrite a newer one, and an expired immediate command is never returned for execution.

Milestone 2 is accepted when an existing firmware-style config request still results in the same parsed message and config reply topic, payload, QoS, and retain values, and all focused Hub MQTT/config/OTA tests pass. Cloudflare and Turso remote synchronization must not be reachable for that reply to succeed.

Milestones 3 through 6 must add end-to-end acceptance scenarios before implementation. At minimum they must prove 24-hour parent outage operation, retry after partial batch acknowledgement, no execution of expired commands, no cross-tenant database routing, Local Hub direct-device control, child Gateway aggregation, and visible freshness timestamps in both Hub views.

## Idempotence and Recovery

All current work is additive. New SQLite migrations use `CREATE TABLE IF NOT EXISTS` and explicit schema versions. Event and command inserts use stable unique IDs so replay is safe. Desired resources use a revision and content hash so an ambiguous same-revision update fails instead of silently overwriting data.

Do not migrate or delete current `.device_configs.json`, `ina.db`, firmware artifacts, or Cloudflare resources during Milestones 0 and 1. Later migrations must copy into new tables, compare counts and hashes, and retain the old files until an explicit, separately approved cleanup. Node re-enrollment must revoke the old credential but retain its event history and device-assignment history.

## Artifacts and Notes

The first implementation should leave these durable artifacts:

    hub/.agent/edge-cloud-platform.md
    docs/jp/EDGE_GATEWAY_HARDWARE_AND_IDENTITY.md
    shared/contracts/sync/v1/README.md
    shared/contracts/sync/v1/sync.schema.json
    shared/contracts/sync/v1/vectors/
    shared/edge-runtime/pyproject.toml
    shared/edge-runtime/src/ina_edge_runtime/
    shared/edge-runtime/tests/
    hub/src/ina_device_hub/local_edge_runtime.py
    hub/tests/test_local_edge_runtime.py
    hub/src/ina_device_hub/hierarchy_repository.py
    hub/src/ina_device_hub/hierarchy_service.py
    hub/src/ina_device_hub/hierarchy_api.py
    hub/src/ina_device_hub/parent_sync_client.py
    hub/tests/test_hierarchy_repository.py
    hub/tests/test_hierarchy_service.py
    hub/tests/test_hierarchy_api.py
    hub/tests/test_parent_sync_client.py
    hub/doc/jp/HIERARCHICAL_SYNC.md
    edge-gateway/pyproject.toml
    edge-gateway/src/ina_edge_gateway/
    edge-gateway/deployment/
    edge-gateway/scripts/stage_appliance_bundle.py
    edge-gateway/tests/
    hub-cloud/wrangler.jsonc
    hub-cloud/migrations/directory/
    hub-cloud/migrations/tenant/
    hub-cloud/src/
    hub-cloud/scripts/
    hub-cloud/public/
    hub-cloud/test/

Do not add secrets or real tenant, SIM, MQTT, or node credentials to examples. Use reserved example IDs and hosts.

## Interfaces and Dependencies

`shared/edge-runtime/src/ina_edge_runtime/identity.py` must expose `NodeType`, `generate_node_id(node_type)`, `parse_node_id(value)`, and `validate_device_id(value, allow_demo=False)`. Production node IDs are `INAEG-<lowercase UUIDv4>` and `INALH-<lowercase UUIDv4>`. Production device IDs remain `INADS-<lowercase UUIDv4>`.

`shared/edge-runtime/src/ina_edge_runtime/mqtt_topics.py` must expose `parse_mqtt_message(topic, payload)` and return the same dictionary shapes currently produced by `HubMQTTClient._parse_message` for farm telemetry, sensor topics, device config/status topics, broker logs, and unknown topics.

`shared/edge-runtime/src/ina_edge_runtime/store.py` must expose `EdgeStore(path)`, `enqueue_event`, `pending_events`, `ack_events`, `apply_desired_resource`, `get_desired_resource`, `receive_command`, `pending_commands`, and `set_command_status`. It must use `sqlite3`, transactions, UTC timestamps, canonical compact JSON, and SHA-256 content hashes. Runtime dependencies remain standard-library-only.

Sync v1 requests carry `protocol_version`, `node_id`, `node_type`, `sent_at`, an optional parent cursor, an ordered event batch, command results, and health. Responses carry `protocol_version`, `server_time`, an acknowledgement list, the next cursor, desired-resource changes, commands, and a bounded next-poll interval. An event ID is globally stable across retries. A desired resource has a positive integer revision. A command has an issuance time and expiry time and is delivered at least once until acknowledged.

Revision note (2026-07-23): created the initial self-contained plan after repository and platform investigation so implementation can proceed from stable identity, hardware, security, and synchronization boundaries.

Revision note (2026-07-23 11:37+09:00): completed Milestones 0 and 1, recorded their test evidence, added an activation-time command expiry guard, and deferred the Local Hub import until the locked production deployment can carry the shared package.

Revision note (2026-07-23 11:42+09:00): added an independent locked CI path for the cross-project Runtime and Sync contract so changes outside `hub/` cannot bypass validation.

Revision note (2026-07-23 11:50+09:00): made the shared package deployable under the historical Hub target layout, delegated MQTT parsing, and validated a materialized frozen install plus the complete Hub test suite.

Revision note (2026-07-23 11:52+09:00): added cross-thread SQLite coverage and made accepted commands safely resumable after process restart without allowing activation after expiry.

Revision note (2026-07-23 13:28+09:00): integrated the revisioned desired-config cache and persistent `INALH` identity behind the Local Hub service, retained the no-network JSON fallback, and fixed the product UI boundary around a shared web UI plus optional thin Flutter console shell.

Revision note (2026-07-23 13:31+09:00): completed Milestone 2 with durable Local Hub event-outbox adapter operations, recorded 23 shared, 31 focused, and 411 full Hub passing tests, and gated automatic Local Hub emission until parent Sync enrollment prevents an unconsumed outbox.

Revision note (2026-07-23 15:28+09:00): completed Milestone 3 with the standalone Gateway process, bounded and authenticated Sync client, conservative command executor, read-only health API, isolated appliance policy, safe bundle staging, 26 shared tests, 21 Gateway tests, and 411 Hub regressions; recorded physical appliance validation as a later hardware-in-the-loop gate.

Revision note (2026-07-23 17:34+09:00): completed Milestone 4 with separately authenticated child Sync, explicit multi-hop routing, bound and probe-first upstream Local Hub Sync, first-success event activation, monotonic authoritative direct-device config, compressed/decompressed transport limits, 28 shared tests, 23 Gateway tests, 433 Hub tests, frozen copied-deployment validation, and bounded secret-free source packaging; deferred physical AP/QR/Flutter and real infrastructure validation to later gates.

Revision note (2026-07-23 20:08+09:00): completed the repository portion of
Milestone 5 with one shared Cloud Hub Worker/frontend, directory-selected
customer Turso databases, Access membership and direct-Edge authentication,
interactive provisioning/kitting with protected QR artifacts, full dependency
audit, 32 Cloud tests, Wrangler dry-run packaging, and unchanged 28 shared, 23
Gateway, and 433 Local Hub passing suites; deferred live infrastructure,
subscription/trial enforcement, and hardware validation to Milestone 6.

Revision note (2026-07-23 23:58+09:00): added and live-validated the
persistent-plus-ephemeral Cloud Hub tenant regression lifecycle, destructive
cleanup guards and trigger migration, bidirectional membership/node/DB-token
isolation checks, deployed-origin Sync checks, and operator recovery runbook.
