import { jsonPayload, parseJsonPayload } from "../db";
import type { DeviceEventInput, DeviceEventRecord, SqlClient } from "../types";

const MAX_LIMIT = 500;

export class DeviceEventRepository {
  constructor(private readonly client: SqlClient) {}

  async list(filters: { deviceId?: string; eventType?: string; direction?: string; limit: number }): Promise<DeviceEventRecord[]> {
    const where: string[] = [];
    const args: unknown[] = [];
    if (filters.deviceId) {
      where.push("device_id = ?");
      args.push(filters.deviceId);
    }
    if (filters.eventType) {
      where.push("event_type = ?");
      args.push(filters.eventType);
    }
    if (filters.direction) {
      where.push("direction = ?");
      args.push(filters.direction);
    }

    const limit = Math.max(1, Math.min(filters.limit || 100, MAX_LIMIT));
    args.push(limit);
    const whereSql = where.length > 0 ? ` WHERE ${where.join(" AND ")}` : "";
    const result = await this.client.execute({
      sql: `SELECT id, occurred_at, event_type, direction, device_id, topic, category, action, kind, seq_id, mqtt_rc, retain, next_sleep_sec, next_wake_at, payload FROM device_events${whereSql} ORDER BY id DESC LIMIT ?`,
      args,
    });
    return result.rows.map(rowToEvent);
  }

  async create(input: DeviceEventInput): Promise<DeviceEventRecord> {
    const occurredAt = input.occurred_at || new Date().toISOString();
    await this.client.execute({
      sql: `INSERT INTO device_events (
        occurred_at, event_type, direction, device_id, topic, category, action, kind,
        seq_id, mqtt_rc, retain, next_sleep_sec, next_wake_at, payload
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [
        occurredAt,
        input.event_type,
        input.direction,
        input.device_id ?? null,
        input.topic ?? null,
        input.category ?? null,
        input.action ?? null,
        input.kind ?? null,
        input.seq_id === undefined || input.seq_id === null ? null : String(input.seq_id),
        input.mqtt_rc ?? null,
        input.retain === undefined || input.retain === null ? null : input.retain ? 1 : 0,
        input.next_sleep_sec ?? null,
        input.next_wake_at ?? null,
        jsonPayload(input.payload),
      ],
    });
    const result = await this.client.execute("SELECT last_insert_rowid() AS id");
    const id = Number(result.rows[0]?.id ?? 0);
    return {
      id,
      occurred_at: occurredAt,
      event_type: input.event_type,
      direction: input.direction,
      device_id: input.device_id ?? null,
      topic: input.topic ?? null,
      category: input.category ?? null,
      action: input.action ?? null,
      kind: input.kind ?? null,
      seq_id: input.seq_id === undefined || input.seq_id === null ? null : String(input.seq_id),
      mqtt_rc: input.mqtt_rc ?? null,
      retain: input.retain ?? null,
      next_sleep_sec: input.next_sleep_sec ?? null,
      next_wake_at: input.next_wake_at ?? null,
      payload: input.payload ?? null,
    };
  }
}

function rowToEvent(row: Record<string, unknown>): DeviceEventRecord {
  return {
    id: Number(row.id),
    occurred_at: String(row.occurred_at),
    event_type: String(row.event_type),
    direction: String(row.direction),
    device_id: nullableString(row.device_id),
    topic: nullableString(row.topic),
    category: nullableString(row.category),
    action: nullableString(row.action),
    kind: nullableString(row.kind),
    seq_id: nullableString(row.seq_id),
    mqtt_rc: nullableNumber(row.mqtt_rc),
    retain: row.retain === null || row.retain === undefined ? null : Boolean(row.retain),
    next_sleep_sec: nullableNumber(row.next_sleep_sec),
    next_wake_at: nullableString(row.next_wake_at),
    payload: parseJsonPayload(row.payload),
  };
}

function nullableString(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function nullableNumber(value: unknown): number | null {
  return value === null || value === undefined ? null : Number(value);
}
