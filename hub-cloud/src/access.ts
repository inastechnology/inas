import { createRemoteJWKSet, jwtVerify } from "jose";
import type { JWTPayload } from "jose";

import { requiredEnv } from "./database";
import { normalizeEmail } from "./tenant-id";
import type { AccessIdentity, Env } from "./types";

const remoteKeySets = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

export async function verifyAccessRequest(request: Request, env: Env): Promise<AccessIdentity> {
  const assertion = request.headers.get("Cf-Access-Jwt-Assertion")?.trim() ?? "";
  if (!assertion || assertion.length > 16_384) {
    throw new AccessAuthenticationError();
  }
  const teamOrigin = accessTeamOrigin(
    requiredEnv(env.CLOUDFLARE_ACCESS_TEAM_DOMAIN, "CLOUDFLARE_ACCESS_TEAM_DOMAIN"),
  );
  const audience = requiredEnv(env.CLOUDFLARE_ACCESS_POLICY_AUD, "CLOUDFLARE_ACCESS_POLICY_AUD");
  const jwksUrl = `${teamOrigin}/cdn-cgi/access/certs`;
  let keySet = remoteKeySets.get(jwksUrl);
  if (!keySet) {
    keySet = createRemoteJWKSet(new URL(jwksUrl));
    remoteKeySets.set(jwksUrl, keySet);
  }
  try {
    const { payload } = await jwtVerify(assertion, keySet, {
      issuer: teamOrigin,
      audience,
      algorithms: ["RS256"],
      requiredClaims: ["exp", "iat", "nbf", "sub"],
      clockTolerance: 10,
    });
    assertAccessTokenTimeClaims(payload);
    return accessIdentityFromClaims(payload);
  } catch (error) {
    if (error instanceof AccessAuthenticationError) {
      throw error;
    }
    throw new AccessAuthenticationError();
  }
}

export function assertAccessTokenTimeClaims(
  payload: JWTPayload,
  nowSeconds = Math.floor(Date.now() / 1000),
): void {
  const { exp, iat, nbf } = payload;
  if (
    !Number.isSafeInteger(exp) ||
    !Number.isSafeInteger(iat) ||
    !Number.isSafeInteger(nbf) ||
    Number(iat) > nowSeconds + 10 ||
    Number(nbf) > nowSeconds + 10 ||
    Number(exp) <= nowSeconds - 10 ||
    Number(exp) <= Number(iat) ||
    Number(exp) < Number(nbf)
  ) {
    throw new AccessAuthenticationError();
  }
}

export function accessIdentityFromClaims(payload: JWTPayload): AccessIdentity {
  if (
    payload.type !== "app" ||
    typeof payload.email !== "string" ||
    typeof payload.sub !== "string" ||
    payload.sub.length === 0 ||
    payload.sub.length > 512 ||
    /[\u0000-\u001f\u007f]/.test(payload.sub)
  ) {
    throw new AccessAuthenticationError();
  }
  try {
    return {
      email: normalizeEmail(payload.email),
      subject: payload.sub,
    };
  } catch {
    throw new AccessAuthenticationError();
  }
}

export class AccessAuthenticationError extends Error {
  constructor() {
    super("Cloudflare Access authentication failed");
    this.name = "AccessAuthenticationError";
  }
}

export function accessTeamOrigin(value: string): string {
  const candidate = value.includes("://") ? value : `https://${value}`;
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new Error("CLOUDFLARE_ACCESS_TEAM_DOMAIN is not a valid URL");
  }
  if (
    url.protocol !== "https:" ||
    !url.hostname.endsWith(".cloudflareaccess.com") ||
    !validDnsHostname(url.hostname) ||
    url.port ||
    url.username ||
    url.password ||
    (url.pathname !== "/" && url.pathname !== "") ||
    url.search ||
    url.hash
  ) {
    throw new Error("CLOUDFLARE_ACCESS_TEAM_DOMAIN must be an HTTPS cloudflareaccess.com origin");
  }
  return url.origin;
}

function validDnsHostname(hostname: string): boolean {
  return (
    hostname.length <= 253 &&
    hostname.split(".").every(
      (label) =>
        label.length >= 1 &&
        label.length <= 63 &&
        /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label),
    )
  );
}
