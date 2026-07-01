import { createClient } from "@libsql/client/web";

import type { Env, SqlClient } from "./types";

export function createTursoClient(env: Env): SqlClient {
  const url = env.TURSO_DATABASE_URL?.trim();
  const authToken = env.TURSO_AUTH_TOKEN?.trim();
  if (!url) {
    throw new Error("TURSO_DATABASE_URL is not configured");
  }
  if (!authToken) {
    throw new Error("TURSO_AUTH_TOKEN is not configured");
  }
  return createClient({ url, authToken });
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

export function jsonPayload(value: unknown): string | null {
  if (value === undefined || value === null) {
    return null;
  }
  return JSON.stringify(value);
}
