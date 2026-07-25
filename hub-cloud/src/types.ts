export type Role = "reader" | "operator" | "admin";
export type TenantStatus = "active" | "suspended" | "deprovisioning";
export type NodeType = "edge_gateway" | "local_hub";

export interface RateLimiterBinding {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

export interface Env {
  ASSETS?: Fetcher;
  SYNC_NODE_RATE_LIMITER?: RateLimiterBinding;
  SYNC_IP_RATE_LIMITER?: RateLimiterBinding;
  SECURITY_ALERT_RATE_LIMITER?: RateLimiterBinding;
  CLOUD_HUB_PUBLIC_ORIGIN?: string;
  CLOUDFLARE_ACCESS_TEAM_DOMAIN?: string;
  CLOUDFLARE_ACCESS_POLICY_AUD?: string;
  DIRECTORY_TURSO_DATABASE_URL?: string;
  DIRECTORY_TURSO_AUTH_TOKEN?: string;
  TENANT_CREDENTIAL_MASTER_KEY?: string;
  DISCORD_SECURITY_WEBHOOK_URL?: string;
}

export interface AccessIdentity {
  email: string;
  subject: string;
}

export interface AccessUser {
  email: string;
  role: Role;
}

export interface TenantSummary {
  id: string;
  publicId: string;
  displayName: string;
  status: TenantStatus;
}

export interface TenantMembership extends TenantSummary {
  role: Role;
}

export interface TenantRecord extends TenantSummary {
  databaseName: string;
  databaseUrl: string;
  encryptedAuthToken: string;
  credentialKeyVersion: number;
}

export interface NodeRecord {
  nodeId: string;
  nodeType: NodeType;
  tenant: TenantRecord;
  status: "active" | "revoked";
  credentials: NodeCredentialRecord[];
}

export interface NodeCredentialRecord {
  credentialId: string;
  salt: string;
  digest: string;
  expiresAt: string | null;
}

export interface TenantNodeSummary {
  nodeId: string;
  label: string | null;
  nodeType: NodeType;
  status: "active" | "revoked";
  lastSeenAt: string | null;
}

export interface SqlResultSet {
  rows: Array<Record<string, unknown>>;
  rowsAffected?: number;
  lastInsertRowid?: bigint | number | string;
}

export type SqlValue = null | string | number | bigint | boolean | ArrayBuffer | Uint8Array | Date;

export interface SqlStatement {
  sql: string;
  args?: SqlValue[];
}

export interface SqlClient {
  execute(statement: string | SqlStatement): Promise<SqlResultSet>;
  batch?(statements: SqlStatement[], mode?: "deferred" | "read" | "write"): Promise<SqlResultSet[]>;
}

export interface DeviceEventRecord {
  id: string;
  source: "sync" | "management";
  origin_node_id: string | null;
  sequence: number | null;
  occurred_at: string;
  event_type: string;
  direction: string;
  device_id: string | null;
  payload: unknown;
}

export interface DashboardSummary {
  edge_nodes: number;
  events_24h: number;
  mqtt_connected_nodes: number;
  pending_commands: number;
}

export interface DirectoryRepositoryContract {
  listMemberships(identity: AccessIdentity): Promise<TenantMembership[]>;
  resolveMembership(publicId: string, identity: AccessIdentity): Promise<(TenantRecord & { role: Role }) | null>;
  listTenantNodes(tenantId: string): Promise<TenantNodeSummary[]>;
  findNode(nodeId: string): Promise<NodeRecord | null>;
  touchNode(nodeId: string, credentialId: string, at: string): Promise<void>;
}

export interface TenantServices {
  events: {
    list(filters: { deviceId?: string; eventType?: string; limit: number }): Promise<DeviceEventRecord[]>;
    createManagementEvent(input: { actorEmail: string; eventType: string; deviceId?: string | null; payload?: unknown }): Promise<DeviceEventRecord>;
  };
  dashboard: {
    summary(): Promise<DashboardSummary>;
  };
  sync: {
    exchange(node: NodeRecord, request: SyncRequest): Promise<SyncResponse>;
  };
}

export interface CloudRuntime {
  directory: DirectoryRepositoryContract;
  tenantServices(tenant: TenantRecord): Promise<TenantServices>;
}

export interface AppVariables {
  accessIdentity: AccessIdentity;
  runtime: CloudRuntime;
  tenant: TenantRecord;
  user: AccessUser;
  tenantServices: TenantServices;
}

export interface SyncEvent {
  event_id: string;
  origin_node_id: string;
  sequence: number;
  schema_version: number;
  event_type: string;
  occurred_at: string;
  device_id?: string;
  payload: unknown;
}

export interface SyncCommandResult {
  result_id: string;
  command_id: string;
  origin_node_id: string;
  status: "accepted" | "running" | "succeeded" | "failed" | "expired" | "rejected";
  occurred_at: string;
  error_code?: string;
  message?: string;
  payload?: unknown;
}

export interface SyncHealth {
  status: "ok" | "degraded" | "critical";
  software_version: string;
  hardware_profile_id?: string;
  outbox_depth: number;
  mqtt_connected: boolean;
  storage_total_bytes?: number;
  storage_free_bytes: number;
  capabilities: string[];
  details?: Record<string, unknown>;
}

export interface SyncRequest {
  protocol_version: "1.0";
  request_id: string;
  node_id: string;
  node_type: NodeType;
  sent_at: string;
  cursor: string | null;
  events: SyncEvent[];
  command_results: SyncCommandResult[];
  health: SyncHealth;
}

export interface DesiredResource {
  resource_type: "device.runtime_config" | "device.assignment" | "device.firmware_target" | "node.policy";
  resource_id: string;
  target_node_id: string;
  revision: number;
  operation: "upsert" | "delete";
  content_sha256: string;
  updated_at: string;
  payload: Record<string, unknown> | null;
}

export interface SyncCommand {
  command_id: string;
  idempotency_key: string;
  command_type: string;
  target_node_id: string;
  device_id?: string;
  issued_at: string;
  expires_at: string;
  payload: Record<string, unknown>;
}

export interface SyncResponse {
  protocol_version: "1.0";
  correlation_request_id: string;
  server_time: string;
  next_cursor: string | null;
  ack_event_ids: string[];
  ack_command_result_ids: string[];
  desired_resources: DesiredResource[];
  commands: SyncCommand[];
  next_poll_seconds: number;
}
