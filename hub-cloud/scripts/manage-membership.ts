import { createClient } from "@libsql/client";
import { createInterface } from "node:readline/promises";
import { parseArgs } from "node:util";

import { canonicalJson, normalizeTursoDatabaseUrl } from "../src/database";
import { normalizeEmail, normalizePublicTenantId } from "../src/tenant-id";
import type { Role } from "../src/types";

const ROLES = new Set<Role>(["reader", "operator", "admin"]);
const parsed = parseArgs({
  options: {
    tenant: { type: "string" },
    email: { type: "string" },
    role: { type: "string" },
    actor: { type: "string" },
    yes: { type: "boolean", short: "y", default: false },
  },
  allowPositionals: true,
  strict: true,
});
const action = parsed.positionals[0] ?? "";
const options = parsed.values;
const terminal = createInterface({ input: process.stdin, output: process.stdout });

try {
  if (!["list", "grant", "revoke", "reset-subject"].includes(action)) {
    throw new Error("action must be one of: list, grant, revoke, reset-subject");
  }
  const publicId = normalizePublicTenantId(requiredOption(options.tenant, "--tenant"));
  const directory = createClient({
    url: normalizeTursoDatabaseUrl(
      requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
      "DIRECTORY_TURSO_DATABASE_URL",
    ),
    authToken: requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN"),
  });
  try {
    const tenant = await directory.execute({
      sql: "SELECT id, display_name FROM tenants WHERE public_id = ? AND status = 'active' LIMIT 1",
      args: [publicId],
    });
    if (!tenant.rows[0]) {
      throw new Error("active tenant was not found");
    }
    const tenantId = String(tenant.rows[0].id);
    if (action === "list") {
      const memberships = await directory.execute({
        sql: `SELECT email, role, status, access_subject IS NOT NULL AS access_bound,
            created_at, updated_at
          FROM tenant_memberships
          WHERE tenant_id = ?
          ORDER BY lower(email)`,
        args: [tenantId],
      });
      console.log(
        JSON.stringify(
          {
            tenant: publicId,
            display_name: String(tenant.rows[0].display_name),
            memberships: memberships.rows.map((row) => ({
              email: String(row.email),
              role: String(row.role),
              status: String(row.status),
              access_identity_bound: Number(row.access_bound) === 1,
              created_at: String(row.created_at),
              updated_at: String(row.updated_at),
            })),
          },
          null,
          2,
        ),
      );
    } else {
      const email = normalizeEmail(requiredOption(options.email, "--email"));
      const actor = normalizeEmail(requiredOption(options.actor, "--actor"));
      const now = new Date().toISOString();
      if (action === "grant") {
        const role = requiredRole(options.role);
        await confirm("GRANT");
        await directory.batch(
          [
            {
              sql: `INSERT INTO tenant_memberships (
                  tenant_id, email, access_subject, role, status, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, 'active', ?, ?)
                ON CONFLICT(tenant_id, email) DO UPDATE SET
                  role = excluded.role,
                  status = 'active',
                  updated_at = excluded.updated_at`,
              args: [tenantId, email, role, now, now],
            },
            auditStatement({
              now,
              actor,
              tenantId,
              action: "membership.grant",
              email,
              payload: { role },
            }),
          ],
          "write",
        );
      } else if (action === "revoke") {
        await confirm("REVOKE");
        const result = await directory.batch(
          [
            {
              sql: `UPDATE tenant_memberships
                SET status = 'revoked', updated_at = ?
                WHERE tenant_id = ? AND email = ? AND status = 'active'`,
              args: [now, tenantId, email],
            },
            auditStatement({
              now,
              actor,
              tenantId,
              action: "membership.revoke",
              email,
              payload: {},
              onlyWhenChanged: true,
            }),
          ],
          "write",
        );
        if (Number(result[0]?.rowsAffected ?? 0) !== 1) {
          throw new Error("active membership was not found");
        }
      } else {
        await confirm("RESET");
        const result = await directory.batch(
          [
            {
              sql: `UPDATE tenant_memberships
                SET access_subject = NULL, updated_at = ?
                WHERE tenant_id = ? AND email = ? AND status = 'active'
                  AND access_subject IS NOT NULL`,
              args: [now, tenantId, email],
            },
            auditStatement({
              now,
              actor,
              tenantId,
              action: "membership.reset_access_subject",
              email,
              payload: {},
              onlyWhenChanged: true,
            }),
          ],
          "write",
        );
        if (Number(result[0]?.rowsAffected ?? 0) !== 1) {
          throw new Error("bound active membership was not found");
        }
      }
      console.log(
        JSON.stringify(
          {
            status: "updated",
            action,
            tenant: publicId,
            email,
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

function auditStatement(input: {
  now: string;
  actor: string;
  tenantId: string;
  action: string;
  email: string;
  payload: Record<string, unknown>;
  onlyWhenChanged?: boolean;
}) {
  return {
    sql: `INSERT INTO directory_audit_logs (
        occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
      ) SELECT ?, ?, ?, ?, 'tenant_membership', ?, ?
      ${input.onlyWhenChanged ? "WHERE changes() = 1" : ""}`,
    args: [
      input.now,
      input.actor,
      input.action,
      input.tenantId,
      input.email,
      canonicalJson(input.payload),
    ],
  };
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

function requiredRole(value: string | undefined): Role {
  const normalized = value?.trim().toLowerCase() ?? "";
  if (!ROLES.has(normalized as Role)) {
    throw new Error("--role must be reader, operator, or admin");
  }
  return normalized as Role;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}
