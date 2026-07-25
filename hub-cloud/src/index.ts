import { Hono } from "hono";
import type { Context, Next } from "hono";

import { AccessAuthenticationError, verifyAccessRequest } from "./access";
import { verifyNodeCredential } from "./crypto";
import { assertSafeJson, JsonSafetyError } from "./json-safety";
import { RequestBodyError, readSyncJson } from "./request-body";
import { SyncConflictError } from "./repositories/sync";
import { createCloudRuntime } from "./runtime";
import {
  reportSecurityEvent,
  type SecurityEventInput,
  type SecurityReporter,
} from "./security-alerts";
import { normalizePublicTenantId } from "./tenant-id";
import { SyncValidationError, validateSyncRequest } from "./sync-validation";
import type {
  AccessIdentity,
  AppVariables,
  CloudRuntime,
  Env,
  NodeCredentialRecord,
  Role,
  TenantRecord,
} from "./types";

type CloudHubApp = {
  Bindings: Env;
  Variables: AppVariables;
};

export interface AppDependencies {
  runtimeFactory?: (env: Env) => CloudRuntime;
  accessVerifier?: (request: Request, env: Env) => Promise<AccessIdentity>;
  securityReporter?: SecurityReporter;
}

const ROLE_RANK: Record<Role, number> = {
  reader: 0,
  operator: 1,
  admin: 2,
};
const NODE_ID = /^INAEG-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DEVICE_ID = /^INADS-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const EVENT_TYPE = /^[a-z][a-z0-9_.-]{0,99}$/;
const NODE_BEARER = /^Bearer ([A-Za-z0-9_-]{43})$/;
const DUMMY_NODE_CREDENTIAL = {
  salt: "A".repeat(22),
  digest: "0".repeat(64),
};

