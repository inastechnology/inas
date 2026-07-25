import type {
  NodeRecord,
  SyncCommandResult,
  SyncEvent,
  SyncHealth,
  SyncRequest,
} from "./types";
import { assertSafeJson } from "./json-safety";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const NODE_ID = /^INAEG-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DEVICE_ID = /^INADS-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const EVENT_TYPE = /^[a-z][a-z0-9_.-]*$/;
const HARDWARE_PROFILE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const RFC3339 =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

const REQUEST_KEYS = [
  "protocol_version",
  "request_id",
  "node_id",
  "node_type",
  "sent_at",
  "cursor",
  "events",
  "command_results",
  "health",
] as const;
const EVENT_KEYS = [
  "event_id",
  "origin_node_id",
  "sequence",
  "schema_version",
  "event_type",
  "occurred_at",
  "device_id",
  "payload",
] as const;
const RESULT_KEYS = [
  "result_id",
  "command_id",
  "origin_node_id",
  "status",
  "occurred_at",
  "error_code",
  "message",
  "payload",
] as const;
const HEALTH_KEYS = [
  "status",
  "software_version",
  "hardware_profile_id",
  "outbox_depth",
  "mqtt_connected",
  "storage_total_bytes",
  "storage_free_bytes",
  "capabilities",
  "details",
] as const;
const RESULT_STATUSES = new Set(["accepted", "running", "succeeded", "failed", "expired", "rejected"]);

export class SyncValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SyncValidationError";
  }
}

export function validateSyncRequest(value: unknown, pathNodeId: string, authenticatedNode: NodeRecord): SyncRequest {
  const document = exactObject(value, REQUEST_KEYS, "request");
  requireValue(document.protocol_version === "1.0", "protocol_version must be 1.0");
  const requestId = boundedPattern(document.request_id, UUID_V4, 36, "request_id");
  const nodeId = boundedPattern(document.node_id, NODE_ID, 42, "node_id");
  requireValue(nodeId === pathNodeId && nodeId === authenticatedNode.nodeId, "node_id does not match authenticated path");
  const nodeType = document.node_type;
  requireValue(nodeType === "edge_gateway", "Cloud Hub accepts only direct Edge Gateway origins");
  requireValue(nodeType === authenticatedNode.nodeType, "node_type does not match authenticated node");
  const sentAt = dateTime(document.sent_at, "sent_at");
  const cursor = optionalCursor(document.cursor);
  requireValue(Array.isArray(document.events) && document.events.length <= 500, "events must contain at most 500 items");
  requireValue(
    Array.isArray(document.command_results) && document.command_results.length <= 200,
    "command_results must contain at most 200 items",
  );
  const events = document.events.map((event, index) => validateEvent(event, nodeId, index));
  const commandResults = document.command_results.map((result, index) =>
    validateCommandResult(result, nodeId, index),
  );
  rejectDuplicates(
    events.map((event) => event.event_id),
    "event_id",
  );
  rejectDuplicates(
    events.map((event) => `${event.origin_node_id}\u0000${event.sequence}`),
    "event origin/sequence",
  );
  rejectDuplicates(
    commandResults.map((result) => result.result_id),
    "command result_id",
  );
  const health = validateHealth(document.health);
  return {
    protocol_version: "1.0",
    request_id: requestId,
    node_id: nodeId,
    node_type: nodeType,
    sent_at: sentAt,
    cursor,
    events,
    command_results: commandResults,
    health,
  };
}

function validateEvent(value: unknown, nodeId: string, index: number): SyncEvent {
  const field = `events[${index}]`;
  const document = exactObject(value, EVENT_KEYS, field);
  for (const required of [
    "event_id",
    "origin_node_id",
    "sequence",
    "schema_version",
    "event_type",
    "occurred_at",
    "payload",
  ]) {
    requireValue(Object.hasOwn(document, required), `${field}.${required} is required`);
  }
  const originNodeId = boundedPattern(document.origin_node_id, NODE_ID, 42, `${field}.origin_node_id`);
  requireValue(originNodeId === nodeId, `${field}.origin_node_id is outside the authenticated node`);
  assertSafeJson(document.payload, `${field}.payload`);
  const event: SyncEvent = {
    event_id: boundedPattern(document.event_id, UUID_V4, 36, `${field}.event_id`),
    origin_node_id: originNodeId,
    sequence: positiveInteger(document.sequence, `${field}.sequence`),
    schema_version: positiveInteger(document.schema_version, `${field}.schema_version`),
    event_type: boundedPattern(document.event_type, EVENT_TYPE, 100, `${field}.event_type`),
    occurred_at: dateTime(document.occurred_at, `${field}.occurred_at`),
    payload: document.payload,
  };
  if (document.device_id !== undefined) {
    event.device_id = boundedPattern(document.device_id, DEVICE_ID, 42, `${field}.device_id`);
  }
  return event;
}

