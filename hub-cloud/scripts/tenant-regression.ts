import { createClient as createDatabaseClient, type Client } from "@libsql/client";
import {
  createClient as createPlatformClient,
  type CreatedDatabase,
  type Database,
} from "@tursodatabase/api";
import { spawnSync } from "node:child_process";
import {
  chmod,
  lstat,
  mkdir,
  readFile,
  readdir,
  unlink,
  writeFile,
} from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { createApp } from "../src";
import {
  decryptTenantCredential,
  encryptTenantCredential,
  generateNodeCredential,
  nodeCredentialDigest,
  sha256Hex,
} from "../src/crypto";
import { canonicalJson, normalizeTursoDatabaseUrl } from "../src/database";
import { DirectoryRepository } from "../src/repositories/directory";
import { createCloudRuntime } from "../src/runtime";
import { normalizeEmail } from "../src/tenant-id";
import type {
  AccessIdentity,
  Env,
  SyncRequest,
  SyncResponse,
} from "../src/types";
import { applyMigrations } from "./migrations";
import {
  assertRegressionManifest,
  createRegressionRunId,
  ephemeralRegressionNames,
  PERSISTENT_CUSTOMER_REFERENCE,
  PERSISTENT_DATABASE_NAME,
  PERSISTENT_PUBLIC_ID,
  REGRESSION_MANIFEST_VERSION,
  type RegressionManifest,
} from "./regression-guards";
import { isTursoHttpError } from "./turso-error";

const PERSISTENT_DISPLAY_NAME = "INAS 回帰試験（常設）";
const EPHEMERAL_DISPLAY_NAME_PREFIX = "INAS 回帰試験（一時）";
const DEFAULT_PUBLIC_ORIGIN = "https://cloud-hub.inas-technologies.com";
const DEFAULT_TURSO_GROUP = "ina-technologies";
const REPOSITORY_ROOT = resolve(fileURLToPath(new URL("../../", import.meta.url)));
const DATABASE_NAME = /^[a-z][a-z0-9-]{2,62}$/;
const NODE_ID = /^INAEG-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

type Platform = ReturnType<typeof createPlatformClient>;

interface CommandLine {
  action: "ensure" | "run" | "cleanup" | "status";
  apply: boolean;
  manifestPath?: string;
  stateDirectory: string;
}

interface RegressionContext {
  directory: Client;
  platform: Platform;
  masterKey: string;
  publicOrigin: string;
  tursoGroup: string;
  adminEmail?: string;
}

interface DirectoryTenant {
  id: string;
  publicId: string;
  displayName: string;
  customerReference: string | null;
  status: "active" | "suspended" | "deprovisioning";
  databaseName: string;
  databaseUrl: string;
  encryptedAuthToken: string;
  credentialKeyVersion: number;
}

interface RegisteredNode {
  nodeId: string;
  token: string;
  label: string;
}

interface TenantFixtures {
  side: "persistent" | "ephemeral";
  eventId: string;
  commandId: string;
  resourceId: string;
  resultId: string;
  request: SyncRequest;
}

interface RegressionResult {
  run_id: string;
  persistent_tenant: string;
  ephemeral_tenant: string;
  checks: string[];
  other_tenant_snapshot_unchanged: boolean;
  cleanup: "complete";
}

const commandLine = parseCommandLine();

