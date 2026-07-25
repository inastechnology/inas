import { createClient as createDatabaseClient } from "@libsql/client";
import {
  createClient as createPlatformClient,
  type CreatedDatabase,
  type Database,
} from "@tursodatabase/api";
import { parseArgs } from "node:util";
import { createInterface } from "node:readline/promises";

import { encryptTenantCredential } from "../src/crypto";
import { canonicalJson, normalizeTursoDatabaseUrl } from "../src/database";
import { generatePublicTenantId, normalizeEmail, normalizePublicTenantId } from "../src/tenant-id";
import { applyMigrations } from "./migrations";
import { isTursoHttpError } from "./turso-error";

const DATABASE_NAME = /^[a-z][a-z0-9-]{2,62}$/;
const options = parseArgs({
  options: {
    "display-name": { type: "string" },
    "admin-email": { type: "string" },
    "customer-reference": { type: "string" },
    "public-id": { type: "string" },
    "database-name": { type: "string" },
    "adopt-existing": { type: "boolean", default: false },
    yes: { type: "boolean", short: "y", default: false },
  },
  strict: true,
}).values;
const terminal = createInterface({ input: process.stdin, output: process.stdout });
let createdDatabase = false;
let databaseNameForRecovery = "";

try {
  const displayName = await requiredInput("顧客・組織名", options["display-name"]);
  const adminEmail = normalizeEmail(await requiredInput("初期管理者メール", options["admin-email"]));
  const customerReference = await optionalInput("顧客管理番号（任意）", options["customer-reference"]);
  const publicId = normalizePublicTenantId(
    await inputWithDefault("公開テナントID", options["public-id"], generatePublicTenantId()),
  );
  const databaseName = normalizeDatabaseName(
    await inputWithDefault("Turso DB名", options["database-name"], `inas-tenant-${publicId}`),
  );
  databaseNameForRecovery = databaseName;

  const directoryUrl = normalizeTursoDatabaseUrl(
    requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
    "DIRECTORY_TURSO_DATABASE_URL",
  );
  const directoryToken = requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN");
  const masterKey = requiredEnvironment("TENANT_CREDENTIAL_MASTER_KEY");
  const tursoOrg = requiredEnvironment("TURSO_ORG");
  const tursoToken = requiredEnvironment("TURSO_PLATFORM_TOKEN");
  const tursoGroup = process.env.TURSO_GROUP?.trim() || "default";
  const directory = createDatabaseClient({ url: directoryUrl, authToken: directoryToken });

  try {
    const existing = await directory.execute({
      sql: `SELECT id, public_id, display_name, turso_database_name
        FROM tenants
        WHERE public_id = ? OR turso_database_name = ?
        LIMIT 1`,
      args: [publicId, databaseName],
    });
    if (existing.rows[0]) {
      console.log(
        JSON.stringify(
          {
            status: "already-provisioned",
            tenant: {
              id: String(existing.rows[0].id),
              public_id: String(existing.rows[0].public_id),
              display_name: String(existing.rows[0].display_name),
              database_name: String(existing.rows[0].turso_database_name),
            },
          },
          null,
          2,
        ),
      );
      process.exitCode = 0;
    } else {
      await confirmProvision({
        displayName,
        adminEmail,
        customerReference,
        publicId,
        databaseName,
        tursoOrg,
        tursoGroup,
      });
      const platform = createPlatformClient({ org: tursoOrg, token: tursoToken });
      const databaseResolution = await resolveDatabase(platform, databaseName, tursoGroup, options["adopt-existing"]);
      createdDatabase = databaseResolution.created;
      const databaseUrl = normalizeTursoDatabaseUrl(
        `libsql://${databaseResolution.database.hostname}`,
        "provisioned tenant database URL",
      );
      const databaseToken = await platform.databases.createToken(databaseName, {
        authorization: "full-access",
      });
      const tenantDatabase = createDatabaseClient({
        url: databaseUrl,
        authToken: databaseToken.jwt,
      });
      try {
        await applyMigrations(tenantDatabase, new URL("../migrations/tenant/", import.meta.url));
      } finally {
        tenantDatabase.close();
      }

      const tenantId = crypto.randomUUID();
      const encryptedToken = await encryptTenantCredential(
        masterKey,
        {
          tenantId,
          databaseName,
          databaseUrl,
        },
        databaseToken.jwt,
      );
      const now = new Date().toISOString();
      await directory.batch(
        [
          {
            sql: `INSERT INTO tenants (
                id, public_id, display_name, customer_reference, status,
                turso_database_name, turso_database_url,
                turso_auth_token_ciphertext, credential_key_version,
                created_at, updated_at
              ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, 2, ?, ?)`,
            args: [
              tenantId,
              publicId,
              displayName,
              customerReference || null,
              databaseName,
              databaseUrl,
              encryptedToken,
              now,
              now,
            ],
          },
          {
            sql: `INSERT INTO tenant_memberships (
                tenant_id, email, role, status, created_at, updated_at
              ) VALUES (?, ?, 'admin', 'active', ?, ?)`,
            args: [tenantId, adminEmail, now, now],
          },
          {
            sql: `INSERT INTO directory_audit_logs (
                occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
              ) VALUES (?, ?, 'tenant.provision', ?, 'tenant', ?, ?)`,
            args: [
              now,
              adminEmail,
              tenantId,
              tenantId,
              canonicalJson({
                public_id: publicId,
                database_name: databaseName,
                database_created: createdDatabase,
              }),
            ],
          },
        ],
        "write",
      );
      console.log(
        JSON.stringify(
          {
            status: "provisioned",
            tenant: {
              id: tenantId,
              public_id: publicId,
              display_name: displayName,
              admin_email: adminEmail,
              database_name: databaseName,
              cloud_hub_url: `${publicOrigin()}/t/${publicId}/`,
            },
          },
          null,
          2,
        ),
      );
    }
  } finally {
    directory.close();
  }
} catch (error) {
  if (createdDatabase) {
    console.error(
      `Provisioning stopped after Turso DB ${databaseNameForRecovery} was created. ` +
        "The script intentionally did not delete it; rerun with --adopt-existing after checking the database.",
    );
  }
  throw error;
} finally {
  terminal.close();
}

