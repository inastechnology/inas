import type { DashboardSummary, SqlClient } from "../types";

export class DashboardRepository {
  constructor(private readonly client: SqlClient) {}

  async summary(): Promise<DashboardSummary> {
    const now = new Date();
    const since = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
    const result = await this.client.execute({
      sql: `SELECT
          (SELECT COUNT(*) FROM node_health) AS edge_nodes,
          (SELECT COUNT(*) FROM device_events WHERE occurred_at >= ?) AS events_24h,
          (SELECT COUNT(*) FROM node_health WHERE mqtt_connected = 1) AS mqtt_connected_nodes,
          (SELECT COUNT(*) FROM commands WHERE status = 'pending' AND expires_at > ?) AS pending_commands`,
      args: [since, now.toISOString()],
    });
    const row = result.rows[0] ?? {};
    return {
      edge_nodes: safeCount(row.edge_nodes),
      events_24h: safeCount(row.events_24h),
      mqtt_connected_nodes: safeCount(row.mqtt_connected_nodes),
      pending_commands: safeCount(row.pending_commands),
    };
  }
}

function safeCount(value: unknown): number {
  const count = Number(value ?? 0);
  return Number.isSafeInteger(count) && count >= 0 ? count : 0;
}