try {
  await main(commandLine);
} catch (error) {
  console.error(
    JSON.stringify(
      {
        status: "failed",
        action: commandLine.action,
        error: safeError(error),
        manifest: commandLine.manifestPath ?? null,
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
}

async function main(command: CommandLine): Promise<void> {
  if (command.action === "status") {
    await reportStatus(command.stateDirectory);
    return;
  }
  if (!command.apply) {
    if (command.action === "cleanup") {
      if (!command.manifestPath) {
        throw new Error("cleanup requires --manifest <absolute-path>");
      }
      const manifest = await readManifest(command.manifestPath);
      console.log(
        JSON.stringify(
          {
            status: "planned",
            action: "cleanup",
            run_id: manifest.run_id,
            ephemeral_tenant: manifest.tenant.public_id,
            ephemeral_database: manifest.tenant.database_name,
            requires: "--apply",
          },
          null,
          2,
        ),
      );
      return;
    }
    console.log(
      JSON.stringify(
        {
          status: "planned",
          action: command.action,
          persistent_tenant: PERSISTENT_PUBLIC_ID,
          persistent_database: PERSISTENT_DATABASE_NAME,
          ephemeral_lifecycle:
            command.action === "run" ? "create, test, deprovision, delete" : null,
          state_directory: command.stateDirectory,
          requires: "--apply",
        },
        null,
        2,
      ),
    );
    return;
  }

  const context = await createContext(command.action !== "cleanup");
  try {
    await applyMigrations(
      context.directory,
      new URL("../migrations/directory/", import.meta.url),
    );
    if (command.action === "ensure") {
      const persistent = await ensurePersistentTenant(context);
      console.log(
        JSON.stringify(
          {
            status: "ready",
            persistent_tenant: persistent.publicId,
            database: persistent.databaseName,
            delete_protection: true,
            cloud_hub_url: `${context.publicOrigin}/t/${persistent.publicId}/`,
          },
          null,
          2,
        ),
      );
      return;
    }
    if (command.action === "cleanup") {
      if (!command.manifestPath) {
        throw new Error("cleanup requires --manifest <absolute-path>");
      }
      const manifest = await readManifest(command.manifestPath);
      await cleanupRegressionRun(context, manifest, command.manifestPath);
      console.log(
        JSON.stringify(
          {
            status: "cleanup_complete",
            run_id: manifest.run_id,
            ephemeral_tenant: manifest.tenant.public_id,
          },
          null,
          2,
        ),
      );
      return;
    }
    await runRegression(context, command.stateDirectory);
  } finally {
    context.directory.close();
  }
}

function parseCommandLine(): CommandLine {
  const parsed = parseArgs({
    allowPositionals: true,
    strict: true,
    options: {
      apply: { type: "boolean", default: false },
      manifest: { type: "string" },
      "state-dir": { type: "string" },
    },
  });
  const action = parsed.positionals[0] ?? "status";
  if (
    parsed.positionals.length > 1 ||
    !["ensure", "run", "cleanup", "status"].includes(action)
  ) {
    throw new Error(
      "usage: tenant-regression.ts <ensure|run|cleanup|status> [--apply] [--manifest <absolute-path>] [--state-dir <absolute-path>]",
    );
  }
  const stateDirectory = secureExternalPath(
    parsed.values["state-dir"]?.trim() || defaultStateDirectory(),
    "regression state directory",
  );
  const manifestPath = parsed.values.manifest
    ? secureExternalPath(parsed.values.manifest.trim(), "regression manifest")
    : undefined;
  return {
    action: action as CommandLine["action"],
    apply: parsed.values.apply,
    manifestPath,
    stateDirectory,
  };
}

async function createContext(requireAdminEmail: boolean): Promise<RegressionContext> {
  const directoryUrl = normalizeTursoDatabaseUrl(
    requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
    "DIRECTORY_TURSO_DATABASE_URL",
  );
  const directoryToken = requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN");
  const masterKey = requiredEnvironment("TENANT_CREDENTIAL_MASTER_KEY");
  const tursoOrg =
    process.env.TURSO_ORG?.trim() || normalizeTursoSlug(tursoWhoAmI(), "Turso organization");
  const tursoGroup = normalizeTursoSlug(
    process.env.TURSO_GROUP?.trim() || DEFAULT_TURSO_GROUP,
    "Turso group",
  );
  const platformToken =
    process.env.TURSO_PLATFORM_TOKEN?.trim() || extractJwt(runTurso(["auth", "token"]));
  const publicOrigin = exactPublicOrigin(
    process.env.CLOUD_HUB_PUBLIC_ORIGIN?.trim() || DEFAULT_PUBLIC_ORIGIN,
  );
  return {
    directory: createDatabaseClient({ url: directoryUrl, authToken: directoryToken }),
    platform: createPlatformClient({ org: tursoOrg, token: platformToken }),
    masterKey,
    publicOrigin,
    tursoGroup,
    adminEmail: requireAdminEmail ? regressionAdminEmail() : undefined,
  };
}

async function reportStatus(stateDirectory: string): Promise<void> {
  const url = normalizeTursoDatabaseUrl(
    requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
    "DIRECTORY_TURSO_DATABASE_URL",
  );
  const client = createDatabaseClient({
    url,
    authToken: requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN"),
  });
  try {
    const tenants = await client.execute({
      sql: `SELECT public_id, status, turso_database_name
        FROM tenants
        WHERE customer_reference LIKE 'regression:%'
        ORDER BY public_id`,
      args: [],
    });
    const manifests = await listManifestNames(stateDirectory);
    console.log(
      JSON.stringify(
        {
          status: "inspected",
          regression_tenants: tenants.rows.map((row) => ({
            public_id: String(row.public_id),
            status: String(row.status),
            database_name: String(row.turso_database_name),
          })),
          pending_cleanup_manifests: manifests,
        },
        null,
        2,
      ),
    );
  } finally {
    client.close();
  }
}

async function runRegression(
  context: RegressionContext,
  stateDirectory: string,
): Promise<void> {
  const persistent = await ensurePersistentTenant(context);
  await assertNoPendingEphemeralState(context.directory, stateDirectory);
  const before = await otherTenantSnapshot(context.directory);
  const runId = createRegressionRunId();
  const names = ephemeralRegressionNames(runId);
  const manifestPath = resolve(stateDirectory, `${runId}.json`);
  const manifest: RegressionManifest = {
    version: REGRESSION_MANIFEST_VERSION,
    run_id: runId,
    created_at: new Date().toISOString(),
    tenant: {
      id: crypto.randomUUID(),
      public_id: names.publicId,
      database_name: names.databaseName,
      customer_reference: names.customerReference,
    },
  };
  await writeManifest(manifestPath, manifest);
  let result: RegressionResult | undefined;
  let testFailure: unknown;
  let cleanupFailure: unknown;
  try {
    const ephemeral = await provisionExactTenant(context, {
      tenantId: manifest.tenant.id,
      publicId: manifest.tenant.public_id,
      displayName: `${EPHEMERAL_DISPLAY_NAME_PREFIX} ${runId}`,
      customerReference: manifest.tenant.customer_reference,
      databaseName: manifest.tenant.database_name,
      adminEmail: `regression-${runId.slice(-8)}@regression.invalid`,
      tokenExpiration: "1d",
    });
    result = await exerciseIsolation(context, runId, persistent, ephemeral);
  } catch (error) {
    testFailure = error;
  } finally {
    try {
      await cleanupRegressionRun(context, manifest, manifestPath);
    } catch (error) {
      cleanupFailure = error;
    }
  }

  const after = await otherTenantSnapshot(context.directory);
  const otherTenantSnapshotUnchanged = before === after;
  if (!otherTenantSnapshotUnchanged && !testFailure) {
    testFailure = new Error(
      "non-regression tenant directory state changed during the isolated regression run",
    );
  }
  if (cleanupFailure) {
    throw new Error(
      `regression cleanup is incomplete; rerun cleanup with manifest ${manifestPath}: ${safeError(cleanupFailure)}`,
      { cause: cleanupFailure },
    );
  }
  if (testFailure) {
    throw new Error(`regression checks failed after successful cleanup: ${safeError(testFailure)}`, {
      cause: testFailure,
    });
  }
  if (!result) {
    throw new Error("regression run did not produce a result");
  }
  result.other_tenant_snapshot_unchanged = otherTenantSnapshotUnchanged;
  console.log(JSON.stringify({ status: "passed", ...result }, null, 2));
}

async function ensurePersistentTenant(
  context: RegressionContext,
): Promise<DirectoryTenant> {
  if (!context.adminEmail) {
    throw new Error("regression administrator email is not configured");
  }
  const matches = await findTenantMatches(
    context.directory,
    PERSISTENT_PUBLIC_ID,
    PERSISTENT_DATABASE_NAME,
    PERSISTENT_CUSTOMER_REFERENCE,
  );
  let tenant: DirectoryTenant;
  if (matches.length === 0) {
    tenant = await provisionExactTenant(context, {
      tenantId: crypto.randomUUID(),
      publicId: PERSISTENT_PUBLIC_ID,
      displayName: PERSISTENT_DISPLAY_NAME,
      customerReference: PERSISTENT_CUSTOMER_REFERENCE,
      databaseName: PERSISTENT_DATABASE_NAME,
      adminEmail: context.adminEmail,
    });
  } else {
    if (matches.length !== 1) {
      throw new Error("persistent regression tenant identifiers resolve to multiple rows");
    }
    tenant = directoryTenant(matches[0]);
    assertExactTenant(tenant, {
      publicId: PERSISTENT_PUBLIC_ID,
      displayName: PERSISTENT_DISPLAY_NAME,
      customerReference: PERSISTENT_CUSTOMER_REFERENCE,
      databaseName: PERSISTENT_DATABASE_NAME,
      status: "active",
    });
    await assertExactAdminMembership(context.directory, tenant.id, context.adminEmail);
    const database = await context.platform.databases.get(PERSISTENT_DATABASE_NAME);
    assertPlatformDatabase(database, PERSISTENT_DATABASE_NAME);
    const tenantDatabase = await openTenantDatabase(context, tenant);
    try {
      await applyMigrations(
        tenantDatabase,
        new URL("../migrations/tenant/", import.meta.url),
      );
    } finally {
      tenantDatabase.close();
    }
  }
  ensureDeleteProtection(PERSISTENT_DATABASE_NAME);
  return tenant;
}

async function provisionExactTenant(
  context: RegressionContext,
  input: {
    tenantId: string;
    publicId: string;
    displayName: string;
    customerReference: string;
    databaseName: string;
    adminEmail: string;
    tokenExpiration?: string;
  },
): Promise<DirectoryTenant> {
  if (!DATABASE_NAME.test(input.databaseName)) {
    throw new Error("regression database name is invalid");
  }
  const existing = await findTenantMatches(
    context.directory,
    input.publicId,
    input.databaseName,
    input.customerReference,
  );
  if (existing.length > 0) {
    throw new Error(`regression tenant already exists: ${input.publicId}`);
  }
  try {
    await context.platform.databases.get(input.databaseName);
    throw new Error(
      `Turso database exists without an exact directory row: ${input.databaseName}`,
    );
  } catch (error) {
    if (!isTursoHttpError(error, 404)) {
      throw error;
    }
  }

  const database = await context.platform.databases.create(input.databaseName, {
    group: context.tursoGroup,
  });
  assertPlatformDatabase(database, input.databaseName);
  const databaseUrl = normalizeTursoDatabaseUrl(
    `libsql://${database.hostname}`,
    "regression tenant database URL",
  );
  const token = await context.platform.databases.createToken(input.databaseName, {
    authorization: "full-access",
    ...(input.tokenExpiration ? { expiration: input.tokenExpiration } : {}),
  });
  const tenantDatabase = createDatabaseClient({
    url: databaseUrl,
    authToken: token.jwt,
  });
  try {
    await applyMigrations(
      tenantDatabase,
      new URL("../migrations/tenant/", import.meta.url),
    );
  } finally {
    tenantDatabase.close();
  }
  const encryptedToken = await encryptTenantCredential(
    context.masterKey,
    {
      tenantId: input.tenantId,
      databaseName: input.databaseName,
      databaseUrl,
    },
    token.jwt,
  );
  const now = new Date().toISOString();
  await context.directory.batch(
    [
      {
        sql: `INSERT INTO tenants (
            id, public_id, display_name, customer_reference, status,
            turso_database_name, turso_database_url,
            turso_auth_token_ciphertext, credential_key_version,
            created_at, updated_at
          ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, 2, ?, ?)`,
        args: [
          input.tenantId,
          input.publicId,
          input.displayName,
          input.customerReference,
          input.databaseName,
          databaseUrl,
          encryptedToken,
          now,
          now,
        ],
      },
      {
        sql: `INSERT INTO tenant_memberships (
            tenant_id, email, access_subject, role, status, created_at, updated_at
          ) VALUES (?, ?, NULL, 'admin', 'active', ?, ?)`,
        args: [input.tenantId, normalizeEmail(input.adminEmail), now, now],
      },
      {
        sql: `INSERT INTO directory_audit_logs (
            occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
          ) VALUES (?, 'tenant-regression', 'tenant.regression_provision', ?,
              'tenant', ?, ?)`,
        args: [
          now,
          input.tenantId,
          input.tenantId,
          canonicalJson({
            public_id: input.publicId,
            database_name: input.databaseName,
            customer_reference: input.customerReference,
          }),
        ],
      },
    ],
    "write",
  );
  return {
    id: input.tenantId,
    publicId: input.publicId,
    displayName: input.displayName,
    customerReference: input.customerReference,
    status: "active",
    databaseName: input.databaseName,
    databaseUrl,
    encryptedAuthToken: encryptedToken,
    credentialKeyVersion: 2,
  };
}

async function exerciseIsolation(
  context: RegressionContext,
  runId: string,
  persistent: DirectoryTenant,
  ephemeral: DirectoryTenant,
): Promise<RegressionResult> {
  const persistentDatabase = await openTenantDatabase(context, persistent);
  const ephemeralDatabase = await openTenantDatabase(context, ephemeral);
  const persistentNode = await registerRegressionNode(
    context.directory,
    persistent.id,
    `regression:${runId}:persistent`,
  );
  const ephemeralNode = await registerRegressionNode(
    context.directory,
    ephemeral.id,
    `regression:${runId}:ephemeral`,
  );
  try {
    const persistentFixtures = await stageTenantFixtures(
      persistentDatabase,
      runId,
      persistentNode,
      "persistent",
    );
    const ephemeralFixtures = await stageTenantFixtures(
      ephemeralDatabase,
      runId,
      ephemeralNode,
      "ephemeral",
    );
    const checks: string[] = [];
    const syncApp = regressionApp(context, {
      email: "sync-regression@regression.invalid",
      subject: `sync-${runId}`,
    });

    await expectStatus(
      syncExchange(
        syncApp,
        context,
        ephemeralNode.nodeId,
        persistentNode.token,
        ephemeralFixtures.request,
      ),
      401,
      "persistent node token cannot authenticate as ephemeral node",
    );
    checks.push("node token persistent -> ephemeral denied (401)");
    await expectStatus(
      syncExchange(
        syncApp,
        context,
        persistentNode.nodeId,
        ephemeralNode.token,
        persistentFixtures.request,
      ),
      401,
      "ephemeral node token cannot authenticate as persistent node",
    );
    checks.push("node token ephemeral -> persistent denied (401)");

    await expectStatus(
      syncExchange(
        syncApp,
        context,
        persistentNode.nodeId,
        persistentNode.token,
        {
          ...persistentFixtures.request,
          node_id: ephemeralNode.nodeId,
        },
      ),
      400,
      "path and body node mismatch must be rejected",
    );
    checks.push("sync path/body identity mismatch denied (400)");
    await expectStatus(
      rawSyncExchange(
        syncApp,
        context,
        persistentNode.nodeId,
        persistentNode.token,
        { ...persistentFixtures.request, tenant_id: ephemeral.publicId },
      ),
      400,
      "caller-selected tenant routing must be rejected",
    );
    checks.push("sync tenant override denied (400)");

    await exerciseSyncTenant(
      syncApp,
      context,
      persistentNode,
      persistentFixtures,
      "persistent",
    );
    await exerciseSyncTenant(
      syncApp,
      context,
      ephemeralNode,
      ephemeralFixtures,
      "ephemeral",
    );
    checks.push("sync success, exact retry, conflict, desired state and command completion");
    await exerciseDeployedOrigin(
      context,
      persistentNode,
      persistentFixtures,
      ephemeralNode,
      ephemeralFixtures,
    );
    checks.push("deployed origin health and both tenant sync routes");

    await assertDatabaseIsolation(
      persistentDatabase,
      runId,
      "persistent",
      ephemeralFixtures.eventId,
      persistentFixtures,
    );
    await assertDatabaseIsolation(
      ephemeralDatabase,
      runId,
      "ephemeral",
      persistentFixtures.eventId,
      ephemeralFixtures,
    );
    checks.push("tenant databases contain own marker and exclude peer marker");
    await assertDatabaseCredentialIsolation(context, persistent, ephemeral);
    checks.push("tenant database credentials cannot open the peer database");

    await exerciseBrowserBoundary(
      context,
      runId,
      persistent,
      ephemeral,
      persistentNode,
      ephemeralNode,
    );
    checks.push("Access membership isolation in both directions (404)");
    checks.push("ephemeral management API, events, dashboard and node listing");

    return {
      run_id: runId,
      persistent_tenant: persistent.publicId,
      ephemeral_tenant: ephemeral.publicId,
      checks,
      other_tenant_snapshot_unchanged: false,
      cleanup: "complete",
    };
  } finally {
    persistentDatabase.close();
    ephemeralDatabase.close();
  }
}

async function exerciseDeployedOrigin(
  context: RegressionContext,
  persistentNode: RegisteredNode,
  persistentFixtures: TenantFixtures,
  ephemeralNode: RegisteredNode,
  ephemeralFixtures: TenantFixtures,
): Promise<void> {
  const health = await expectJson<{ status: string; service: string }>(
    await fetch(`${context.publicOrigin}/healthz`, {
      headers: { Accept: "application/json" },
      redirect: "error",
    }),
    200,
    "deployed Cloud Hub health",
  );
  assert(
    health.status === "ok" && health.service === "inas-hub-cloud",
    "deployed Cloud Hub health response is unexpected",
  );
  for (const [node, fixtures] of [
    [persistentNode, persistentFixtures],
    [ephemeralNode, ephemeralFixtures],
  ] as const) {
    const response = await expectJson<SyncResponse>(
      await fetch(
        `${context.publicOrigin}/sync/v1/nodes/${node.nodeId}/exchange`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${node.token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ...fixtures.request,
            request_id: crypto.randomUUID(),
            sent_at: new Date().toISOString(),
          }),
          redirect: "error",
        },
      ),
      200,
      `deployed ${fixtures.side} sync`,
    );
    assert(
      response.ack_event_ids.includes(fixtures.eventId),
      `deployed ${fixtures.side} sync did not acknowledge its own marker`,
    );
    assert(
      response.desired_resources.some(
        (resource) =>
          resource.resource_id === fixtures.resourceId &&
          resource.target_node_id === node.nodeId,
      ),
      `deployed ${fixtures.side} sync did not return its own desired resource`,
    );
  }
}

async function stageTenantFixtures(
  database: Client,
  runId: string,
  node: RegisteredNode,
  side: TenantFixtures["side"],
): Promise<TenantFixtures> {
  const now = new Date().toISOString();
  const commandId = crypto.randomUUID();
  const resourceId = `regression-${runId}-${side}`;
  const payload = { run_id: runId, side };
  const resourceContentSha = await sha256Hex(canonicalJson(payload));
  await database.batch(
    [
      {
        sql: `INSERT INTO desired_resources (
            resource_type, resource_id, target_node_id, revision, operation,
            content_sha256, updated_at, payload
          ) VALUES ('node.policy', ?, ?, 1, 'upsert', ?, ?, ?)`,
        args: [
          resourceId,
          node.nodeId,
          resourceContentSha,
          now,
          JSON.stringify(payload),
        ],
      },
      {
        sql: `INSERT INTO commands (
            command_id, idempotency_key, command_type, target_node_id,
            device_id, issued_at, expires_at, payload, status, created_at
          ) VALUES (?, ?, 'regression.echo', ?, NULL, ?, ?, ?, 'pending', ?)`,
        args: [
          commandId,
          `regression:${runId}:${side}`,
          node.nodeId,
          now,
          new Date(Date.now() + 60 * 60 * 1000).toISOString(),
          JSON.stringify(payload),
          now,
        ],
      },
    ],
    "write",
  );
  const eventId = crypto.randomUUID();
  return {
    side,
    eventId,
    commandId,
    resourceId,
    resultId: crypto.randomUUID(),
    request: {
      protocol_version: "1.0",
      request_id: crypto.randomUUID(),
      node_id: node.nodeId,
      node_type: "edge_gateway",
      sent_at: now,
      cursor: null,
      events: [
        {
          event_id: eventId,
          origin_node_id: node.nodeId,
          sequence: 1,
          schema_version: 1,
          event_type: "regression.marker",
          occurred_at: now,
          payload,
        },
      ],
      command_results: [],
      health: {
        status: "ok",
        software_version: "regression-1",
        outbox_depth: 1,
        mqtt_connected: true,
        storage_total_bytes: 1_000_000,
        storage_free_bytes: 500_000,
        capabilities: ["regression"],
        details: payload,
      },
    },
  };
}

async function exerciseSyncTenant(
  app: ReturnType<typeof createApp>,
  context: RegressionContext,
  node: RegisteredNode,
  fixtures: TenantFixtures,
  label: string,
): Promise<void> {
  const first = await expectJson<SyncResponse>(
    await syncExchange(app, context, node.nodeId, node.token, fixtures.request),
    200,
    `${label} first sync`,
  );
  assert(
    first.ack_event_ids.includes(fixtures.eventId),
    `${label} event was not acknowledged`,
  );
  assert(
    first.desired_resources.some(
      (resource) =>
        resource.resource_id === fixtures.resourceId &&
        resource.target_node_id === node.nodeId,
    ),
    `${label} desired resource was not scoped to its node`,
  );
  assert(
    first.commands.some(
      (command) =>
        command.command_id === fixtures.commandId &&
        command.target_node_id === node.nodeId,
    ),
    `${label} command was not scoped to its node`,
  );
  await expectStatus(
    syncExchange(app, context, node.nodeId, node.token, fixtures.request),
    200,
    `${label} exact sync retry`,
  );
  const changed: SyncRequest = {
    ...fixtures.request,
    request_id: crypto.randomUUID(),
    events: [
      {
        ...fixtures.request.events[0],
        payload: { run_id: "changed-content", side: fixtures.side },
      },
    ],
  };
  await expectStatus(
    syncExchange(app, context, node.nodeId, node.token, changed),
    409,
    `${label} changed retry`,
  );
  const completion: SyncRequest = {
    ...fixtures.request,
    request_id: crypto.randomUUID(),
    sent_at: new Date().toISOString(),
    events: [],
    command_results: [
      {
        result_id: fixtures.resultId,
        command_id: fixtures.commandId,
        origin_node_id: node.nodeId,
        status: "succeeded",
        occurred_at: new Date().toISOString(),
        payload: {
          run_id: (fixtures.request.events[0].payload as { run_id: string }).run_id,
          side: fixtures.side,
        },
      },
    ],
  };
  const completed = await expectJson<SyncResponse>(
    await syncExchange(app, context, node.nodeId, node.token, completion),
    200,
    `${label} command completion`,
  );
  assert(
    completed.ack_command_result_ids.includes(fixtures.resultId),
    `${label} command result was not acknowledged`,
  );
  assert(
    !completed.commands.some((command) => command.command_id === fixtures.commandId),
    `${label} completed command remained pending`,
  );
}

async function assertDatabaseIsolation(
  database: Client,
  runId: string,
  side: TenantFixtures["side"],
  peerEventId: string,
  fixtures: TenantFixtures,
): Promise<void> {
  const result = await database.execute({
    sql: `SELECT
        (SELECT COUNT(*) FROM device_events
          WHERE id = ? AND json_extract(payload, '$.run_id') = ?) AS own_events,
        (SELECT COUNT(*) FROM device_events WHERE id = ?) AS peer_events,
        (SELECT COUNT(*) FROM desired_resources
          WHERE resource_id = ? AND target_node_id = ?) AS own_resources,
        (SELECT COUNT(*) FROM commands
          WHERE command_id = ? AND target_node_id = ? AND status = 'completed') AS completed_commands`,
    args: [
      fixtures.eventId,
      runId,
      peerEventId,
      fixtures.resourceId,
      fixtures.request.node_id,
      fixtures.commandId,
      fixtures.request.node_id,
    ],
  });
  const row = result.rows[0] ?? {};
  assert(Number(row.own_events) === 1, `${side} tenant is missing its own marker`);
  assert(Number(row.peer_events) === 0, `${side} tenant contains its peer marker`);
  assert(Number(row.own_resources) === 1, `${side} tenant is missing its desired resource`);
  assert(
    Number(row.completed_commands) === 1,
    `${side} tenant command was not completed`,
  );
}

async function exerciseBrowserBoundary(
  context: RegressionContext,
  runId: string,
  persistent: DirectoryTenant,
  ephemeral: DirectoryTenant,
  persistentNode: RegisteredNode,
  ephemeralNode: RegisteredNode,
): Promise<void> {
  const ephemeralMembership = await membership(context.directory, ephemeral.id);
  const persistentMembership = await membership(context.directory, persistent.id);
  const ephemeralIdentity: AccessIdentity = {
    email: ephemeralMembership.email,
    subject: `regression-ephemeral-${runId}`,
  };
  const persistentIdentity: AccessIdentity = {
    email: persistentMembership.email,
    subject:
      persistentMembership.accessSubject ?? `regression-persistent-denial-${runId}`,
  };
  const ephemeralApp = regressionApp(context, ephemeralIdentity);
  const persistentApp = regressionApp(context, persistentIdentity);

  const own = await expectJson<{
    tenant: { public_id: string };
    user: { role: string };
  }>(
    await ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/me`,
      {},
      workerEnvironment(context),
    ),
    200,
    "ephemeral own membership",
  );
  assert(own.tenant.public_id === ephemeral.publicId, "ephemeral own tenant mismatch");
  assert(own.user.role === "admin", "ephemeral test member is not admin");
  assert(
    !JSON.stringify(own).includes(ephemeral.databaseUrl) &&
      !JSON.stringify(own).includes(ephemeral.encryptedAuthToken),
    "tenant API exposed database routing credentials",
  );

  await expectStatus(
    ephemeralApp.request(
      `${context.publicOrigin}/api/t/${persistent.publicId}/dashboard`,
      {},
      workerEnvironment(context),
    ),
    404,
    "ephemeral identity opening persistent tenant",
  );
  await expectStatus(
    persistentApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/dashboard`,
      {},
      workerEnvironment(context),
    ),
    404,
    "persistent identity opening ephemeral tenant",
  );

  const repository = new DirectoryRepository(context.directory);
  const [ephemeralTenants, persistentTenants] = await Promise.all([
    repository.listMemberships(ephemeralIdentity),
    repository.listMemberships(persistentIdentity),
  ]);
  assert(
    ephemeralTenants.some((tenant) => tenant.publicId === ephemeral.publicId) &&
      !ephemeralTenants.some((tenant) => tenant.publicId === persistent.publicId),
    "ephemeral membership list crossed the tenant boundary",
  );
  assert(
    persistentTenants.some((tenant) => tenant.publicId === persistent.publicId) &&
      !persistentTenants.some((tenant) => tenant.publicId === ephemeral.publicId),
    "persistent membership list crossed the tenant boundary",
  );

  await expectStatus(
    ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/events`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://attacker.invalid",
        },
        body: JSON.stringify({
          event_type: "regression.management",
          payload: { run_id: runId, side: "ephemeral" },
        }),
      },
      workerEnvironment(context),
    ),
    403,
    "cross-origin management mutation",
  );

  const event = await expectJson<{ event: { id: string; payload: unknown } }>(
    await ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/events`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: context.publicOrigin,
        },
        body: JSON.stringify({
          event_type: "regression.management",
          payload: { run_id: runId, side: "ephemeral" },
        }),
      },
      workerEnvironment(context),
    ),
    201,
    "ephemeral management event",
  );
  assert(typeof event.event.id === "string", "management event has no ID");

  const events = await expectJson<{ events: Array<{ id: string }> }>(
    await ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/events?event_type=regression.management`,
      {},
      workerEnvironment(context),
    ),
    200,
    "ephemeral event listing",
  );
  assert(
    events.events.some((item) => item.id === event.event.id),
    "ephemeral event listing omitted the created event",
  );
  const nodes = await expectJson<{ nodes: Array<{ node_id: string }> }>(
    await ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/nodes`,
      {},
      workerEnvironment(context),
    ),
    200,
    "ephemeral node listing",
  );
  assert(
    nodes.nodes.some((node) => node.node_id === ephemeralNode.nodeId) &&
      !nodes.nodes.some((node) => node.node_id === persistentNode.nodeId),
    "ephemeral node listing crossed the tenant boundary",
  );
  const dashboard = await expectJson<{ edge_nodes: number; events_24h: number }>(
    await ephemeralApp.request(
      `${context.publicOrigin}/api/t/${ephemeral.publicId}/dashboard`,
      {},
      workerEnvironment(context),
    ),
    200,
    "ephemeral dashboard",
  );
  assert(
    dashboard.edge_nodes >= 1 && dashboard.events_24h >= 2,
    "ephemeral dashboard did not reflect regression activity",
  );
}

