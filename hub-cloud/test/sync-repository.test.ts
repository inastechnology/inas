import { createClient } from "@libsql/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SyncConflictError, SyncRepository } from "../src/repositories/sync";
import { applyMigrations } from "../scripts/migrations";
import { node, syncRequest } from "./helpers";

describe("tenant Sync repository", () => {
  let client: ReturnType<typeof createClient>;

  beforeEach(async () => {
    client = createClient({ url: "file::memory:" });
    await applyMigrations(client, new URL("../migrations/tenant/", import.meta.url));
  });

  afterEach(() => {
    client.close();
  });

  it("acknowledges exact retries without duplicating tenant data", async () => {
    const repository = new SyncRepository(client);
    const request = syncRequest();
    const first = await repository.exchange(node(), request);
    const second = await repository.exchange(node(), request);
    expect(first.ack_event_ids).toEqual([request.events[0].event_id]);
    expect(second.ack_event_ids).toEqual(first.ack_event_ids);
    const count = await client.execute("SELECT COUNT(*) AS count FROM device_events");
    expect(Number(count.rows[0].count)).toBe(1);
  });

  it("rejects conflicting ID and sequence reuse before writing health", async () => {
    const repository = new SyncRepository(client);
    const request = syncRequest();
    await repository.exchange(node(), request);
    const conflict = syncRequest({
      events: [{ ...request.events[0], payload: { moisture: 99 } }],
      health: { ...request.health, status: "critical" },
    });
    await expect(repository.exchange(node(), conflict)).rejects.toBeInstanceOf(SyncConflictError);
    const health = await client.execute({
      sql: "SELECT status FROM node_health WHERE node_id = ?",
      args: [request.node_id],
    });
    expect(health.rows[0].status).toBe("ok");
  });

  it("returns only desired state and commands targeting the authenticated node", async () => {
    const now = new Date();
    const resourcePayload = { sample_seconds: 30 };
    await client.batch(
      [
        {
          sql: `INSERT INTO desired_resources (
              resource_type, resource_id, target_node_id, revision,
              operation, content_sha256, updated_at, payload
            ) VALUES ('node.policy', 'policy-1', ?, 1, 'upsert', ?, ?, ?)`,
          args: [
            syncRequest().node_id,
            "a".repeat(64),
            now.toISOString(),
            JSON.stringify(resourcePayload),
          ],
        },
        {
          sql: `INSERT INTO commands (
              command_id, idempotency_key, command_type, target_node_id,
              issued_at, expires_at, payload, status, created_at
            ) VALUES (?, 'push-1', 'device.runtime_config_push', ?, ?, ?, '{}', 'pending', ?)`,
          args: [
            "88888888-8888-4888-8888-888888888888",
            syncRequest().node_id,
            now.toISOString(),
            new Date(now.getTime() + 60_000).toISOString(),
            now.toISOString(),
          ],
        },
        {
          sql: `INSERT INTO commands (
              command_id, idempotency_key, command_type, target_node_id,
              issued_at, expires_at, payload, status, created_at
            ) VALUES (?, 'other-1', 'device.runtime_config_push', ?, ?, ?, '{}', 'pending', ?)`,
          args: [
            "99999999-9999-4999-8999-999999999999",
            "INAEG-22222222-2222-4222-8222-222222222222",
            now.toISOString(),
            new Date(now.getTime() + 60_000).toISOString(),
            now.toISOString(),
          ],
        },
      ],
      "write",
    );
    const response = await new SyncRepository(client).exchange(node(), syncRequest());
    expect(response.desired_resources).toHaveLength(1);
    expect(response.desired_resources[0].payload).toEqual(resourcePayload);
    expect(response.commands.map((command) => command.command_id)).toEqual([
      "88888888-8888-4888-8888-888888888888",
    ]);
  });

  it("rejects command results for another node before writing tenant state", async () => {
    const otherNodeId = "INAEG-22222222-2222-4222-8222-222222222222";
    const commandId = "99999999-9999-4999-8999-999999999999";
    const now = new Date().toISOString();
    await client.execute({
      sql: `INSERT INTO commands (
          command_id, idempotency_key, command_type, target_node_id,
          issued_at, expires_at, payload, status, created_at
        ) VALUES (?, 'other-result', 'device.runtime_config_push', ?, ?, ?, '{}', 'pending', ?)`,
      args: [
        commandId,
        otherNodeId,
        now,
        new Date(Date.now() + 60_000).toISOString(),
        now,
      ],
    });
    const request = syncRequest({
      events: [],
      command_results: [
        {
          result_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          command_id: commandId,
          origin_node_id: syncRequest().node_id,
          status: "succeeded",
          occurred_at: now,
        },
      ],
    });
    await expect(new SyncRepository(client).exchange(node(), request)).rejects.toThrow(
      "not authorized",
    );
    const health = await client.execute("SELECT COUNT(*) AS count FROM node_health");
    expect(Number(health.rows[0].count)).toBe(0);
  });
});
