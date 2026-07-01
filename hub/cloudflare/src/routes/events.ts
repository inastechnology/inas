import { Hono } from "hono";

import { requireRole } from "../access";
import type { AccessUser, AppServices, DeviceEventInput, Env } from "../types";

type Variables = {
  services: AppServices;
  user: AccessUser;
};

export function eventsRoutes() {
  const app = new Hono<{ Bindings: Env; Variables: Variables }>();

  app.get("/", async (c) => {
    const limit = parseLimit(c.req.query("limit"));
    const events = await c.get("services").deviceEvents.list({
      limit,
      deviceId: c.req.query("device_id"),
      eventType: c.req.query("event_type"),
      direction: c.req.query("direction"),
    });
    return c.json({ events });
  });

  app.post("/", requireRole("operator", "admin"), async (c) => {
    const body = await c.req.json().catch(() => null);
    const input = validateEventInput(body);
    if ("error" in input) {
      return c.json({ error: input.error }, 400);
    }
    const event = await c.get("services").deviceEvents.create(input.value);
    await c.get("services").auditLogs.append({
      actorEmail: c.get("user").email,
      action: "device_event.create",
      resourceType: "device_event",
      resourceId: String(event.id),
      payload: { device_id: event.device_id, event_type: event.event_type },
    });
    return c.json({ event }, 201);
  });

  return app;
}

function parseLimit(value?: string): number {
  if (!value) {
    return 100;
  }
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) {
    return 100;
  }
  return Math.max(1, Math.min(parsed, 500));
}

function validateEventInput(body: unknown): { value: DeviceEventInput } | { error: string } {
  if (!isRecord(body)) {
    return { error: "JSON body is required" };
  }
  if (typeof body.event_type !== "string" || body.event_type.trim().length === 0) {
    return { error: "event_type is required" };
  }
  if (typeof body.direction !== "string" || body.direction.trim().length === 0) {
    return { error: "direction is required" };
  }
  return {
    value: {
      occurred_at: stringOrUndefined(body.occurred_at),
      event_type: body.event_type,
      direction: body.direction,
      device_id: stringOrNull(body.device_id),
      topic: stringOrNull(body.topic),
      category: stringOrNull(body.category),
      action: stringOrNull(body.action),
      kind: stringOrNull(body.kind),
      seq_id: typeof body.seq_id === "number" || typeof body.seq_id === "string" ? body.seq_id : null,
      mqtt_rc: numberOrNull(body.mqtt_rc),
      retain: typeof body.retain === "boolean" ? body.retain : null,
      next_sleep_sec: numberOrNull(body.next_sleep_sec),
      next_wake_at: stringOrNull(body.next_wake_at),
      payload: body.payload ?? null,
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