async function assertDatabaseCredentialIsolation(
  context: RegressionContext,
  persistent: DirectoryTenant,
  ephemeral: DirectoryTenant,
): Promise<void> {
  const persistentToken = await decryptTenantToken(context, persistent);
  const ephemeralToken = await decryptTenantToken(context, ephemeral);
  await expectDatabaseCredentialDenied(
    ephemeral.databaseUrl,
    persistentToken,
    "persistent credential opening ephemeral database",
  );
  await expectDatabaseCredentialDenied(
    persistent.databaseUrl,
    ephemeralToken,
    "ephemeral credential opening persistent database",
  );
}

async function expectDatabaseCredentialDenied(
  databaseUrl: string,
  token: string,
  label: string,
): Promise<void> {
  const client = createDatabaseClient({ url: databaseUrl, authToken: token });
  try {
    let denied = false;
    try {
      await client.execute("SELECT 1");
    } catch {
      denied = true;
    }
    if (!denied) {
      throw new Error(`${label}: peer database accepted a foreign database token`);
    }
  } finally {
    client.close();
  }
}

function regressionApp(
  context: RegressionContext,
  identity: AccessIdentity,
): ReturnType<typeof createApp> {
  return createApp({
    accessVerifier: async () => identity,
    runtimeFactory: createCloudRuntime,
    securityReporter: async () => undefined,
  });
}

