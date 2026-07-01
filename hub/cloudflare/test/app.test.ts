import { describe, expect, it } from "vitest";

import { createApp } from "../src";
import type { AppServices, DeviceEventInput, DeviceEventRecord, Env, Role } from "../src/types";

const baseEnv: Env = {
  CLOUDFLARE_ACCESS_TEAM_DOMAIN: "https://team.cloudflareaccess.com",
  CLOUDFLARE_ACCESS_POLICY_AUD: "aud",
  TURSO_DATABASE_URL: "libsql://example.turso.io",
  TURSO_AUTH_TOKEN: "secret",
};

describe("cloud hub app", () => {
  it("exposes health without Access JWT", async () => {
    const app = createApp({ servicesFactory: () => fakeServices({}) });

    const response = await app.request("/api/health", {}, baseEnv);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ ok: true, service: "ina-device-hub-cloud" });
  });

  it("rejects API requests without Access JWT", async () => {
    const app = createApp({ servicesFactory: () => fakeServices({}) });

    const response = await app.request("/api/me", {}, baseEnv);

    expect(response.status).toBe(401);
  });

  it("rejects authenticated users that are not registered in admin_users", async () => {
    const app = createApp({
      servicesFactory: () => fakeServices({}),
      verifyAccessJwt: async () => ({ email: "unknown@example.com" }),
    });

    const response = await app.request("/api/me", { headers: accessHeaders() }, baseEnv);

    expect(response.status).toBe(403);
  });

  it("returns the authenticated user role", async () => {
    const app = createApp({
      servicesFactory: () => fakeServices({ roleByEmail: { "reader@example.com": "reader" } }),
      verifyAccessJwt: async () => ({ email: "reader@example.com" }),
    });

    const response = await app.request("/api/me", { headers: accessHeaders() }, baseEnv);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ user: { email: "reader@example.com", role: "reader" } });
  });

  it("allows readers to list events", async () => {
    const services = fakeServices({
      roleByEmail: { "reader@example.com": "reader" },
      events: [
        {
          id: 10,
          occurred_at: "2026-07-01T00:00:00.000Z",
          event_type: "mqtt_message_received",
          direction: "inbound",
          device_id: "INADS-1",
          topic: "sensor/1",
          category: "sensor",
          action: "telemetry",
          kind: null,
          seq_id: "1",
          mqtt_rc: null,
          retain: null,
          next_sleep_sec: null,
          next_wake_at: null,
          payload: { temp: 24.1 },
        },
      ],
    });
    const app = createApp({
      servicesFactory: () => services,
      verifyAccessJwt: async () => ({ email: "reader@example.com" }),
    });

    const response = await app.request("/api/events?device_id=INADS-1&limit=50", { headers: accessHeaders() }, baseEnv);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ events: [{ id: 10, device_id: "INADS-1" }] });
  });

  it("prevents readers from creating events", async () => {
    const app = createApp({
      servicesFactory: () => fakeServices({ roleByEmail: { "reader@example.com": "reader" } }),
      verifyAccessJwt: async () => ({ email: "reader@example.com" }),
    });

    const response = await app.request("/api/events", jsonRequest({ event_type: "manual_note", direction: "inbound" }), baseEnv);

    expect(response.status).toBe(403);
  });

  it("allows operators to create events and writes an audit log", async () => {
    const services = fakeServices({ roleByEmail: { "operator@example.com": "operator" } });
    const app = createApp({
      servicesFactory: () => services,
      verifyAccessJwt: async () => ({ email: "operator@example.com" }),
    });

    const response = await app.request(
      "/api/events",
      jsonRequest({
        event_type: "manual_note",
        direction: "inbound",
        device_id: "INADS-2",
        payload: { note: "checked" },
      }),
      baseEnv,
    );

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toMatchObject({ event: { id: 1, device_id: "INADS-2", event_type: "manual_note" } });
    expect(services.auditEntries).toEqual([
      {
        actorEmail: "operator@example.com",
        action: "device_event.create",
        resourceType: "device_event",
        resourceId: "1",
        payload: { device_id: "INADS-2", event_type: "manual_note" },
      },
    ]);
  });
});

function accessHeaders() {
  return { "cf-access-jwt-assertion": "test.jwt" };
}

function jsonRequest(body: unknown) {
  return {
    method: "POST",
    headers: { ...accessHeaders(), "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

function fakeServices(options: { roleByEmail?: Record<string, Role>; events?: DeviceEventRecord[] }) {
  const events = [...(options.events ?? [])];
  const auditEntries: Array<{ actorEmail: string; action: string; resourceType: string; resourceId?: string | null; payload?: unknown }> = [];
  const services: AppServices & { auditEntries: typeof auditEntries } = {
    auditEntries,
    deviceEvents: {
      async list() {
        return events;
      },
      async create(input: DeviceEventInput) {
        const event: DeviceEventRecord = {
          id: events.length + 1,
          occurred_at: input.occurred_at ?? "2026-07-01T00:00:00.000Z",
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
        events.unshift(event);
        return event;
      },
    },
    adminUsers: {
      async roleForEmail(email: string) {
        return options.roleByEmail?.[email] ?? null;
      },
    },
    auditLogs: {
      async append(entry) {
        auditEntries.push(entry);
      },
    },
  };
  return services;
}
