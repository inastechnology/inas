import { batchStatements, canonicalJson, jsonPayload, parseJsonPayload } from "../database";
import { sha256Hex } from "../crypto";
import type {
  DesiredResource,
  NodeRecord,
  SqlClient,
  SqlStatement,
  SyncCommand,
  SyncCommandResult,
  SyncEvent,
  SyncRequest,
  SyncResponse,
} from "../types";

const TERMINAL_COMMAND_STATUSES = new Set(["succeeded", "failed", "expired", "rejected"]);

export class SyncConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SyncConflictError";
  }
}

export class SyncRepository {
  constructor(private readonly client: SqlClient) {}

  async exchange(node: NodeRecord, request: SyncRequest): Promise<SyncResponse> {
    const now = new Date().toISOString();
    const events = await hashEvents(request.events);
    const results = await hashCommandResults(request.command_results);

    await this.assertCommandResultsBelongToNode(node.nodeId, request.command_results);
    const existingEvents = await this.findExistingEvents(request.events);
    const existingResults = await this.findExistingCommandResults(request.command_results);
    const newEvents = events.filter(({ value, digest }) => {
      const byId = existingEvents.byId.get(value.event_id);
      const bySequence = existingEvents.bySequence.get(sequenceKey(value.origin_node_id, value.sequence));
      if (byId && bySequence && byId.id !== bySequence.id) {
        throw new SyncConflictError("event identity maps to more than one stored record");
      }
      const existing = byId ?? bySequence;
      if (existing && existing.digest !== digest) {
        throw new SyncConflictError("event identity was reused with different content");
      }
      return existing === undefined;
    });
    const newResults = results.filter(({ value, digest }) => {
      const existing = existingResults.get(value.result_id);
      if (existing && existing !== digest) {
        throw new SyncConflictError("command result identity was reused with different content");
      }
      return existing === undefined;
    });

    const statements: SqlStatement[] = [
      ...newEvents.map(({ value, digest }) => eventInsert(value, digest, now)),
      ...newResults.map(({ value, digest }) => commandResultInsert(value, digest, now)),
      ...request.command_results
        .filter((result) => TERMINAL_COMMAND_STATUSES.has(result.status))
        .map((result) => ({
          sql: `UPDATE commands
            SET status = 'completed'
            WHERE command_id = ? AND target_node_id = ? AND status = 'pending'`,
          args: [result.command_id, node.nodeId],
        })),
      {
        sql: `INSERT INTO node_health (
            node_id, reported_at, status, software_version, hardware_profile_id,
            outbox_depth, mqtt_connected, storage_total_bytes, storage_free_bytes,
            capabilities, details
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(node_id) DO UPDATE SET
            reported_at = excluded.reported_at,
            status = excluded.status,
            software_version = excluded.software_version,
            hardware_profile_id = excluded.hardware_profile_id,
            outbox_depth = excluded.outbox_depth,
            mqtt_connected = excluded.mqtt_connected,
            storage_total_bytes = excluded.storage_total_bytes,
            storage_free_bytes = excluded.storage_free_bytes,
            capabilities = excluded.capabilities,
            details = excluded.details`,
        args: [
          node.nodeId,
          now,
          request.health.status,
          request.health.software_version,
          request.health.hardware_profile_id ?? null,
          request.health.outbox_depth,
          request.health.mqtt_connected ? 1 : 0,
          request.health.storage_total_bytes ?? null,
          request.health.storage_free_bytes,
          jsonPayload(request.health.capabilities),
          jsonPayload(request.health.details ?? null),
        ],
      },
    ];
    await batchStatements(this.client, statements);

    const [desiredResources, commands] = await Promise.all([
      this.desiredResources(node.nodeId),
      this.pendingCommands(node.nodeId, now),
    ]);
    return {
      protocol_version: "1.0",
      correlation_request_id: request.request_id,
      server_time: now,
      next_cursor: `v1.${Date.now()}.${request.request_id}`,
      ack_event_ids: request.events.map((event) => event.event_id),
      ack_command_result_ids: request.command_results.map((result) => result.result_id),
      desired_resources: desiredResources,
      commands,
      next_poll_seconds: 30,
    };
  }

  private async assertCommandResultsBelongToNode(
    nodeId: string,
    results: SyncCommandResult[],
  ): Promise<void> {
    if (results.length === 0) {
      return;
    }
    const commandIds = [...new Set(results.map((result) => result.command_id))];
    const placeholders = commandIds.map(() => "?").join(", ");
    const query = await this.client.execute({
      sql: `SELECT command_id, target_node_id
        FROM commands
        WHERE command_id IN (${placeholders})`,
      args: commandIds,
    });
    const targets = new Map(
      query.rows.map((row) => [String(row.command_id), String(row.target_node_id)]),
    );
    for (const result of results) {
      if (targets.get(result.command_id) !== nodeId) {
        throw new SyncConflictError(
          "command result is not authorized for the authenticated node",
        );
      }
    }
  }

