import { jsonPayload } from "../db";
import type { SqlClient } from "../types";

export class AuditLogRepository {
  constructor(private readonly client: SqlClient) {}

  async append(entry: { actorEmail: string; action: string; resourceType: string; resourceId?: string | null; payload?: unknown }): Promise<void> {
    await this.client.execute({
      sql: "INSERT INTO audit_logs (occurred_at, actor_email, action, resource_type, resource_id, payload) VALUES (?, ?, ?, ?, ?, ?)",
      args: [new Date().toISOString(), entry.actorEmail, entry.action, entry.resourceType, entry.resourceId ?? null, jsonPayload(entry.payload)],
    });
  }
}
