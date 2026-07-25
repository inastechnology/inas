import { createClient } from "@libsql/client/web";

import type { Env, SqlClient, SqlResultSet, SqlStatement } from "./types";

export function createDirectoryClient(env: Env): SqlClient {
  const url = normalizeTursoDatabaseUrl(
    requiredEnv(env.DIRECTORY_TURSO_DATABASE_URL, "DIRECTORY_TURSO_DATABASE_URL"),
    "DIRECTORY_TURSO_DATABASE_URL",
  );
  const authToken = requiredEnv(env.DIRECTORY_TURSO_AUTH_TOKEN, "DIRECTORY_TURSO_AUTH_TOKEN");
  return createClient({ url, authToken });
}

export function createTenantClient(url: string, authToken: string): SqlClient {
  if (!authToken.trim()) {
    throw new Error("tenant database credentials are incomplete");
  }
  return createClient({
    url: normalizeTursoDatabaseUrl(url, "tenant database URL"),
    authToken: authToken.trim(),
  });
}

export function requiredEnv(value: string | undefined, name: string): string {
  const normalized = value?.trim() ?? "";
  if (!normalized) {
    throw new Error(`${name} is not configured`);
  }
  return normalized;
}

export function jsonPayload(value: unknown): string | null {
  return value === undefined || value === null ? null : JSON.stringify(value);
}

export function parseJsonPayload(value: unknown): unknown {
  if (typeof value !== "string" || value.length === 0) {
    return value ?? null;
  }
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalValue(value));
}

export function normalizeTursoDatabaseUrl(value: string, name = "Turso database URL"): string {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error(`${name} is not a valid URL`);
  }
  if (
    url.protocol !== "libsql:" ||
    !url.hostname.endsWith(".turso.io") ||
    url.hostname === "turso.io" ||
    !isValidDnsHostname(url.hostname) ||
    url.username ||
    url.password ||
    url.port ||
    (url.pathname !== "" && url.pathname !== "/") ||
    url.search ||
    url.hash
  ) {
    throw new Error(`${name} must be an exact libsql://*.turso.io database origin`);
  }
  return `libsql://${url.hostname}`;
}

function isValidDnsHostname(hostname: string): boolean {
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

export async function batchStatements(
  client: SqlClient,
  statements: SqlStatement[],
  mode: "deferred" | "read" | "write" = "write",
): Promise<SqlResultSet[]> {
  if (!client.batch) {
    throw new Error("database client does not support atomic batches");
  }
  return client.batch(statements, mode);
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalValue);
  }
  if (value && typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new Error("canonical JSON accepts only plain objects");
    }
    const result: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      result[key] = canonicalValue((value as Record<string, unknown>)[key]);
    }
    return result;
  }
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new Error("canonical JSON does not accept non-finite numbers");
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  throw new Error("canonical JSON contains an unsupported value");
}