function workerEnvironment(context: RegressionContext): Env {
  const allowed = {
    async limit() {
      return { success: true };
    },
  };
  return {
    CLOUD_HUB_PUBLIC_ORIGIN: context.publicOrigin,
    DIRECTORY_TURSO_DATABASE_URL: requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
    DIRECTORY_TURSO_AUTH_TOKEN: requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN"),
    TENANT_CREDENTIAL_MASTER_KEY: context.masterKey,
    SYNC_NODE_RATE_LIMITER: allowed,
    SYNC_IP_RATE_LIMITER: allowed,
  };
}

function syncExchange(
  app: ReturnType<typeof createApp>,
  context: RegressionContext,
  nodeId: string,
  token: string,
  body: SyncRequest,
): Promise<Response> {
  return rawSyncExchange(app, context, nodeId, token, body);
}

async function rawSyncExchange(
  app: ReturnType<typeof createApp>,
  context: RegressionContext,
  nodeId: string,
  token: string,
  body: unknown,
): Promise<Response> {
  return app.request(
    `${context.publicOrigin}/sync/v1/nodes/${nodeId}/exchange`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "CF-Connecting-IP": "192.0.2.1",
      },
      body: JSON.stringify(body),
    },
    workerEnvironment(context),
  );
}

async function registerRegressionNode(
  directory: Client,
  tenantId: string,
  label: string,
): Promise<RegisteredNode> {
  const nodeId = `INAEG-${crypto.randomUUID()}`;
  const credential = generateNodeCredential();
  const credentialId = crypto.randomUUID();
  const digest = await nodeCredentialDigest(credential.token, credential.salt);
  const now = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
  await directory.batch(
    [
      {
        sql: `INSERT INTO edge_nodes (
            node_id, tenant_id, label, node_type, status, created_at, updated_at
          ) VALUES (?, ?, ?, 'edge_gateway', 'active', ?, ?)`,
        args: [nodeId, tenantId, label, now, now],
      },
      {
        sql: `INSERT INTO edge_node_credentials (
            credential_id, node_id, status, credential_salt, credential_digest,
            created_at, updated_at, expires_at
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
            occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
          ) VALUES (?, 'tenant-regression', 'node.regression_register', ?,
              'edge_node', ?, ?)`,
        args: [now, tenantId, nodeId, canonicalJson({ label, expires_at: expiresAt })],
      },
    ],
    "write",
  );
  return { nodeId, token: credential.token, label };
}

