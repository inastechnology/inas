import { batchStatements, canonicalJson, jsonPayload, parseJsonPayload } from "../database";
import { sha256Hex } from "../crypto";
import type { DeviceEventRecord, SqlClient } from "../types";

export class DeviceEventRepository {
  constructor(private readonly client: SqlClient) {}

  async list(filters: { deviceId?: string; eventType?: string; limit: number }): Promise<DeviceEventRecord[]> {
    const where: string[] = [];
    const args: Array<string | number> = [];
    if (filters.deviceId) {
      where.push("device_id = ?");
      args.push(filters.deviceId);
    }
    if (filters.eventType) {
      where.push("event_type = ?");
      args.push(filters.eventType);
    }
    args.push(filters.limit);
    const result = await this.client.execute({
      sql: `SELECT id, source, origin_node_id, sequence, occurred_at, event_type,
          direction, device_id, payload
        FROM device_events
        ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
        ORDER BY occurred_at DESC, id DESC
        LIMIT ?`,
      args,
    });
    return result.rows.map(eventFromRow).filter((event): event is DeviceEventRecord => event !== null);
  }

  async createManagementEvent(input: {
    actorEmail: string;
    eventType: string;
    deviceId?: string | null;
    payload?: unknown;
  }): Promise<DeviceEventRecord> {
    const id = globalThis.crypto.randomUUID();
    const occurredAt = new Date().toISOString();
    const payload = input.payload ?? null;
    const contentSha256 = await sha256Hex(
      canonicalJson({
        id,
        source: "management",
        origin_node_id: null,
        sequence: null,
        occurred_at: occurredAt,
        event_type: input.eventType,
        direction: "management",
        device_id: input.deviceId ?? null,
        payload,
      }),
    );
    await batchStatements(this.client, [
      {
        sql: `INSERT INTO device_events (
            id, source, origin_node_id, sequence, occurred_at, event_type,
            direction, device_id, payload, content_sha256, created_at
          ) VALUES (?, 'management', NULL, NULL, ?, ?, 'management', ?, ?, ?, ?)`,
        args: [
          id,
          occurredAt,
          input.eventType,
          input.deviceId ?? null,
          jsonPayload(payload),
          contentSha256,
          occurredAt,
        ],
      },
      {
        sql: `INSERT INTO audit_logs (
            occurred_at, actor, action, resource_type, resource_id, payload
          ) VALUES (?, ?, 'event.create', 'device_event', ?, ?)`,
        args: [
          occurredAt,
          input.actorEmail,
          id,
          jsonPayload({ event_type: input.eventType, device_id: input.deviceId ?? null }),
        ],
      },
    ]);
    return {
      id,
      source: "management",
      origin_node_id: null,
      sequence: null,
      occurred_at: occurredAt,
      event_type: input.eventType,
      direction: "management",
      device_id: input.deviceId ?? null,
      payload,
    };
  }
}

function eventFromRow(row: Record<string, unknown>): DeviceEventRecord | null {
  const source = row.source;
  if (source !== "sync" && source !== "management") {
    return null;
  }
  const sequence = row.sequence === null || row.sequence === undefined ? null : Number(row.sequence);
  if (sequence !== null && (!Number.isSafeInteger(sequence) || sequence < 1)) {
    return null;
  }
  return {
    id: String(row.id),
    source,
    origin_node_id: row.origin_node_id === null || row.origin_node_id === undefined ? null : String(row.origin_node_id),
    sequence,
    occurred_at: String(row.occurred_at),
    event_type: String(row.event_type),
    direction: String(row.direction),
    device_id: row.device_id === null || row.device_id === undefined ? null : String(row.device_id),
    payload: parseJsonPayload(row.payload),
  };
}
