import { createClient } from "@libsql/client";
import { chmod, lstat, mkdir, unlink, writeFile } from "node:fs/promises";
import { createInterface } from "node:readline/promises";
import { dirname, isAbsolute, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { generateNodeCredential, nodeCredentialDigest } from "../src/crypto";
import { canonicalJson, normalizeTursoDatabaseUrl } from "../src/database";
import { normalizeEmail } from "../src/tenant-id";

const NODE_ID =
  /^INAEG-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const parsed = parseArgs({
  options: {
    node: { type: "string" },
    "credential-id": { type: "string" },
    output: { type: "string", short: "o" },
    actor: { type: "string" },
    "valid-days": { type: "string", default: "400" },
    yes: { type: "boolean", short: "y", default: false },
  },
  allowPositionals: true,
  strict: true,
});
const action = parsed.positionals[0] ?? "";
const options = parsed.values;
const terminal = createInterface({ input: process.stdin, output: process.stdout });

try {
  if (!["list", "rotate", "revoke"].includes(action)) {
    throw new Error("action must be one of: list, rotate, revoke");
  }
  const nodeId = requiredOption(options.node, "--node");
  if (!NODE_ID.test(nodeId)) {
    throw new Error("--node must be a canonical INAEG UUIDv4");
  }
  const directory = createClient({
    url: normalizeTursoDatabaseUrl(
      requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
      "DIRECTORY_TURSO_DATABASE_URL",
    ),
    authToken: requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN"),
  });
  try {
    const node = await directory.execute({
      sql: `SELECT n.node_id, n.tenant_id, n.label, t.public_id
        FROM edge_nodes n
        JOIN tenants t ON t.id = n.tenant_id
        WHERE n.node_id = ? AND n.status = 'active' AND t.status = 'active'
        LIMIT 1`,
      args: [nodeId],
    });
    if (!node.rows[0]) {
      throw new Error("active Edge Gateway was not found");
    }
    if (action === "list") {
      const credentials = await directory.execute({
        sql: `SELECT credential_id, status, created_at, expires_at, last_used_at
          FROM edge_node_credentials
          WHERE node_id = ?
          ORDER BY created_at DESC, credential_id`,
        args: [nodeId],
      });
      console.log(
        JSON.stringify(
          {
            node_id: nodeId,
            tenant: String(node.rows[0].public_id),
            credentials: credentials.rows.map((row) => ({
              credential_id: String(row.credential_id),
              status: String(row.status),
              created_at: String(row.created_at),
              expires_at: row.expires_at === null ? null : String(row.expires_at),
              last_used_at: row.last_used_at === null ? null : String(row.last_used_at),
            })),
          },
          null,
          2,
        ),
      );
    } else if (action === "rotate") {
      const actor = normalizeEmail(requiredOption(options.actor, "--actor"));
      const output = validateOutput(requiredOption(options.output, "--output"));
      await requireMissing(output);
      const validDays = boundedInteger(options["valid-days"], "--valid-days", 30, 730);
      const active = await directory.execute({
        sql: `SELECT COUNT(*) AS count
          FROM edge_node_credentials
          WHERE node_id = ? AND status = 'active'
            AND (expires_at IS NULL OR datetime(expires_at) > datetime(?))`,
        args: [nodeId, new Date().toISOString()],
      });
      if (Number(active.rows[0]?.count ?? 0) >= 2) {
        throw new Error("revoke an old credential before creating another one");
      }
      const credentialId = crypto.randomUUID();
      const credential = generateNodeCredential();
      const digest = await nodeCredentialDigest(credential.token, credential.salt);
      const now = new Date().toISOString();
      const expiresAt = new Date(
        Date.now() + validDays * 24 * 60 * 60 * 1000,
      ).toISOString();
      await confirm("ROTATE");
      await mkdir(dirname(output), { recursive: true, mode: 0o700 });
      await writeFile(output, `${credential.token}\n`, {
        encoding: "utf8",
        mode: 0o600,
        flag: "wx",
      });
      await chmod(output, 0o600);
      try {
        await directory.batch(
          [
            {
              sql: `INSERT INTO edge_node_credentials (
                  credential_id, node_id, status, credential_salt,
                  credential_digest, created_at, updated_at, expires_at
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?)`,
              args: [
                credentialId,
                nodeId,
                credential.salt,
                digest,
                now,
                now,
                expiresAt,
              ],
            },
            {
              sql: `INSERT INTO directory_audit_logs (
                  occurred_at, actor, action, tenant_id, resource_type,
                  resource_id, payload
                ) VALUES (?, ?, 'edge_credential.rotate', ?, 'edge_credential', ?, ?)`,
              args: [
                now,
                actor,
                String(node.rows[0].tenant_id),
                credentialId,
                canonicalJson({ node_id: nodeId, expires_at: expiresAt }),
              ],
            },
          ],
          "write",
        );
      } catch (error) {
        await unlink(output).catch(() => undefined);
        throw error;
      }
      console.log(
        JSON.stringify(
          {
            status: "credential-created",
            node_id: nodeId,
            credential_id: credentialId,
            expires_at: expiresAt,
            credential_file: output,
            next: [
              "Install the new mode-0600 token file on the labeled Gateway.",
              "Verify a successful Sync and last_used_at for this credential.",
              "Then revoke the previous credential explicitly.",
            ],
          },
          null,
          2,
        ),
      );
    } else {
      const actor = normalizeEmail(requiredOption(options.actor, "--actor"));
      const credentialId = requiredOption(options["credential-id"], "--credential-id");
      if (!UUID_V4.test(credentialId)) {
        throw new Error("--credential-id must be a canonical UUIDv4");
      }
      await confirm("REVOKE");
      const now = new Date().toISOString();
      const result = await directory.batch(
        [
          {
            sql: `UPDATE edge_node_credentials
              SET status = 'revoked', updated_at = ?
              WHERE credential_id = ? AND node_id = ? AND status = 'active'`,
            args: [now, credentialId, nodeId],
          },
          {
            sql: `INSERT INTO directory_audit_logs (
                occurred_at, actor, action, tenant_id, resource_type,
                resource_id, payload
              ) SELECT ?, ?, 'edge_credential.revoke', ?, 'edge_credential', ?, ?
              WHERE changes() = 1`,
            args: [
              now,
              actor,
              String(node.rows[0].tenant_id),
              credentialId,
              canonicalJson({ node_id: nodeId }),
            ],
          },
        ],
        "write",
      );
      if (Number(result[0]?.rowsAffected ?? 0) !== 1) {
        throw new Error("active credential was not found");
      }
      console.log(
        JSON.stringify(
          {
            status: "credential-revoked",
            node_id: nodeId,
            credential_id: credentialId,
          },
          null,
          2,
        ),
      );
    }
  } finally {
    directory.close();
  }
} finally {
  terminal.close();
}

async function confirm(word: string): Promise<void> {
  if (options.yes) {
    return;
  }
  if (!process.stdin.isTTY) {
    throw new Error("--yes is required when stdin is not interactive");
  }
  const answer = (await terminal.question(`${word} と入力してください: `)).trim();
  if (answer !== word) {
    throw new Error("operation was cancelled");
  }
}

function requiredOption(value: string | undefined, name: string): string {
  const normalized = value?.trim() ?? "";
  if (!normalized || normalized.length > 500) {
    throw new Error(`${name} is required and must be at most 500 characters`);
  }
  return normalized;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}

function boundedInteger(
  value: string | undefined,
  name: string,
  minimum: number,
  maximum: number,
): number {
  const parsedValue = Number(value);
  if (
    !Number.isSafeInteger(parsedValue) ||
    parsedValue < minimum ||
    parsedValue > maximum
  ) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`);
  }
  return parsedValue;
}

function validateOutput(value: string): string {
  if (!isAbsolute(value)) {
    throw new Error("--output must be an absolute path");
  }
  const output = resolve(value);
  const repository = resolve(fileURLToPath(new URL("../..", import.meta.url)));
  const home = process.env.HOME ? resolve(process.env.HOME) : "";
  if (output === parse(output).root || output === repository || (home && output === home)) {
    throw new Error("--output must not be a filesystem root, home, or repository root");
  }
  const fromRepository = relative(repository, output);
  if (fromRepository === "" || (!fromRepository.startsWith(`..${sep}`) && fromRepository !== "..")) {
    throw new Error("credential output must be outside the source repository");
  }
  return output;
}

async function requireMissing(path: string): Promise<void> {
  try {
    await lstat(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return;
    }
    throw error;
  }
  throw new Error(`output already exists: ${path}`);
}
