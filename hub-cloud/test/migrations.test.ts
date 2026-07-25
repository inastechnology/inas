import { describe, expect, it } from "vitest";
import { createClient } from "@libsql/client";

import { applyMigrations, splitSqlStatements } from "../scripts/migrations";

describe("migration parser", () => {
  it("does not split semicolons inside strings or comments", () => {
    expect(
      splitSqlStatements(`
        -- ignored ; comment
        CREATE TABLE sample (value TEXT);
        INSERT INTO sample VALUES ('a;''b');
        /* ignored ; block */
      `),
    ).toEqual(["CREATE TABLE sample (value TEXT)", "INSERT INTO sample VALUES ('a;''b')"]);
  });

  it("keeps trigger bodies together", () => {
    expect(
      splitSqlStatements(`
        CREATE TRIGGER sample_trigger
        BEFORE DELETE ON sample
        BEGIN
          SELECT RAISE(ABORT, 'blocked');
        END;
        CREATE INDEX sample_index ON sample(value);
      `),
    ).toEqual([
      `CREATE TRIGGER sample_trigger
        BEFORE DELETE ON sample
        BEGIN
          SELECT RAISE(ABORT, 'blocked');
        END`,
      "CREATE INDEX sample_index ON sample(value)",
    ]);
  });

  it("uses the tenant database itself as the isolation boundary", async () => {
    const client = createClient({ url: "file::memory:" });
    try {
      await applyMigrations(client, new URL("../migrations/tenant/", import.meta.url));
      const tables = [
        "device_events",
        "command_results",
        "node_health",
        "desired_resources",
        "commands",
        "audit_logs",
      ];
      for (const table of tables) {
        const columns = await client.execute(`PRAGMA table_info(${table})`);
        expect(columns.rows.map((row) => String(row.name))).not.toContain("tenant_id");
      }
    } finally {
      client.close();
    }
  });
});