function validateCommandResult(value: unknown, nodeId: string, index: number): SyncCommandResult {
  const field = `command_results[${index}]`;
  const document = exactObject(value, RESULT_KEYS, field);
  for (const required of ["result_id", "command_id", "origin_node_id", "status", "occurred_at"]) {
    requireValue(Object.hasOwn(document, required), `${field}.${required} is required`);
  }
  const originNodeId = boundedPattern(document.origin_node_id, NODE_ID, 42, `${field}.origin_node_id`);
  requireValue(originNodeId === nodeId, `${field}.origin_node_id is outside the authenticated node`);
  requireValue(
    typeof document.status === "string" && RESULT_STATUSES.has(document.status),
    `${field}.status is invalid`,
  );
  const result: SyncCommandResult = {
    result_id: boundedPattern(document.result_id, UUID_V4, 36, `${field}.result_id`),
    command_id: boundedPattern(document.command_id, UUID_V4, 36, `${field}.command_id`),
    origin_node_id: originNodeId,
    status: document.status as SyncCommandResult["status"],
    occurred_at: dateTime(document.occurred_at, `${field}.occurred_at`),
  };
  if (document.error_code !== undefined) {
    result.error_code = boundedText(document.error_code, 1, 100, `${field}.error_code`);
  }
  if (document.message !== undefined) {
    result.message = boundedText(document.message, 0, 1000, `${field}.message`);
  }
  if (document.payload !== undefined) {
    assertSafeJson(document.payload, `${field}.payload`);
    result.payload = document.payload;
  }
  return result;
}

function validateHealth(value: unknown): SyncHealth {
  const document = exactObject(value, HEALTH_KEYS, "health");
  for (const required of [
    "status",
    "software_version",
    "outbox_depth",
    "mqtt_connected",
    "storage_free_bytes",
    "capabilities",
  ]) {
    requireValue(Object.hasOwn(document, required), `health.${required} is required`);
  }
  requireValue(
    document.status === "ok" || document.status === "degraded" || document.status === "critical",
    "health.status is invalid",
  );
  requireValue(typeof document.mqtt_connected === "boolean", "health.mqtt_connected must be a boolean");
  requireValue(
    Array.isArray(document.capabilities) && document.capabilities.length <= 50,
    "health.capabilities must contain at most 50 items",
  );
  const capabilities = document.capabilities.map((capability, index) =>
    boundedPattern(capability, EVENT_TYPE, 100, `health.capabilities[${index}]`),
  );
  rejectDuplicates(capabilities, "health capability");
  const storageTotal =
    document.storage_total_bytes === undefined
      ? undefined
      : nonnegativeInteger(document.storage_total_bytes, "health.storage_total_bytes");
  const storageFree = nonnegativeInteger(document.storage_free_bytes, "health.storage_free_bytes");
  if (storageTotal !== undefined) {
    requireValue(storageFree <= storageTotal, "health.storage_free_bytes exceeds total storage");
  }
  const health: SyncHealth = {
    status: document.status,
    software_version: boundedText(document.software_version, 1, 100, "health.software_version"),
    outbox_depth: nonnegativeInteger(document.outbox_depth, "health.outbox_depth"),
    mqtt_connected: document.mqtt_connected,
    storage_free_bytes: storageFree,
    capabilities,
  };
  if (document.hardware_profile_id !== undefined) {
    health.hardware_profile_id = boundedPattern(
      document.hardware_profile_id,
      HARDWARE_PROFILE,
      100,
      "health.hardware_profile_id",
    );
  }
  if (storageTotal !== undefined) {
    health.storage_total_bytes = storageTotal;
  }
  if (document.details !== undefined) {
    requireValue(isRecord(document.details), "health.details must be an object");
    requireValue(Object.keys(document.details).length <= 50, "health.details has too many properties");
    assertSafeJson(document.details, "health.details");
    health.details = document.details;
  }
  return health;
}

function exactObject<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  field: string,
): Record<string, unknown> {
  requireValue(isRecord(value), `${field} must be an object`);
  const allowedKeys = new Set<string>(allowed);
  for (const key of Object.keys(value)) {
    requireValue(allowedKeys.has(key), `${field}.${key} is not allowed`);
  }
  return value;
}

function optionalCursor(value: unknown): string | null {
  if (value === null) {
    return null;
  }
  return boundedText(value, 1, 1000, "cursor");
}

function boundedPattern(value: unknown, pattern: RegExp, maximum: number, field: string): string {
  const text = boundedText(value, 1, maximum, field);
  requireValue(pattern.test(text), `${field} has an invalid format`);
  return text;
}

function boundedText(value: unknown, minimum: number, maximum: number, field: string): string {
  requireValue(typeof value === "string", `${field} must be a string`);
  requireValue(value.length >= minimum && value.length <= maximum, `${field} has an invalid length`);
  return value;
}

function dateTime(value: unknown, field: string): string {
  const text = boundedText(value, 20, 40, field);
  requireValue(RFC3339.test(text) && Number.isFinite(Date.parse(text)), `${field} must be an RFC 3339 date-time`);
  return text;
}

function positiveInteger(value: unknown, field: string): number {
  requireValue(Number.isSafeInteger(value) && Number(value) >= 1, `${field} must be a positive integer`);
  return Number(value);
}

function nonnegativeInteger(value: unknown, field: string): number {
  requireValue(Number.isSafeInteger(value) && Number(value) >= 0, `${field} must be a non-negative integer`);
  return Number(value);
}

function rejectDuplicates(values: string[], field: string): void {
  requireValue(new Set(values).size === values.length, `${field} contains duplicates`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireValue(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new SyncValidationError(message);
  }
}