async function cleanupRegressionRun(
  context: RegressionContext,
  manifest: RegressionManifest,
  manifestPath: string,
): Promise<void> {
  assertRegressionManifest(manifest);
  const live = await exactEphemeralTenant(context.directory, manifest);
  if (live?.status === "active" || live?.status === "suspended") {
    const now = new Date().toISOString();
    await context.directory.batch(
      [
        {
          sql: `UPDATE tenants
            SET status = 'deprovisioning', updated_at = ?
            WHERE id = ? AND public_id = ? AND turso_database_name = ?
              AND customer_reference = ?`,
          args: [
            now,
            manifest.tenant.id,
            manifest.tenant.public_id,
            manifest.tenant.database_name,
            manifest.tenant.customer_reference,
          ],
        },
        {
          sql: `INSERT INTO directory_audit_logs (
              occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
            ) VALUES (?, 'tenant-regression', 'tenant.regression_deprovision', ?,
                'tenant', ?, ?)`,
          args: [
            now,
            manifest.tenant.id,
            manifest.tenant.id,
            canonicalJson({ run_id: manifest.run_id }),
          ],
        },
      ],
      "write",
    );
  }

  let persistentCleanupError: unknown;
  try {
    await cleanupPersistentRunArtifacts(context, manifest.run_id);
  } catch (error) {
    persistentCleanupError = error;
  }

  let nodeCleanupComplete = false;
  try {
    await cleanupNodesForTenant(context.directory, manifest.tenant.id);
    nodeCleanupComplete = true;
  } catch (error) {
    if (!persistentCleanupError) {
      persistentCleanupError = error;
    }
  }

  let databaseCleanupComplete = false;
  try {
    await deleteExactEphemeralDatabase(context.platform, manifest);
    databaseCleanupComplete = true;
  } catch (error) {
    if (!persistentCleanupError) {
      persistentCleanupError = error;
    }
  }

  if (nodeCleanupComplete && databaseCleanupComplete) {
    const refreshed = await exactEphemeralTenant(context.directory, manifest);
    if (refreshed) {
      if (refreshed.status !== "deprovisioning") {
        throw new Error("ephemeral tenant is not deprovisioning during purge");
      }
      const now = new Date().toISOString();
      await context.directory.batch(
        [
          {
            sql: "DELETE FROM tenant_memberships WHERE tenant_id = ?",
            args: [manifest.tenant.id],
          },
          {
            sql: `DELETE FROM tenants
              WHERE id = ? AND public_id = ? AND turso_database_name = ?
                AND customer_reference = ? AND status = 'deprovisioning'`,
            args: [
              manifest.tenant.id,
              manifest.tenant.public_id,
              manifest.tenant.database_name,
              manifest.tenant.customer_reference,
            ],
          },
          {
            sql: `INSERT INTO directory_audit_logs (
                occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
              ) VALUES (?, 'tenant-regression', 'tenant.regression_delete', ?,
                  'tenant', ?, ?)`,
            args: [
              now,
              manifest.tenant.id,
              manifest.tenant.id,
              canonicalJson({
                run_id: manifest.run_id,
                public_id: manifest.tenant.public_id,
                database_name: manifest.tenant.database_name,
              }),
            ],
          },
        ],
        "write",
      );
      const stillPresent = await exactEphemeralTenant(context.directory, manifest);
      if (stillPresent) {
        throw new Error("ephemeral tenant directory row was not deleted");
      }
    }
  }
  if (persistentCleanupError) {
    throw persistentCleanupError;
  }
  await unlink(manifestPath);
}

