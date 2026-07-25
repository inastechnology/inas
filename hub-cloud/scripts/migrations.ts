import { readFile, readdir } from "node:fs/promises";
import type { Client } from "@libsql/client";

export async function applyMigrations(client: Client, directory: URL): Promise<string[]> {
  await client.execute(`CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
  )`);
  const entries = (await readdir(directory, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".sql"))
    .map((entry) => entry.name)
    .sort();
  const applied: string[] = [];
  for (const name of entries) {
    const present = await client.execute({
      sql: "SELECT 1 FROM schema_migrations WHERE name = ? LIMIT 1",
      args: [name],
    });
    if (present.rows.length > 0) {
      continue;
    }
    const sql = await readFile(new URL(name, ensureDirectoryUrl(directory)), "utf8");
    const statements = splitSqlStatements(sql).map((statement) => ({ sql: statement }));
    if (statements.length === 0) {
      throw new Error(`migration is empty: ${name}`);
    }
    await client.batch(
      [
        ...statements,
        {
          sql: "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
          args: [name, new Date().toISOString()],
        },
      ],
      "write",
    );
    applied.push(name);
  }
  return applied;
}

export function splitSqlStatements(sql: string): string[] {
  const statements: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;
  let lineComment = false;
  let blockComment = false;
  for (let index = 0; index < sql.length; index += 1) {
    const character = sql[index];
    const next = sql[index + 1] ?? "";
    if (lineComment) {
      if (character === "\n") {
        lineComment = false;
        current += character;
      }
      continue;
    }
    if (blockComment) {
      if (character === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (!quote && character === "-" && next === "-") {
      lineComment = true;
      index += 1;
      continue;
    }
    if (!quote && character === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (quote) {
      current += character;
      if (character === quote) {
        if (next === quote) {
          current += next;
          index += 1;
        } else {
          quote = null;
        }
      }
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      current += character;
      continue;
    }
    if (character === ";") {
      const statement = current.trim();
      if (
        /^CREATE\s+(?:TEMP(?:ORARY)?\s+)?TRIGGER\b/i.test(statement) &&
        !/\bEND\s*$/i.test(statement)
      ) {
        current += character;
        continue;
      }
      if (statement) {
        statements.push(statement);
      }
      current = "";
      continue;
    }
    current += character;
  }
  if (quote || blockComment) {
    throw new Error("migration contains an unterminated quoted string or comment");
  }
  const remainder = current.trim();
  if (remainder) {
    statements.push(remainder);
  }
  return statements;
}

function ensureDirectoryUrl(directory: URL): URL {
  return directory.href.endsWith("/") ? directory : new URL(`${directory.href}/`);
}