  private async findExistingEvents(events: SyncEvent[]): Promise<{
    byId: Map<string, { id: string; digest: string }>;
    bySequence: Map<string, { id: string; digest: string }>;
  }> {
    const byId = new Map<string, { id: string; digest: string }>();
    const bySequence = new Map<string, { id: string; digest: string }>();
    if (events.length === 0) {
      return { byId, bySequence };
    }
    const idPlaceholders = events.map(() => "?").join(", ");
    const sequencePlaceholders = events.map(() => "(?, ?)").join(", ");
    const result = await this.client.execute({
      sql: `SELECT id, origin_node_id, sequence, content_sha256
        FROM device_events
        WHERE id IN (${idPlaceholders})
          OR (origin_node_id, sequence) IN (${sequencePlaceholders})`,
      args: [
        ...events.map((event) => event.event_id),
        ...events.flatMap((event) => [event.origin_node_id, event.sequence]),
      ],
    });
    for (const row of result.rows) {
      const id = String(row.id);
      const digest = String(row.content_sha256);
      const existing = { id, digest };
      byId.set(id, existing);
      bySequence.set(sequenceKey(String(row.origin_node_id), Number(row.sequence)), existing);
    }
    return { byId, bySequence };
  }

  private async findExistingCommandResults(results: SyncCommandResult[]): Promise<Map<string, string>> {
    const existing = new Map<string, string>();
    if (results.length === 0) {
      return existing;
    }
    const placeholders = results.map(() => "?").join(", ");
    const query = await this.client.execute({
      sql: `SELECT result_id, content_sha256
        FROM command_results
        WHERE result_id IN (${placeholders})`,
      args: results.map((result) => result.result_id),
    });
    for (const row of query.rows) {
      existing.set(String(row.result_id), String(row.content_sha256));
    }
    return existing;
  }

  private async desiredResources(nodeId: string): Promise<DesiredResource[]> {
    const result = await this.client.execute({
      sql: `SELECT resource_type, resource_id, target_node_id, revision,
          operation, content_sha256, updated_at, payload
        FROM desired_resources
        WHERE target_node_id = ?
        ORDER BY resource_type, resource_id
        LIMIT 500`,
      args: [nodeId],
    });
    return result.rows.map(desiredResourceFromRow).filter((value): value is DesiredResource => value !== null);
  }

  private async pendingCommands(nodeId: string, now: string): Promise<SyncCommand[]> {
    const result = await this.client.execute({
      sql: `SELECT command_id, idempotency_key, command_type, target_node_id,
          device_id, issued_at, expires_at, payload
        FROM commands
        WHERE target_node_id = ?
          AND status = 'pending'
          AND expires_at > ?
        ORDER BY issued_at, command_id
        LIMIT 200`,
      args: [nodeId, now],
    });
    return result.rows.map(commandFromRow).filter((value): value is SyncCommand => value !== null);
  }
}

async function hashEvents(events: SyncEvent[]): Promise<Array<{ value: SyncEvent; digest: string }>> {
  return Promise.all(events.map(async (value) => ({ value, digest: await sha256Hex(canonicalJson(value)) })));
}

async function hashCommandResults(
  results: SyncCommandResult[],
): Promise<Array<{ value: SyncCommandResult; digest: string }>> {
  return Promise.all(results.map(async (value) => ({ value, digest: await sha256Hex(canonicalJson(value)) })));
}

function eventInsert(event: SyncEvent, digest: string, now: string): SqlStatement {
  return {
    sql: `INSERT INTO device_events (
        id, source, origin_node_id, sequence, occurred_at, event_type,
        direction, device_id, payload, content_sha256, created_at
      ) VALUES (?, 'sync', ?, ?, ?, ?, 'upstream', ?, ?, ?, ?)`,
    args: [
      event.event_id,
      event.origin_node_id,
      event.sequence,
      event.occurred_at,
      event.event_type,
      event.device_id ?? null,
      jsonPayload(event.payload),
      digest,
      now,
    ],
  };
}

function commandResultInsert(result: SyncCommandResult, digest: string, now: string): SqlStatement {
  return {
    sql: `INSERT INTO command_results (
        result_id, command_id, origin_node_id, status, occurred_at,
        error_code, message, payload, content_sha256, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      result.result_id,
      result.command_id,
      result.origin_node_id,
      result.status,
      result.occurred_at,
      result.error_code ?? null,
      result.message ?? null,
      jsonPayload(result.payload ?? null),
      digest,
      now,
    ],
  };
}

function desiredResourceFromRow(row: Record<string, unknown>): DesiredResource | null {
  const resourceType = row.resource_type;
  const operation = row.operation;
  const payload = parseJsonPayload(row.payload);
  if (
    !["device.runtime_config", "device.assignment", "device.firmware_target", "node.policy"].includes(
      String(resourceType),
    ) ||
    (operation !== "upsert" && operation !== "delete") ||
    (operation === "delete" && payload !== null) ||
    (operation === "upsert" && !isRecord(payload))
  ) {
    return null;
  }
  return {
    resource_type: resourceType as DesiredResource["resource_type"],
    resource_id: String(row.resource_id),
    target_node_id: String(row.target_node_id),
    revision: Number(row.revision),
    operation,
    content_sha256: String(row.content_sha256),
    updated_at: String(row.updated_at),
    payload: payload as Record<string, unknown> | null,
  };
}

function commandFromRow(row: Record<string, unknown>): SyncCommand | null {
  const payload = parseJsonPayload(row.payload);
  if (!isRecord(payload)) {
    return null;
  }
  return {
    command_id: String(row.command_id),
    idempotency_key: String(row.idempotency_key),
    command_type: String(row.command_type),
    target_node_id: String(row.target_node_id),
    ...(row.device_id === null || row.device_id === undefined ? {} : { device_id: String(row.device_id) }),
    issued_at: String(row.issued_at),
    expires_at: String(row.expires_at),
    payload,
  };
}

function sequenceKey(originNodeId: string, sequence: number): string {
  return `${originNodeId}\u0000${sequence}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