async function cleanupPersistentRunArtifacts(
  context: RegressionContext,
  runId: string,
): Promise<void> {
  const matches = await findTenantMatches(
    context.directory,
    PERSISTENT_PUBLIC_ID,
    PERSISTENT_DATABASE_NAME,
    PERSISTENT_CUSTOMER_REFERENCE,
  );
  if (matches.length === 0) {
    return;
  }
  if (matches.length !== 1) {
    throw new Error("persistent regression tenant identifiers are ambiguous");
  }
  const persistent = directoryTenant(matches[0]);
  assertExactTenant(persistent, {
    publicId: PERSISTENT_PUBLIC_ID,
    displayName: PERSISTENT_DISPLAY_NAME,
    customerReference: PERSISTENT_CUSTOMER_REFERENCE,
    databaseName: PERSISTENT_DATABASE_NAME,
    status: "active",
  });
  const database = await openTenantDatabase(context, persistent);
  try {
    const events = await database.execute({
      sql: `SELECT id, origin_node_id
        FROM device_events
        WHERE json_extract(payload, '$.run_id') = ?`,
      args: [runId],
    });
    const eventIds = events.rows.map((row) => String(row.id));
    const nodeIds = [
      ...new Set(
        events.rows
          .map((row) => row.origin_node_id)
          .filter((value): value is string => typeof value === "string" && NODE_ID.test(value)),
      ),
    ];
    const statements: Array<{ sql: string; args: string[] }> = [
      {
        sql: `DELETE FROM command_results
          WHERE json_extract(payload, '$.run_id') = ?`,
        args: [runId],
      },
      {
        sql: "DELETE FROM commands WHERE idempotency_key = ?",
        args: [`regression:${runId}:persistent`],
      },
      {
        sql: "DELETE FROM desired_resources WHERE resource_id = ?",
        args: [`regression-${runId}-persistent`],
      },
    ];
    if (eventIds.length > 0) {
      statements.push({
        sql: `DELETE FROM audit_logs
          WHERE action = 'event.create'
            AND resource_type = 'device_event'
            AND resource_id IN (${eventIds.map(() => "?").join(", ")})`,
        args: eventIds,
      });
    }
    if (nodeIds.length > 0) {
      statements.push({
        sql: `DELETE FROM node_health
          WHERE node_id IN (${nodeIds.map(() => "?").join(", ")})`,
        args: nodeIds,
      });
    }
    statements.push({
      sql: `DELETE FROM device_events
        WHERE json_extract(payload, '$.run_id') = ?`,
      args: [runId],
    });
    await database.batch(statements, "write");
  } finally {
    database.close();
  }
  await cleanupNodesByLabel(
    context.directory,
    persistent.id,
    `regression:${runId}:persistent`,
  );
}

async function cleanupNodesByLabel(
  directory: Client,
  tenantId: string,
  label: string,
): Promise<void> {
  const nodes = await directory.execute({
    sql: "SELECT node_id FROM edge_nodes WHERE tenant_id = ? AND label = ?",
    args: [tenantId, label],
  });
  for (const row of nodes.rows) {
    const nodeId = String(row.node_id);
    if (!NODE_ID.test(nodeId)) {
      throw new Error("regression node identifier is invalid");
    }
    await revokeAndDeleteNode(directory, tenantId, nodeId);
  }
}

async function cleanupNodesForTenant(directory: Client, tenantId: string): Promise<void> {
  const nodes = await directory.execute({
    sql: "SELECT node_id FROM edge_nodes WHERE tenant_id = ? ORDER BY node_id",
    args: [tenantId],
  });
  for (const row of nodes.rows) {
    const nodeId = String(row.node_id);
    if (!NODE_ID.test(nodeId)) {
      throw new Error("ephemeral tenant contains an invalid node identifier");
    }
    await revokeAndDeleteNode(directory, tenantId, nodeId);
  }
}

async function revokeAndDeleteNode(
  directory: Client,
  tenantId: string,
  nodeId: string,
): Promise<void> {
  const now = new Date().toISOString();
  await directory.batch(
    [
      {
        sql: `UPDATE edge_nodes SET status = 'revoked', updated_at = ?
          WHERE node_id = ? AND tenant_id = ?`,
        args: [now, nodeId, tenantId],
      },
      {
        sql: `UPDATE edge_node_credentials SET status = 'revoked', updated_at = ?
          WHERE node_id = ?`,
        args: [now, nodeId],
      },
      {
        sql: "DELETE FROM edge_node_credentials WHERE node_id = ?",
        args: [nodeId],
      },
      {
        sql: "DELETE FROM edge_nodes WHERE node_id = ? AND tenant_id = ?",
        args: [nodeId, tenantId],
      },
    ],
    "write",
  );
}

