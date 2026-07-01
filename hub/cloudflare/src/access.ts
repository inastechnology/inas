import type { Context, MiddlewareHandler } from "hono";
import { createRemoteJWKSet, jwtVerify } from "jose";

import type { AccessUser, AppServices, Env, Role } from "./types";

export type VerifyAccessJwt = (token: string, env: Env) => Promise<{ email: string }>;

export async function verifyAccessJwt(token: string, env: Env): Promise<{ email: string }> {
  const issuer = normalizeIssuer(env.CLOUDFLARE_ACCESS_TEAM_DOMAIN);
  const audience = env.CLOUDFLARE_ACCESS_POLICY_AUD?.trim();
  if (!issuer || !audience) {
    throw new Error("Cloudflare Access env is not configured");
  }

  const jwks = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
  const result = await jwtVerify(token, jwks, { issuer, audience });
  const email = result.payload.email;
  if (typeof email !== "string" || email.trim().length === 0) {
    throw new Error("Cloudflare Access token did not include email");
  }
  return { email: email.toLowerCase() };
}

export function normalizeIssuer(value?: string): string {
  const trimmed = value?.trim().replace(/\/+$/, "") ?? "";
  if (!trimmed) {
    return "";
  }
  return trimmed.startsWith("http://") || trimmed.startsWith("https://") ? trimmed : `https://${trimmed}`;
}

export function accessAuth(options: { services: (c: Context) => AppServices; verify?: VerifyAccessJwt }): MiddlewareHandler<{ Bindings: Env; Variables: { user: AccessUser } }> {
  const verify = options.verify ?? verifyAccessJwt;
  return async (c, next) => {
    const token = c.req.header("cf-access-jwt-assertion");
    if (!token) {
      return c.json({ error: "missing Cloudflare Access JWT" }, 401);
    }

    let identity: { email: string };
    try {
      identity = await verify(token, c.env);
    } catch {
      return c.json({ error: "invalid Cloudflare Access JWT" }, 401);
    }

    const role = await options.services(c).adminUsers.roleForEmail(identity.email);
    if (!role) {
      return c.json({ error: "user is not registered for cloud hub access" }, 403);
    }
    c.set("user", { email: identity.email, role });
    await next();
  };
}

export function requireRole(...allowed: Role[]): MiddlewareHandler<{ Bindings: Env; Variables: { user: AccessUser } }> {
  return async (c, next) => {
    const user = c.get("user");
    if (!user || !allowed.includes(user.role)) {
      return c.json({ error: "insufficient role" }, 403);
    }
    await next();
  };
}
