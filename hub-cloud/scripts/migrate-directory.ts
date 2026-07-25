import { createClient } from "@libsql/client";

import { normalizeTursoDatabaseUrl } from "../src/database";
import { applyMigrations } from "./migrations";

const url = normalizeTursoDatabaseUrl(
  requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
  "DIRECTORY_TURSO_DATABASE_URL",
);
const authToken = requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN");
const client = createClient({ url, authToken });

try {
  const applied = await applyMigrations(client, new URL("../migrations/directory/", import.meta.url));
  console.log(
    JSON.stringify(
      {
        database: url,
        applied,
        status: applied.length ? "migrated" : "up-to-date",
      },
      null,
      2,
    ),
  );
} finally {
  client.close();
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}