async function resolveDatabase(
  platform: ReturnType<typeof createPlatformClient>,
  databaseName: string,
  group: string,
  adoptExisting: boolean,
): Promise<{ database: CreatedDatabase | Database; created: boolean }> {
  try {
    const database = await platform.databases.get(databaseName);
    if (!adoptExisting) {
      throw new Error(
        `Turso DB ${databaseName} already exists but is not registered. ` +
          "Inspect it, then pass --adopt-existing to issue a new scoped token and adopt it.",
      );
    }
    return { database, created: false };
  } catch (error) {
    if (!isTursoHttpError(error, 404)) {
      throw error;
    }
  }
  return {
    database: await platform.databases.create(databaseName, { group }),
    created: true,
  };
}

async function confirmProvision(summary: Record<string, string>): Promise<void> {
  console.log(JSON.stringify({ action: "provision-tenant", ...summary }, null, 2));
  if (options.yes) {
    return;
  }
  if (!process.stdin.isTTY) {
    throw new Error("--yes is required when stdin is not interactive");
  }
  const answer = (await terminal.question("作成する場合は PROVISION と入力してください: ")).trim();
  if (answer !== "PROVISION") {
    throw new Error("provisioning was cancelled");
  }
}

async function requiredInput(label: string, supplied: string | undefined): Promise<string> {
  const value = supplied?.trim() || (process.stdin.isTTY ? (await terminal.question(`${label}: `)).trim() : "");
  if (!value || value.length > 200) {
    throw new Error(`${label} is required and must be at most 200 characters`);
  }
  return value;
}

async function optionalInput(label: string, supplied: string | undefined): Promise<string> {
  const value = supplied !== undefined ? supplied.trim() : process.stdin.isTTY ? (await terminal.question(`${label}: `)).trim() : "";
  if (value.length > 200) {
    throw new Error(`${label} must be at most 200 characters`);
  }
  return value;
}

async function inputWithDefault(label: string, supplied: string | undefined, fallback: string): Promise<string> {
  if (supplied?.trim()) {
    return supplied.trim();
  }
  if (!process.stdin.isTTY) {
    return fallback;
  }
  return (await terminal.question(`${label} [${fallback}]: `)).trim() || fallback;
}

function normalizeDatabaseName(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!DATABASE_NAME.test(normalized)) {
    throw new Error("database name must be 3-63 lowercase letters, numbers, or hyphens and start with a letter");
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

function publicOrigin(): string {
  return (
    process.env.CLOUD_HUB_PUBLIC_ORIGIN?.trim() ||
    "https://cloud-hub.inas-technologies.com"
  ).replace(/\/+$/, "");
}
