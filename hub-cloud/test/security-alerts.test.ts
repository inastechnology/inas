import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createSecurityAuditEvent,
  discordWebhookUrl,
  reportSecurityEvent,
  securityAlertRateLimitKey,
} from "../src/security-alerts";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Cloud Hub security audit events", () => {
  it("records only bounded request metadata", () => {
    const event = createSecurityAuditEvent(
      new Request("https://hub.example/sync/v1/nodes/secret?token=secret", {
        method: "POST",
        headers: {
          Authorization: "Bearer secret",
          "CF-Connecting-IP": "203.0.113.10",
          "CF-Ray": "abc123-NRT",
        },
        body: "secret body",
      }),
      {
        kind: "node_authentication_rejected",
        status: 401,
        authentication: "node",
        route: "/sync/v1/nodes/:nodeId/exchange",
      },
    );

    expect(event.method).toBe("POST");
    expect(event.cf_ray).toBe("abc123-NRT");
    expect(JSON.stringify(event)).not.toContain("203.0.113.10");
    expect(JSON.stringify(event)).not.toContain("Bearer");
    expect(JSON.stringify(event)).not.toContain("secret body");
    expect(JSON.stringify(event)).not.toContain("token=secret");
  });

  it("requires an exact Discord webhook destination", () => {
    expect(
      discordWebhookUrl("https://discord.com/api/webhooks/123/abc_DEF-456"),
    ).toBe("https://discord.com/api/webhooks/123/abc_DEF-456");
    expect(() =>
      discordWebhookUrl("https://attacker.example/api/webhooks/123/abc"),
    ).toThrow();
    expect(() =>
      discordWebhookUrl("https://discord.com/api/webhooks/123/abc?wait=true"),
    ).toThrow();
  });

  it("uses a bounded stable rate-limit key", () => {
    const key = securityAlertRateLimitKey({
      kind: "node_authentication_rejected",
      route: "/sync/v1/nodes/:nodeId/exchange",
    });
    expect(key).toBe("node-auth:sync");
    expect(new TextEncoder().encode(key).byteLength).toBeLessThanOrEqual(32);
  });

  it("sends one sanitized Discord alert when the limiter allows it", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    await reportSecurityEvent(
      new Request("https://hub.example/api/tenants?secret=value", {
        headers: {
          "CF-Ray": "abc123-NRT",
          Authorization: "Bearer secret",
        },
      }),
      {
        DISCORD_SECURITY_WEBHOOK_URL:
          "https://discord.com/api/webhooks/123/abc_DEF-456",
        SECURITY_ALERT_RATE_LIMITER: {
          async limit() {
            return { success: true };
          },
        },
      },
      {
        kind: "access_authentication_rejected",
        status: 401,
        authentication: "access",
        route: "/api/*",
      },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    const payload = String(init?.body);
    expect(payload).toContain("access_authentication_rejected");
    expect(payload).toContain("abc123-NRT");
    expect(payload).not.toContain("secret=value");
    expect(payload).not.toContain("Bearer secret");
  });

  it("keeps the audit log but suppresses repeated Discord alerts", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "info").mockImplementation(() => undefined);

    await reportSecurityEvent(
      new Request("https://hub.example/api/tenants"),
      {
        DISCORD_SECURITY_WEBHOOK_URL:
          "https://discord.com/api/webhooks/123/abc_DEF-456",
        SECURITY_ALERT_RATE_LIMITER: {
          async limit() {
            return { success: false };
          },
        },
      },
      {
        kind: "access_authentication_rejected",
        status: 401,
        authentication: "access",
        route: "/api/*",
      },
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalledOnce();
  });
});
