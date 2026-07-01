export type Role = "reader" | "operator" | "admin";

export interface Env {
  CLOUDFLARE_ACCESS_TEAM_DOMAIN?: string;
  CLOUDFLARE_ACCESS_POLICY_AUD?: string;
  TURSO_DATABASE_URL?: string;
  TURSO_AUTH_TOKEN?: string;
}

export interface AccessUser {
  email: string;
  role: Role;
}

export interface DeviceEventInput {
  occurred_at?: string;
  event_type: string;
  direction: string;
  device_id?: string | null;
  topic?: string | null;
  category?: string | null;
  action?: string | null;
  kind?: string | null;
  seq_id?: string | number | null;
  mqtt_rc?: number | null;
  retain?: boolean | null;
  next_sleep_sec?: number | null;
  next_wake_at?: string | null;
  payload?: unknown;
}

export interface DeviceEventRecord extends DeviceEventInput {
  id: number;
  occurred_at: string;
  device_id: string | null;
  topic: string | null;
  category: string | null;
  action: string | null;
  kind: string | null;
  seq_id: string | null;
  mqtt_rc: number | null;
  retain: boolean | null;
  next_sleep_sec: number | null;
  next_wake_at: string | null;
}

export interface SqlClient {
  execute(statement: string | { sql: string; args?: unknown[] }): Promise<SqlResultSet>;
}

export interface SqlResultSet {
  rows: Array<Record<string, unknown>>;
}

export interface AppServices {
  deviceEvents: {
    list(filters: { deviceId?: string; eventType?: string; direction?: string; limit: number }): Promise<DeviceEventRecord[]>;
    create(input: DeviceEventInput): Promise<DeviceEventRecord>;
  };
  adminUsers: {
    roleForEmail(email: string): Promise<Role | null>;
  };
  auditLogs: {
    append(entry: { actorEmail: string; action: string; resourceType: string; resourceId?: string | null; payload?: unknown }): Promise<void>;
  };
}
