import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

import { createClient, type Client } from "@libsql/client";

import { normalizeTursoDatabaseUrl } from "../src/database";

const CORE_TABLES = [
  "schema_migrations",
  "tenants",
  "tenant_memberships",
  "edge_nodes",
  "edge_node_credentials",
  "directory_audit_logs",
] as const;

const execute = process.argv.includes("--execute");
const keep = process.argv.includes("--keep");
const sourceName =
  process.env.DIRECTORY_TURSO_DATABASE_NAME?.trim() || "inas-cloud-directory";
const groupName = process.env.TURSO_GROUP?.trim() || "ina-technologies";
const sourceUrl = normalizeTursoDatabaseUrl(
  requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
  "DIRECTORY_TURSO_DATABASE_URL",
);
const sourceToken = requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN");
validateDatabaseName(sourceName, "DIRECTORY_TURSO_DATABASE_NAME");
validateDatabaseName(groupName, "TURSO_GROUP");

const restorePoint = new Date(Date.now() - 120_000);
const recoveryName = `${sourceName}-drill-${compactTimestamp(new Date())}`;
validateDatabaseName(recoveryName, "recovery database name");

if (!execute) {
  console.log(
    JSON.stringify(
      {
        status: "planned",
        source_database: sourceName,
        recovery_database: recoveryName,
        restore_point: restorePoint.toISOString(),
        cleanup_after_success: !keep,
        checks: ["integrity_check", "schema_sha256", "core_table_row_counts"],
      },
      null,
      2,
    ),
  );
  process.exit(0);
}

if (!/Delete Protection on/i.test(runTurso([
  "db",
  "config",
  "delete-protection",
  "show",
  sourceName,
]))) {
  throw new Error("Directory recovery drill requires source delete protection to be enabled");
}

let created = false;
let verified = false;
try {
  runTurso([
    "db",
    "create",
    recoveryName,
    "--from-db",
    sourceName,
    "--timestamp",
    restorePoint.toISOString(),
    "--group",
    groupName,
    "--wait",
  ]);
  created = true;
  const recoveryUrl = extractUrl(runTurso(["db", "show", recoveryName, "--url"]));
  const recoveryToken = extractJwt(
    runTurso([
      "db",
      "tokens",
      "create",
      recoveryName,
      "--read-only",
      "--expiration",
      "1d",
    ]),
  );

  const source = createClient({ url: sourceUrl, authToken: sourceToken });
  const recovery = createClient({ url: recoveryUrl, authToken: recoveryToken });
  try {
    const [sourceSnapshot, recoverySnapshot] = await Promise.all([
      inspectDirectory(source),
      inspectDirectory(recovery),
    ]);
    if (sourceSnapshot.integrity !== "ok" || recoverySnapshot.integrity !== "ok") {
      throw new Error("Directory integrity_check did not return ok");
    }
    if (sourceSnapshot.schemaSha256 !== recoverySnapshot.schemaSha256) {
      throw new Error("Restored directory schema does not match the source schema");
    }
    for (const table of CORE_TABLES) {
      if (sourceSnapshot.counts[table] !== recoverySnapshot.counts[table]) {
        throw new Error(`Restored row count does not match for ${table}`);
      }
    }
    verified = true;
    console.log(
      JSON.stringify(
        {
          status: "verified",
          source_database: sourceName,
          recovery_database: recoveryName,
          restore_point: restorePoint.toISOString(),
          integrity_check: "ok",
          schema_sha256: recoverySnapshot.schemaSha256,
          core_table_row_counts: recoverySnapshot.counts,
          cleanup_after_success: !keep,
        },
        null,
        2,
      ),
    );
  } finally {
    source.close();
    recovery.close();
  }
} finally {
  if (created && verified && !keep) {
    runTurso(["db", "destroy", recoveryName, "--yes"]);
    console.log(
      JSON.stringify({
        status: "cleanup_complete",
        recovery_database: recoveryName,
      }),
    );
  } else if (created && !verified) {
    console.error(`Recovery database retained for investigation: ${recoveryName}`);
  }
}

async function inspectDirectory(client: Client): Promise<{
  integrity: string;
  schemaSha256: string;
  counts: Record<(typeof CORE_TABLES)[number], number>;
}> {
  const integrityResult = await client.execute("PRAGMA integrity_check");
  const integrity = String(integrityResult.rows[0]?.integrity_check ?? "");
  const schema = await client.execute(`
    SELECT type, name, tbl_name, sql
    FROM sqlite_schema
    WHERE name NOT LIKE 'sqlite_%'
    ORDER BY type, name
  `);
  const schemaSha256 = createHash("sha256")
    .update(
      JSON.stringify(
        schema.rows.map((row) => ({
          type: String(row.type ?? ""),
          name: String(row.name ?? ""),
          table: String(row.tbl_name ?? ""),
          sql: String(row.sql ?? ""),
        })),
      ),
    )
    .digest("hex");
  const counts = {} as Record<(typeof CORE_TABLES)[number], number>;
  for (const table of CORE_TABLES) {
    const result = await client.execute(`SELECT COUNT(*) AS count FROM "${table}"`);
    counts[table] = Number(result.rows[0]?.count ?? -1);
    if (!Number.isSafeInteger(counts[table]) || counts[table] < 0) {
      throw new Error(`Invalid row count returned for ${table}`);
    }
  }
  return { integrity, schemaSha256, counts };
}

function runTurso(args: string[]): string {
  const result = spawnSync("turso", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    const detail = redact(`${result.stdout}\n${result.stderr}`).trim().slice(0, 1_000);
    throw new Error(`turso ${args.slice(0, 3).join(" ")} failed: ${detail}`);
  }
  return `${result.stdout}\n${result.stderr}`;
}

function extractUrl(output: string): string {
  const match = output.match(/libsql:\/\/[a-z0-9.-]+\.turso\.io/i);
  if (!match) {
    throw new Error("Turso did not return the recovery database URL");
  }
  return normalizeTursoDatabaseUrl(match[0], "recovery database URL");
}

function extractJwt(output: string): string {
  const match = output.match(/\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/);
  if (!match) {
    throw new Error("Turso did not return a recovery database token");
  }
  return match[0];
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function validateDatabaseName(value: string, label: string): void {
  if (!/^[a-z][a-z0-9-]{2,62}$/.test(value)) {
    throw new Error(`${label} is invalid`);
  }
}

function compactTimestamp(value: Date): string {
  return value.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "z").toLowerCase();
}

function redact(value: string): string {
  return value.replace(
    /\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g,
    "[REDACTED_JWT]",
  );
}