export function createApp(dependencies: AppDependencies = {}): Hono<CloudHubApp> {
  const runtimeFactory = dependencies.runtimeFactory ?? createCloudRuntime;
  const accessVerifier = dependencies.accessVerifier ?? verifyAccessRequest;
  const securityReporter = dependencies.securityReporter ?? reportSecurityEvent;
  const app = new Hono<CloudHubApp>();

  app.use("*", async (context, next) => {
    try {
      await next();
    } finally {
      setSecurityHeaders(context);
    }
  });

  app.get("/healthz", (context) =>
    noStoreJson(context, {
      status: "ok",
      service: "inas-hub-cloud",
    }),
  );

  app.use("/api/*", async (context, next) => {
    const identity = await accessVerifier(context.req.raw, context.env);
    requireSameOriginMutation(context.req.raw, context.env);
    context.set("accessIdentity", identity);
    context.set("runtime", runtimeFactory(context.env));
    await next();
  });

  app.get("/api/tenants", async (context) => {
    const identity = context.get("accessIdentity");
    const memberships = await context.get("runtime").directory.listMemberships(identity);
    return noStoreJson(context, {
      user: { email: identity.email },
      tenants: memberships.map((tenant) => ({
        public_id: tenant.publicId,
        display_name: tenant.displayName,
        role: tenant.role,
      })),
    });
  });

  app.get("/api/session/start", (context) => {
    const current = new URL(context.req.url);
    let target = "/";
    try {
      const requested = new URL(context.req.query("return") || "/", current.origin);
      if (
        requested.origin === current.origin &&
        (requested.pathname === "/" ||
          /^\/t\/[a-z0-9](?:[a-z0-9-]{4,30}[a-z0-9])\/?$/.test(requested.pathname))
      ) {
        target = `${requested.pathname}${requested.search}`;
      }
    } catch {
      target = "/";
    }
    context.header("Cache-Control", "no-store");
    return context.redirect(target, 302);
  });

  app.use("/api/t/:publicId/*", async (context, next) => {
    let publicId: string;
    try {
      publicId = normalizePublicTenantId(context.req.param("publicId"));
    } catch {
      return context.json({ error: "Hub was not found" }, 404);
    }
    const identity = context.get("accessIdentity");
    const membership = await context.get("runtime").directory.resolveMembership(publicId, identity);
    if (!membership) {
      return context.json({ error: "Hub was not found" }, 404);
    }
    const { role, ...tenant } = membership;
    context.set("tenant", tenant);
    context.set("user", { email: identity.email, role });
    context.set("tenantServices", await context.get("runtime").tenantServices(tenant));
    await next();
  });

  app.get("/api/t/:publicId/me", (context) => {
    const tenant = context.get("tenant");
    return noStoreJson(context, {
      tenant: publicTenant(tenant),
      user: context.get("user"),
    });
  });

  app.get("/api/t/:publicId/dashboard", async (context) =>
    noStoreJson(context, await context.get("tenantServices").dashboard.summary()),
  );

  app.get("/api/t/:publicId/nodes", async (context) => {
    const nodes = await context.get("runtime").directory.listTenantNodes(context.get("tenant").id);
    return noStoreJson(context, {
      nodes: nodes.map((registeredNode) => ({
        node_id: registeredNode.nodeId,
        label: registeredNode.label,
        node_type: registeredNode.nodeType,
        status: registeredNode.status,
        last_seen_at: registeredNode.lastSeenAt,
      })),
    });
  });

  app.get("/api/t/:publicId/events", async (context) => {
    const limit = integerQuery(context.req.query("limit"), 30, 1, 200);
    const deviceId = optionalQuery(context.req.query("device_id"), DEVICE_ID, "device_id");
    const eventType = optionalQuery(context.req.query("event_type"), EVENT_TYPE, "event_type");
    const events = await context.get("tenantServices").events.list({ deviceId, eventType, limit });
    return noStoreJson(context, { events });
  });

  app.post("/api/t/:publicId/events", async (context) => {
    requireRole(context, "operator");
    const value = await readApiJson(context.req.raw);
    if (!isRecord(value)) {
      throw new ApiInputError("request body must be an object");
    }
    rejectUnknownKeys(value, new Set(["event_type", "device_id", "payload"]));
    if (typeof value.event_type !== "string" || !EVENT_TYPE.test(value.event_type)) {
      throw new ApiInputError("event_type is invalid");
    }
    if (value.device_id !== undefined && value.device_id !== null) {
      if (typeof value.device_id !== "string" || !DEVICE_ID.test(value.device_id)) {
        throw new ApiInputError("device_id is invalid");
      }
    }
    assertSafeJson(value.payload ?? null, "payload");
    const event = await context.get("tenantServices").events.createManagementEvent({
      actorEmail: context.get("user").email,
      eventType: value.event_type,
      deviceId: value.device_id as string | null | undefined,
      payload: value.payload,
    });
    return noStoreJson(context, { event }, 201);
  });

  app.post("/sync/v1/nodes/:nodeId/exchange", async (context) => {
    const nodeId = context.req.param("nodeId");
    const authorization = context.req.header("Authorization") ?? "";
    const credential = NODE_BEARER.exec(authorization)?.[1];
    if (!NODE_ID.test(nodeId) || !credential) {
      throw new NodeAuthenticationError();
    }
    await enforceNodeRequestRateLimit(context.req.raw, context.env, nodeId);
    const runtime = runtimeFactory(context.env);
    const node = await runtime.directory.findNode(nodeId);
    const authenticatedCredential = await matchingNodeCredential(
      credential,
      node?.credentials ?? [],
    );
    if (!node || node.nodeType !== "edge_gateway" || !authenticatedCredential) {
      throw new NodeAuthenticationError();
    }
    const document = await readSyncJson(context.req.raw);
    const request = validateSyncRequest(document, nodeId, node);
    const services = await runtime.tenantServices(node.tenant);
    const response = await services.sync.exchange(node, request);
    await runtime.directory.touchNode(
      node.nodeId,
      authenticatedCredential.credentialId,
      response.server_time,
    );
    return noStoreJson(context, response);
  });

  app.all("*", async (context) => {
    if (context.env.ASSETS) {
      return context.env.ASSETS.fetch(context.req.raw);
    }
    return context.json({ error: "Not found" }, 404);
  });

  app.onError(async (error, context) => {
    if (error instanceof AccessAuthenticationError || error instanceof NodeAuthenticationError) {
      const authentication = error instanceof AccessAuthenticationError ? "access" : "node";
      await recordSecurityEvent(securityReporter, context, {
        kind:
          authentication === "access"
            ? "access_authentication_rejected"
            : "node_authentication_rejected",
        status: 401,
        authentication,
        route: authenticationPath(context.req.path),
      });
      return noStoreJson(context, { error: "Authentication required" }, 401);
    }
    if (error instanceof AuthorizationError) {
      await recordSecurityEvent(securityReporter, context, {
        kind: "authorization_rejected",
        status: 403,
        authentication: "access",
        route: authenticationPath(context.req.path),
      });
      return noStoreJson(context, { error: "Insufficient role" }, 403);
    }
    if (error instanceof CsrfError) {
      await recordSecurityEvent(securityReporter, context, {
        kind: "cross_origin_mutation_rejected",
        status: 403,
        authentication: "access",
        route: authenticationPath(context.req.path),
      });
      return noStoreJson(context, { error: "Insufficient role" }, 403);
    }
    if (error instanceof SyncRateLimitError) {
      await recordSecurityEvent(securityReporter, context, {
        kind: "sync_rate_limit_exceeded",
        status: 429,
        authentication: "node",
        route: authenticationPath(context.req.path),
      });
      context.header("Retry-After", "60");
      return noStoreJson(context, { error: "Too many requests" }, 429);
    }
    if (error instanceof RequestBodyError) {
      if (error.status === 413) {
        await recordSecurityEvent(securityReporter, context, {
          kind: "oversized_request_rejected",
          status: 413,
          authentication: context.req.path.startsWith("/sync/") ? "node" : "access",
          route: authenticationPath(context.req.path),
        });
      }
      return noStoreJson(context, { error: error.message }, error.status as 400 | 413 | 415);
    }
    if (
      error instanceof SyncValidationError ||
      error instanceof ApiInputError ||
      error instanceof JsonSafetyError
    ) {
      return noStoreJson(context, { error: error.message }, 400);
    }
    if (error instanceof SyncConflictError) {
      return noStoreJson(context, { error: error.message }, 409);
    }
    console.error("Cloud Hub request failed", {
      name: error.name,
      path: context.req.path,
    });
    return noStoreJson(context, { error: "Internal server error" }, 500);
  });

  return app;
}

