import type {
  CloudRuntime,
  NodeRecord,
  SyncRequest,
  SyncResponse,
  TenantRecord,
  TenantServices,
} from "../src/types";

export const EDGE_NODE_ID = "INAEG-11111111-1111-4111-8111-111111111111";
export const OTHER_EDGE_NODE_ID = "INAEG-22222222-2222-4222-8222-222222222222";

export function tenant(overrides: Partial<TenantRecord> = {}): TenantRecord {
  return {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    publicId: "tenant-a",
    displayName: "Tenant A",
    status: "active",
    databaseName: "inas-tenant-a",
    databaseUrl: "libsql://inas-tenant-a-example.turso.io",
    encryptedAuthToken: "v2.encrypted.token",
    credentialKeyVersion: 2,
    ...overrides,
  };
}

export function node(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    nodeId: EDGE_NODE_ID,
    nodeType: "edge_gateway",
    tenant: tenant(),
    status: "active",
    credentials: [
      {
        credentialId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        salt: "",
        digest: "",
        expiresAt: null,
      },
    ],
    ...overrides,
  };
}

export function syncRequest(overrides: Partial<SyncRequest> = {}): SyncRequest {
  return {
    protocol_version: "1.0",
    request_id: "33333333-3333-4333-8333-333333333333",
    node_id: EDGE_NODE_ID,
    node_type: "edge_gateway",
    sent_at: "2026-07-23T10:00:00.000Z",
    cursor: null,
    events: [
      {
        event_id: "44444444-4444-4444-8444-444444444444",
        origin_node_id: EDGE_NODE_ID,
        sequence: 1,
        schema_version: 1,
        event_type: "device.telemetry",
        occurred_at: "2026-07-23T09:59:00.000Z",
        device_id: "INADS-55555555-5555-4555-8555-555555555555",
        payload: { moisture: 42 },
      },
    ],
    command_results: [],
    health: {
      status: "ok",
      software_version: "0.1.0",
      hardware_profile_id: "egw-cm4-standard-r1",
      outbox_depth: 1,
      mqtt_connected: true,
      storage_total_bytes: 1000,
      storage_free_bytes: 800,
      capabilities: ["mqtt", "wifi_ap"],
    },
    ...overrides,
  };
}

export function syncResponse(request: SyncRequest): SyncResponse {
  return {
    protocol_version: "1.0",
    correlation_request_id: request.request_id,
    server_time: "2026-07-23T10:00:01.000Z",
    next_cursor: "cursor-1",
    ack_event_ids: request.events.map((event) => event.event_id),
    ack_command_result_ids: request.command_results.map((result) => result.result_id),
    desired_resources: [],
    commands: [],
    next_poll_seconds: 30,
  };
}

export function services(overrides: Partial<TenantServices> = {}): TenantServices {
  return {
    events: {
      async list() {
        return [];
      },
      async createManagementEvent(input) {
        return {
          id: "66666666-6666-4666-8666-666666666666",
          source: "management",
          origin_node_id: null,
          sequence: null,
          occurred_at: "2026-07-23T10:00:00.000Z",
          event_type: input.eventType,
          direction: "management",
          device_id: input.deviceId ?? null,
          payload: input.payload ?? null,
        };
      },
    },
    dashboard: {
      async summary() {
        return {
          edge_nodes: 1,
          events_24h: 2,
          mqtt_connected_nodes: 1,
          pending_commands: 0,
        };
      },
    },
    sync: {
      async exchange(_node, request) {
        return syncResponse(request);
      },
    },
    ...overrides,
  };
}

export function runtime(overrides: Partial<CloudRuntime> = {}): CloudRuntime {
  return {
    directory: {
      async listMemberships() {
        return [{ ...tenant(), role: "admin" }];
      },
      async resolveMembership(publicId, identity) {
        return publicId === "tenant-a" && identity.email === "admin@example.com"
          ? { ...tenant(), role: "admin" }
          : null;
      },
      async listTenantNodes() {
        return [];
      },
      async findNode() {
        return null;
      },
      async touchNode() {},
    },
    async tenantServices() {
      return services();
    },
    ...overrides,
  };
}
