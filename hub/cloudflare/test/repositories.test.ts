import { describe, expect, it } from "vitest";

import { AdminUserRepository } from "../src/repositories/admin-users";
import { AuditLogRepository } from "../src/repositories/audit-logs";
import { DeviceEventRepository } from "../src/repositories/device-events";
import type { SqlClient } from "../src/types";

describe("repositories", () => {
  it("builds filtered device event queries and parses payloads", async () => {
    const client = new FakeSqlClient([
      {
        rows: [
          {
            id: 7,
            occurred_at: "2026-07-01T00:00:00.000Z",
            event_type: "mqtt_message_received",
            direction: "inbound",
            device_id: "INADS-1",
            topic: "farm/INADS-1/telemetry",
            category: "sensor",
            action: "telemetry",
            kind: null,
            seq_id: "42",
            mqtt_rc: null,
            retain: 0,
            next_sleep_sec: null,
            next_wake_at: null,
            payload: '{"temp":25.5}',
          },
        ],
      },
    ]);
    const repository = new DeviceEventRepository(client);

    const events = await repository.list({
      deviceId: "INADS-1",
      eventType: "mqtt_message_received",
      direction: "inbound",
      limit: 999,
    });

    expect(client.calls[0]).toMatchObject({
      args: ["INADS-1", "mqtt_message_received", "inbound", 500],
    });
    expect(client.calls[0]?.sql).toContain("device_id = ?");
    expect(events).toEqual([
      expect.objectContaining({
        id: 7,
        retain: false,
        payload: { temp: 25.5 },
      }),
    ]);
  });

  it("serializes device event inserts and returns the inserted record", async () => {
    const client = new FakeSqlClient([{ rows: [] }, { rows: [{ id: 11 }] }]);
    const repository = new DeviceEventRepository(client);

    const event = await repository.create({
      occurred_at: "2026-07-01T01:02:03.000Z",
      event_type: "manual_note",
      direction: "inbound",
      device_id: "INADS-2",
      seq_id: 123,
      retain: true,
      payload: { note: "checked" },
    });

    expect(client.calls[0]).toMatchObject({
      args: expect.arrayContaining(["2026-07-01T01:02:03.000Z", "manual_note", "inbound", "INADS-2", "123", 1, '{"note":"checked"}']),
    });
    expect(client.calls[1]).toEqual({ sql: "SELECT last_insert_rowid() AS id", args: [] });
    expect(event).toMatchObject({
      id: 11,
      device_id: "INADS-2",
      seq_id: "123",
      retain: true,
      payload: { note: "checked" },
    });
  });

  it("returns only supported admin user roles", async () => {
    await expect(new AdminUserRepository(new FakeSqlClient([{ rows: [{ role: "operator" }] }])).roleForEmail("op@example.com")).resolves.toBe("operator");
    await expect(new AdminUserRepository(new FakeSqlClient([{ rows: [{ role: "owner" }] }])).roleForEmail("owner@example.com")).resolves.toBeNull();
  });

  it("writes audit logs with JSON payloads", async () => {
    const client = new FakeSqlClient([{ rows: [] }]);
    const repository = new AuditLogRepository(client);

    await repository.append({
      actorEmail: "operator@example.com",
      action: "device_event.create",
      resourceType: "device_event",
      resourceId: "11",
      payload: { event_type: "manual_note" },
    });

    expect(client.calls[0]).toMatchObject({
      args: expect.arrayContaining(["operator@example.com", "device_event.create", "device_event", "11", '{"event_type":"manual_note"}']),
    });
  });
});

class FakeSqlClient implements SqlClient {
  readonly calls: Array<{ sql: string; args: unknown[] }> = [];

  constructor(private readonly responses: Array<{ rows: Array<Record<string, unknown>> }>) {}

  async execute(statement: string | { sql: string; args?: unknown[] }) {
    if (typeof statement === "string") {
      this.calls.push({ sql: statement, args: [] });
    } else {
      this.calls.push({ sql: statement.sql, args: statement.args ?? [] });
    }
    return this.responses.shift() ?? { rows: [] };
  }
}
