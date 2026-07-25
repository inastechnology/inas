import { describe, expect, it, vi } from "vitest";

import { createApp } from "../src";
import { AccessAuthenticationError } from "../src/access";
import { generateNodeCredential, nodeCredentialDigest } from "../src/crypto";
import type { CloudRuntime } from "../src/types";
import { EDGE_NODE_ID, node, runtime, services, syncRequest, syncResponse, tenant } from "./helpers";

const identity = async () => ({ email: "admin@example.com", subject: "access-user-admin" });
const syncEnvironment = {
  SYNC_NODE_RATE_LIMITER: {
    async limit() {
      return { success: true };
    },
  },
  SYNC_IP_RATE_LIMITER: {
    async limit() {
      return { success: true };
    },
  },
};

describe("Cloud Hub API tenant isolation", () => {
  it("resolves membership before opening a tenant database and never exposes credentials", async () => {
    const tenantServices = vi.fn(async () => services());
    const cloudRuntime = runtime({ tenantServices });
    const app = createApp({ accessVerifier: identity, runtimeFactory: () => cloudRuntime });

    const denied = await app.request("https://hub.example/api/t/tenant-b/dashboard", {}, {});
    expect(denied.status).toBe(404);
    expect(tenantServices).not.toHaveBeenCalled();

    const allowed = await app.request("https://hub.example/api/t/tenant-a/me", {}, {});
    expect(allowed.status).toBe(200);
    const body = await allowed.text();
    expect(body).toContain("Tenant A");
    expect(body).not.toContain(tenant().id);
    expect(body).not.toContain(tenant().databaseUrl);
    expect(body).not.toContain(tenant().encryptedAuthToken);
    expect(tenantServices).toHaveBeenCalledOnce();
  });

  it("does not initialize database access when Access verification fails", async () => {
    const runtimeFactory = vi.fn(() => runtime());
    const securityReporter = vi.fn(async () => undefined);
    const app = createApp({
      accessVerifier: async () => {
        throw new AccessAuthenticationError();
      },
      runtimeFactory,
      securityReporter,
    });
    const response = await app.request("https://hub.example/api/tenants", {}, {});
    expect(response.status).toBe(401);
    expect(runtimeFactory).not.toHaveBeenCalled();
    expect(securityReporter).toHaveBeenCalledWith(
      expect.any(Request),
      {},
      expect.objectContaining({
        kind: "access_authentication_rejected",
        status: 401,
        route: "/api/*",
      }),
    );
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
  });

  it("requires the configured same origin for browser mutations", async () => {
    const app = createApp({ accessVerifier: identity, runtimeFactory: () => runtime() });
    const response = await app.request(
      "https://hub.example/api/t/tenant-a/events",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://attacker.example",
        },
        body: JSON.stringify({ event_type: "management.note", payload: {} }),
      },
      { CLOUD_HUB_PUBLIC_ORIGIN: "https://hub.example" },
    );
    expect(response.status).toBe(403);

    const local = await app.request(
      "http://127.0.0.1:8787/api/t/tenant-a/events",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "http://127.0.0.1:8787",
        },
        body: JSON.stringify({ event_type: "management.note", payload: {} }),
      },
      { CLOUD_HUB_PUBLIC_ORIGIN: "http://127.0.0.1:8787" },
    );
    expect(local.status).toBe(201);
  });
});

describe("Cloud Hub Edge authentication", () => {
  it("binds a node credential to its directory-selected tenant database", async () => {
    const credential = generateNodeCredential();
    const digest = await nodeCredentialDigest(credential.token, credential.salt);
    const exchange = vi.fn(async (_registeredNode, request) => syncResponse(request));
    const touchNode = vi.fn(async () => undefined);
    const registeredNode = node({
      credentials: [
        {
          credentialId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          salt: credential.salt,
          digest,
          expiresAt: null,
        },
      ],
    });
    const tenantServices = vi.fn(async () => services({ sync: { exchange } }));
    const cloudRuntime: CloudRuntime = runtime({
      directory: {
        ...runtime().directory,
        async findNode(nodeId) {
          return nodeId === EDGE_NODE_ID ? registeredNode : null;
        },
        touchNode,
      },
      tenantServices,
    });
    const app = createApp({ accessVerifier: identity, runtimeFactory: () => cloudRuntime });
    const response = await app.request(
      `https://hub.example/sync/v1/nodes/${EDGE_NODE_ID}/exchange`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${credential.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(syncRequest()),
      },
      syncEnvironment,
    );
    expect(response.status).toBe(200);
    expect(tenantServices).toHaveBeenCalledWith(registeredNode.tenant);
    expect(exchange).toHaveBeenCalledOnce();
    expect(touchNode).toHaveBeenCalledWith(
      EDGE_NODE_ID,
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      "2026-07-23T10:00:01.000Z",
    );
  });

  it("authenticates before parsing and rejects a tenant override", async () => {
    const credential = generateNodeCredential();
    const digest = await nodeCredentialDigest(credential.token, credential.salt);
    const exchange = vi.fn(async (_registeredNode, request) => syncResponse(request));
    const cloudRuntime: CloudRuntime = runtime({
      directory: {
        ...runtime().directory,
        async findNode(nodeId) {
          return nodeId === EDGE_NODE_ID
            ? node({
                credentials: [
                  {
                    credentialId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    salt: credential.salt,
                    digest,
                    expiresAt: null,
                  },
                ],
              })
            : null;
        },
      },
      async tenantServices() {
        return services({ sync: { exchange } });
      },
    });
    const app = createApp({ accessVerifier: identity, runtimeFactory: () => cloudRuntime });
    const unknown = await app.request(
      `https://hub.example/sync/v1/nodes/${EDGE_NODE_ID}/exchange`,
      {
        method: "POST",
        headers: {
          Authorization: "Bearer AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
          "Content-Type": "text/plain",
        },
        body: "not-json",
      },
      syncEnvironment,
    );
    expect(unknown.status).toBe(401);

    const override = await app.request(
      `https://hub.example/sync/v1/nodes/${EDGE_NODE_ID}/exchange`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${credential.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ...syncRequest(), tenant_id: "tenant-b" }),
      },
      syncEnvironment,
    );
    expect(override.status).toBe(400);
    expect(exchange).not.toHaveBeenCalled();
  });

  it("rate limits repeated Sync authentication attempts before directory access", async () => {
    const findNode = vi.fn(async () => null);
    const app = createApp({
      accessVerifier: identity,
      runtimeFactory: () =>
        runtime({
          directory: {
            ...runtime().directory,
            findNode,
          },
        }),
    });
    const response = await app.request(
      `https://hub.example/sync/v1/nodes/${EDGE_NODE_ID}/exchange`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${"A".repeat(43)}`,
          "Content-Type": "application/json",
        },
        body: "{}",
      },
      {
        SYNC_NODE_RATE_LIMITER: {
          async limit() {
            return { success: false };
          },
        },
        SYNC_IP_RATE_LIMITER: {
          async limit() {
            return { success: true };
          },
        },
      },
    );
    expect(response.status).toBe(429);
    expect(response.headers.get("Retry-After")).toBe("60");
    expect(findNode).not.toHaveBeenCalled();
  });
});