async function recordSecurityEvent(
  reporter: SecurityReporter,
  context: Context<CloudHubApp>,
  input: SecurityEventInput,
): Promise<void> {
  try {
    await reporter(context.req.raw, context.env, input);
  } catch (error) {
    console.error("cloud_hub_security_reporter_failed", {
      reason: error instanceof Error ? error.name : "unknown_error",
      route: input.route,
    });
  }
}

class NodeAuthenticationError extends Error {
  constructor() {
    super("node authentication failed");
    this.name = "NodeAuthenticationError";
  }
}

class AuthorizationError extends Error {
  constructor() {
    super("role is insufficient");
    this.name = "AuthorizationError";
  }
}

class ApiInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiInputError";
  }
}

class CsrfError extends Error {
  constructor() {
    super("request origin is not allowed");
    this.name = "CsrfError";
  }
}

class SyncRateLimitError extends Error {
  constructor() {
    super("Sync request rate limit exceeded");
    this.name = "SyncRateLimitError";
  }
}

function publicTenant(tenant: TenantRecord): Record<string, string> {
  return {
    public_id: tenant.publicId,
    display_name: tenant.displayName,
    status: tenant.status,
  };
}

function requireRole(context: Context<CloudHubApp>, required: Role): void {
  if (ROLE_RANK[context.get("user").role] < ROLE_RANK[required]) {
    throw new AuthorizationError();
  }
}

