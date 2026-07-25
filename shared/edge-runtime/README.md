# INA Edge Runtime

`ina-edge-runtime` contains the device-facing primitives shared by a Local Hub and a standalone Edge Gateway. It has no Flask, Cloudflare, Turso, UI, camera, notification, or billing dependency. Runtime dependencies are Python's standard library only.

The first milestone provides:

- production device/node identity validation;
- the existing MQTT topic parser as a transport-neutral function;
- durable SQLite event and command-result outboxes;
- revision-safe desired-resource storage;
- idempotent, expiring command intake;
- Sync v1 request construction from durable state.

Run the tests from the repository root:

```bash
PYTHONPATH=shared/edge-runtime/src \
  python3 -m unittest discover -s shared/edge-runtime/tests -p 'test_*.py'
```

The package does not make network calls. A later `edge-gateway/` adapter and the Local Hub adapter will provide MQTT and HTTPS transports.

One `EdgeStore` instance may be shared by the MQTT and Sync threads. Access to its cross-thread SQLite connection is serialized internally; callers still own process lifecycle and must not close the store while workers are active.

`build_sync_request` derives `node_type` from the authenticated node ID, reads only durable outbox state, and calculates `health.outbox_depth` from SQLite. Tenant IDs, database URLs, and parent overrides are intentionally absent from the API and wire envelope.

Command adapters must move a command to `running` immediately before publishing its device action. Both `accepted` and `running` transitions recheck `expires_at`; an expired command is durably marked `expired` and raises `CommandExpiredError` instead of being activated.