async function deleteExactEphemeralDatabase(
  platform: Platform,
  manifest: RegressionManifest,
): Promise<void> {
  assertRegressionManifest(manifest);
  let database: Database;
  try {
    database = await platform.databases.get(manifest.tenant.database_name);
  } catch (error) {
    if (isTursoHttpError(error, 404)) {
      return;
    }
    throw error;
  }
  assertPlatformDatabase(database, manifest.tenant.database_name);
  await platform.databases.delete(manifest.tenant.database_name);
  try {
    await platform.databases.get(manifest.tenant.database_name);
    throw new Error("ephemeral database still exists after deletion");
  } catch (error) {
    if (!isTursoHttpError(error, 404)) {
      throw error;
    }
  }
}

async function exactEphemeralTenant(
  directory: Client,
  manifest: RegressionManifest,
): Promise<DirectoryTenant | null> {
  assertRegressionManifest(manifest);
  const matches = await directory.execute({
    sql: `SELECT *
      FROM tenants
      WHERE id = ? OR public_id = ? OR turso_database_name = ?
        OR customer_reference = ?`,
    args: [
      manifest.tenant.id,
      manifest.tenant.public_id,
      manifest.tenant.database_name,
      manifest.tenant.customer_reference,
    ],
  });
  if (matches.rows.length === 0) {
    return null;
  }
  if (matches.rows.length !== 1) {
    throw new Error("ephemeral manifest identifiers resolve to multiple tenant rows");
  }
  const tenant = directoryTenant(matches.rows[0]);
  if (
    tenant.id !== manifest.tenant.id ||
    tenant.publicId !== manifest.tenant.public_id ||
    tenant.databaseName !== manifest.tenant.database_name ||
    tenant.customerReference !== manifest.tenant.customer_reference
  ) {
    throw new Error("live tenant does not exactly match the ephemeral manifest");
  }
  return tenant;
}

async function openTenantDatabase(
  context: RegressionContext,
  tenant: DirectoryTenant,
): Promise<Client> {
  const token = await decryptTenantToken(context, tenant);
  return createDatabaseClient({ url: tenant.databaseUrl, authToken: token });
}

async function decryptTenantToken(
  context: RegressionContext,
  tenant: DirectoryTenant,
): Promise<string> {
  if (tenant.credentialKeyVersion !== 2) {
    throw new Error("regression tenant credential key version is unsupported");
  }
  return decryptTenantCredential(
    context.masterKey,
    {
      tenantId: tenant.id,
      databaseName: tenant.databaseName,
      databaseUrl: tenant.databaseUrl,
    },
    tenant.encryptedAuthToken,
  );
}

async function findTenantMatches(
  directory: Client,
  publicId: string,
  databaseName: string,
  customerReference: string,
) {
  const result = await directory.execute({
    sql: `SELECT *
      FROM tenants
      WHERE public_id = ? OR turso_database_name = ? OR customer_reference = ?`,
    args: [publicId, databaseName, customerReference],
  });
  return result.rows;
}

function directoryTenant(row: Record<string, unknown>): DirectoryTenant {
  const status = String(row.status);
  if (
    !["active", "suspended", "deprovisioning"].includes(status) ||
    Number(row.credential_key_version) !== 2
  ) {
    throw new Error("directory tenant row is invalid");
  }
  return {
    id: String(row.id),
    publicId: String(row.public_id),
    displayName: String(row.display_name),
    customerReference:
      row.customer_reference === null || row.customer_reference === undefined
        ? null
        : String(row.customer_reference),
    status: status as DirectoryTenant["status"],
    databaseName: String(row.turso_database_name),
    databaseUrl: normalizeTursoDatabaseUrl(
      String(row.turso_database_url),
      "directory tenant database URL",
    ),
    encryptedAuthToken: String(row.turso_auth_token_ciphertext),
    credentialKeyVersion: Number(row.credential_key_version),
  };
}

function assertExactTenant(
  tenant: DirectoryTenant,
  expected: {
    publicId: string;
    displayName: string;
    customerReference: string;
    databaseName: string;
    status: DirectoryTenant["status"];
  },
): void {
  if (
    tenant.publicId !== expected.publicId ||
    tenant.displayName !== expected.displayName ||
    tenant.customerReference !== expected.customerReference ||
    tenant.databaseName !== expected.databaseName ||
    tenant.status !== expected.status
  ) {
    throw new Error(`regression tenant does not match its fixed definition: ${expected.publicId}`);
  }
}

async function assertExactAdminMembership(
  directory: Client,
  tenantId: string,
  adminEmail: string,
): Promise<void> {
  const result = await directory.execute({
    sql: `SELECT email, role, status
      FROM tenant_memberships
      WHERE tenant_id = ?
      ORDER BY lower(email)`,
    args: [tenantId],
  });
  if (
    result.rows.length !== 1 ||
    normalizeEmail(String(result.rows[0].email)) !== normalizeEmail(adminEmail) ||
    result.rows[0].role !== "admin" ||
    result.rows[0].status !== "active"
  ) {
    throw new Error("persistent regression tenant must have exactly one configured active admin");
  }
}

async function membership(
  directory: Client,
  tenantId: string,
): Promise<{ email: string; accessSubject: string | null }> {
  const result = await directory.execute({
    sql: `SELECT email, access_subject
      FROM tenant_memberships
      WHERE tenant_id = ? AND role = 'admin' AND status = 'active'
      ORDER BY lower(email)`,
    args: [tenantId],
  });
  if (result.rows.length !== 1) {
    throw new Error("regression tenant must have exactly one active admin");
  }
  return {
    email: normalizeEmail(String(result.rows[0].email)),
    accessSubject:
      result.rows[0].access_subject === null ||
      result.rows[0].access_subject === undefined
        ? null
        : String(result.rows[0].access_subject),
  };
}

async function otherTenantSnapshot(directory: Client): Promise<string> {
  const queries = [
    {
      sql: `SELECT id, public_id, display_name, customer_reference, status,
          turso_database_name, turso_database_url, credential_key_version
        FROM tenants
        WHERE COALESCE(customer_reference, '') <> ?
        ORDER BY id`,
      args: [PERSISTENT_CUSTOMER_REFERENCE],
    },
    {
      sql: `SELECT m.tenant_id, lower(m.email) AS email, m.access_subject, m.role, m.status
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE COALESCE(t.customer_reference, '') <> ?
        ORDER BY m.tenant_id, lower(m.email)`,
      args: [PERSISTENT_CUSTOMER_REFERENCE],
    },
    {
      sql: `SELECT n.node_id, n.tenant_id, n.label, n.node_type, n.status
        FROM edge_nodes n
        JOIN tenants t ON t.id = n.tenant_id
        WHERE COALESCE(t.customer_reference, '') <> ?
        ORDER BY n.tenant_id, n.node_id`,
      args: [PERSISTENT_CUSTOMER_REFERENCE],
    },
    {
      sql: `SELECT c.credential_id, c.node_id, c.status, c.expires_at
        FROM edge_node_credentials c
        JOIN edge_nodes n ON n.node_id = c.node_id
        JOIN tenants t ON t.id = n.tenant_id
        WHERE COALESCE(t.customer_reference, '') <> ?
        ORDER BY c.node_id, c.credential_id`,
      args: [PERSISTENT_CUSTOMER_REFERENCE],
    },
  ];
  const values: unknown[] = [];
  for (const query of queries) {
    const result = await directory.execute(query);
    values.push(
      result.rows.map((row) =>
        Object.fromEntries(
          Object.entries(row).map(([key, value]) => [key, value === undefined ? null : value]),
        ),
      ),
    );
  }
  return sha256Hex(canonicalJson(values));
}