function integerQuery(value: string | undefined, fallback: number, minimum: number, maximum: number): number {
  if (value === undefined || value === "") {
    return fallback;
  }
  if (!/^[0-9]+$/.test(value)) {
    throw new ApiInputError("limit is invalid");
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new ApiInputError(`limit must be between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function optionalQuery(value: string | undefined, pattern: RegExp, name: string): string | undefined {
  if (value === undefined || value === "") {
    return undefined;
  }
  if (!pattern.test(value)) {
    throw new ApiInputError(`${name} is invalid`);
  }
  return value;
}

async function readApiJson(request: Request): Promise<unknown> {
  const mediaType = request.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new RequestBodyError("Content-Type must be application/json", 415);
  }
  const declaredLength = request.headers.get("Content-Length");
  if (declaredLength && (!/^[0-9]+$/.test(declaredLength) || Number(declaredLength) > 64 * 1024)) {
    throw new RequestBodyError("request body exceeds 64 KiB", 413);
  }
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength > 64 * 1024) {
    throw new RequestBodyError("request body exceeds 64 KiB", 413);
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new ApiInputError("request body is not valid JSON");
  }
}

function rejectUnknownKeys(value: Record<string, unknown>, allowed: Set<string>): void {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) {
      throw new ApiInputError(`${key} is not allowed`);
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function setSecurityHeaders(context: Context<CloudHubApp>): void {
  context.header(
    "Content-Security-Policy",
    "default-src 'self'; base-uri 'none'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self'",
  );
  context.header("Cross-Origin-Opener-Policy", "same-origin");
  context.header("Cross-Origin-Resource-Policy", "same-origin");
  context.header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()");
  context.header("Referrer-Policy", "no-referrer");
  context.header("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  context.header("X-Content-Type-Options", "nosniff");
  context.header("X-Frame-Options", "DENY");
  context.header("X-Permitted-Cross-Domain-Policies", "none");
}

function requireSameOriginMutation(request: Request, env: Env): void {
  if (request.method === "GET" || request.method === "HEAD" || request.method === "OPTIONS") {
    return;
  }
  const configuredOrigin = requiredPublicOrigin(env.CLOUD_HUB_PUBLIC_ORIGIN);
  const requestUrl = new URL(request.url);
  const suppliedOrigin = request.headers.get("Origin");
  if (requestUrl.origin !== configuredOrigin || suppliedOrigin !== configuredOrigin) {
    throw new CsrfError();
  }
}

function requiredPublicOrigin(value: string | undefined): string {
  let url: URL;
  try {
    url = new URL(value?.trim() ?? "");
  } catch {
    throw new Error("CLOUD_HUB_PUBLIC_ORIGIN is not configured as a valid URL");
  }
  const isLoopbackDevelopment =
    url.protocol === "http:" &&
    (url.hostname === "localhost" ||
      url.hostname === "127.0.0.1" ||
      url.hostname === "[::1]");
  if (
    (url.protocol !== "https:" && !isLoopbackDevelopment) ||
    url.username ||
    url.password ||
    (url.protocol === "https:" && url.port) ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("CLOUD_HUB_PUBLIC_ORIGIN must be an exact HTTPS origin");
  }
  return url.origin;
}

async function enforceNodeRequestRateLimit(request: Request, env: Env, nodeId: string): Promise<void> {
  if (!env.SYNC_NODE_RATE_LIMITER?.limit || !env.SYNC_IP_RATE_LIMITER?.limit) {
    throw new Error("Sync rate limit bindings are not configured");
  }
  const connectingIp = request.headers.get("CF-Connecting-IP")?.trim() || "unknown";
  const [nodeResult, ipResult] = await Promise.all([
    env.SYNC_NODE_RATE_LIMITER.limit({ key: nodeId }),
    env.SYNC_IP_RATE_LIMITER.limit({ key: connectingIp }),
  ]);
  if (!nodeResult.success || !ipResult.success) {
    throw new SyncRateLimitError();
  }
}

function authenticationPath(path: string): SecurityEventInput["route"] {
  if (path.startsWith("/sync/v1/nodes/")) {
    return "/sync/v1/nodes/:nodeId/exchange";
  }
  if (path.startsWith("/api/")) {
    return "/api/*";
  }
  return "/";
}

async function matchingNodeCredential(
  token: string,
  credentials: NodeCredentialRecord[],
): Promise<NodeCredentialRecord | null> {
  const candidates = credentials.slice(0, 2);
  const checks = [
    ...candidates.map(async (credential) => ({
      credential,
      matches: await verifyNodeCredential(token, credential.salt, credential.digest),
    })),
    ...Array.from({ length: 2 - candidates.length }, async () => ({
      credential: null,
      matches: await verifyNodeCredential(
        token,
        DUMMY_NODE_CREDENTIAL.salt,
        DUMMY_NODE_CREDENTIAL.digest,
      ),
    })),
  ];
  const matches = await Promise.all(checks);
  return matches.find((result) => result.credential && result.matches)?.credential ?? null;
}

function noStoreJson<T>(
  context: Context<CloudHubApp>,
  value: T,
  status: 200 | 201 | 400 | 401 | 403 | 404 | 409 | 413 | 415 | 429 | 500 = 200,
): Response {
  context.header("Cache-Control", "no-store");
  return context.json(value, status);
}

const app = createApp();
export default app;