async function assertNoPendingEphemeralState(
  directory: Client,
  stateDirectory: string,
): Promise<void> {
  const tenants = await directory.execute({
    sql: `SELECT public_id
      FROM tenants
      WHERE customer_reference LIKE 'regression:ephemeral:%'
      ORDER BY public_id`,
    args: [],
  });
  const manifests = await listManifestNames(stateDirectory);
  if (tenants.rows.length > 0 || manifests.length > 0) {
    throw new Error(
      "a previous ephemeral regression requires cleanup before a new run; inspect regression:tenant status",
    );
  }
}

async function writeManifest(
  path: string,
  manifest: RegressionManifest,
): Promise<void> {
  assertRegressionManifest(manifest);
  await ensurePrivateStateDirectory(dirname(path));
  await writeFile(path, `${JSON.stringify(manifest, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
  await assertPrivateRegularFile(path);
}

async function readManifest(path: string): Promise<RegressionManifest> {
  await assertPrivateRegularFile(path);
  let value: unknown;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch {
    throw new Error("regression manifest is not valid JSON");
  }
  return assertRegressionManifest(value);
}

async function ensurePrivateStateDirectory(path: string): Promise<void> {
  await mkdir(path, { recursive: true, mode: 0o700 });
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("regression state path must be a regular directory");
  }
  if ((stat.mode & 0o077) !== 0) {
    await chmod(path, 0o700);
  }
  const secured = await lstat(path);
  if ((secured.mode & 0o077) !== 0) {
    throw new Error("regression state directory must not be group/world accessible");
  }
  if (typeof process.getuid === "function" && secured.uid !== process.getuid()) {
    throw new Error("regression state directory must be owned by the current user");
  }
}

async function assertPrivateRegularFile(path: string): Promise<void> {
  const stat = await lstat(path);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("regression manifest must be a regular non-symlink file");
  }
  if ((stat.mode & 0o077) !== 0) {
    throw new Error("regression manifest must have mode 0600 or stricter");
  }
  if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
    throw new Error("regression manifest must be owned by the current user");
  }
}

async function listManifestNames(stateDirectory: string): Promise<string[]> {
  try {
    await ensurePrivateStateDirectory(stateDirectory);
    return (await readdir(stateDirectory))
      .filter((name) => /^[0-9]{8}t[0-9]{6}z-[a-f0-9]{8}\.json$/.test(name))
      .sort();
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return [];
    }
    throw error;
  }
}

function secureExternalPath(value: string, label: string): string {
  if (!isAbsolute(value)) {
    throw new Error(`${label} must be an absolute path`);
  }
  const normalized = resolve(value);
  const fromRepository = relative(REPOSITORY_ROOT, normalized);
  if (
    fromRepository === "" ||
    (!fromRepository.startsWith("..") && !isAbsolute(fromRepository))
  ) {
    throw new Error(`${label} must be outside the repository`);
  }
  return normalized;
}

function defaultStateDirectory(): string {
  const xdgStateHome = process.env.XDG_STATE_HOME?.trim();
  if (xdgStateHome) {
    if (!isAbsolute(xdgStateHome)) {
      throw new Error("XDG_STATE_HOME must be an absolute path");
    }
    return resolve(xdgStateHome, "inas", "cloud-regression");
  }
  const userHome = process.env.HOME?.trim();
  if (!userHome || !isAbsolute(userHome)) {
    throw new Error(
      "set XDG_STATE_HOME or pass an absolute --state-dir outside the repository",
    );
  }
  return resolve(userHome, ".local", "state", "inas", "cloud-regression");
}

function assertPlatformDatabase(
  database: Database | CreatedDatabase,
  expectedName: string,
): void {
  if (database.name !== expectedName || !database.hostname.endsWith(".turso.io")) {
    throw new Error(`Turso database identity mismatch for ${expectedName}`);
  }
}

function ensureDeleteProtection(databaseName: string): void {
  const before = runTurso([
    "db",
    "config",
    "delete-protection",
    "show",
    databaseName,
  ]);
  if (/Delete Protection off/i.test(before)) {
    runTurso([
      "db",
      "config",
      "delete-protection",
      "enable",
      databaseName,
    ]);
  } else if (!/Delete Protection on/i.test(before)) {
    throw new Error(`could not determine delete protection for ${databaseName}`);
  }
  const after = runTurso([
    "db",
    "config",
    "delete-protection",
    "show",
    databaseName,
  ]);
  if (!/Delete Protection on/i.test(after)) {
    throw new Error(`delete protection is not enabled for ${databaseName}`);
  }
}

function runTurso(args: string[]): string {
  const result = spawnSync("turso", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    const detail = redact(`${result.stdout}\n${result.stderr}`).trim().slice(0, 1_000);
    throw new Error(`turso ${args.slice(0, 4).join(" ")} failed: ${detail}`);
  }
  return `${result.stdout}\n${result.stderr}`;
}

function tursoWhoAmI(): string {
  const output = runTurso(["auth", "whoami"]).trim();
  const candidate = output.split(/\s+/).at(-1) ?? "";
  return candidate;
}

function extractJwt(output: string): string {
  const match = output.match(/\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/);
  if (!match) {
    throw new Error("Turso CLI did not return a platform token");
  }
  return match[0];
}

function regressionAdminEmail(): string {
  const supplied = process.env.CLOUD_HUB_REGRESSION_ADMIN_EMAIL?.trim();
  if (supplied) {
    return normalizeEmail(supplied);
  }
  const allowed = (process.env.CLOUDFLARE_ACCESS_ALLOWED_EMAILS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (allowed.length !== 1) {
    throw new Error(
      "set CLOUD_HUB_REGRESSION_ADMIN_EMAIL, or configure exactly one CLOUDFLARE_ACCESS_ALLOWED_EMAILS entry",
    );
  }
  return normalizeEmail(allowed[0]);
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}

function normalizeTursoSlug(value: string, label: string): string {
  const normalized = value.trim().toLowerCase();
  if (!/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(normalized)) {
    throw new Error(`${label} is invalid`);
  }
  return normalized;
}

function exactPublicOrigin(value: string): string {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("CLOUD_HUB_PUBLIC_ORIGIN must be an exact HTTPS origin");
  }
  return url.origin;
}

async function expectStatus(
  responsePromise: Promise<Response> | Response,
  expected: number,
  label: string,
): Promise<Response> {
  const response = await responsePromise;
  if (response.status !== expected) {
    const body = (await response.text()).slice(0, 500);
    throw new Error(`${label}: expected ${expected}, received ${response.status}: ${body}`);
  }
  return response;
}

async function expectJson<T>(
  response: Response,
  expected: number,
  label: string,
): Promise<T> {
  if (response.status !== expected) {
    const body = (await response.text()).slice(0, 500);
    throw new Error(`${label}: expected ${expected}, received ${response.status}: ${body}`);
  }
  return (await response.json()) as T;
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function safeError(error: unknown): string {
  return redact(error instanceof Error ? error.message : String(error)).slice(0, 1_000);
}

function redact(value: string): string {
  return value.replace(
    /\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g,
    "[REDACTED_JWT]",
  );
}
