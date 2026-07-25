import { createClient } from "@libsql/client";
import { createInterface } from "node:readline/promises";
import { parseArgs } from "node:util";
import { chmod, lstat, mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { base64UrlEncode, generateNodeCredential, nodeCredentialDigest } from "../src/crypto";
import { canonicalJson, normalizeTursoDatabaseUrl } from "../src/database";
import { normalizePublicTenantId } from "../src/tenant-id";
import { buildGatewayOverlay } from "./gateway-overlay";

const options = parseArgs({
  options: {
    tenant: { type: "string" },
    label: { type: "string" },
    output: { type: "string", short: "o" },
    "hardware-profile": { type: "string", default: "egw-cm4-standard-r1" },
    "cloud-origin": { type: "string" },
    "credential-valid-days": { type: "string", default: "400" },
    yes: { type: "boolean", short: "y", default: false },
  },
  strict: true,
}).values;
const terminal = createInterface({ input: process.stdin, output: process.stdout });
let preparedOutput: string | null = null;
let directoryCommitted = false;

try {
  const directoryUrl = normalizeTursoDatabaseUrl(
    requiredEnvironment("DIRECTORY_TURSO_DATABASE_URL"),
    "DIRECTORY_TURSO_DATABASE_URL",
  );
  const directoryToken = requiredEnvironment("DIRECTORY_TURSO_AUTH_TOKEN");
  const directory = createClient({ url: directoryUrl, authToken: directoryToken });
  try {
    const tenant = await chooseTenant(directory, options.tenant);
    const label = await requiredInput("Gateway表示名", options.label);
    const output = validateOutput(await requiredInput("出荷オーバーレイ出力先（新規・リポジトリ外）", options.output));
    await requireMissing(output);
    const hardwareProfile = normalizeHardwareProfile(options["hardware-profile"] ?? "");
    const cloudOrigin = normalizeOrigin(
      options["cloud-origin"] ||
        process.env.CLOUD_HUB_PUBLIC_ORIGIN ||
        "https://cloud-hub.inas-technologies.com",
    );
    const nodeId = `INAEG-${crypto.randomUUID()}`;
    const credentialId = crypto.randomUUID();
    const credentialValidDays = boundedInteger(
      options["credential-valid-days"],
      "credential-valid-days",
      30,
      730,
    );
    const credentialExpiresAt = new Date(
      Date.now() + credentialValidDays * 24 * 60 * 60 * 1000,
    ).toISOString();
    const { token: parentToken, salt } = generateNodeCredential();
    const digest = await nodeCredentialDigest(parentToken, salt);
    const mqttUsername = `edge-${nodeId.slice(-12)}`.toLowerCase();
    const mqttPassword = randomSecret(32);
    const apPassword = randomSecret(18);
    const overlay = buildGatewayOverlay({
      nodeId,
      parentToken,
      mqttUsername,
      mqttPassword,
      hardwareProfile,
      cloudOrigin,
      tenantPublicId: tenant.publicId,
      tenantDisplayName: tenant.displayName,
      label,
      apPassword,
      credentialExpiresAt,
    });

    console.log(
      JSON.stringify(
        {
          action: "kit-edge-gateway",
          tenant: tenant.publicId,
          node_id: nodeId,
          label,
          output,
          cloud_hub_url: `${cloudOrigin}/t/${tenant.publicId}/`,
        },
        null,
        2,
      ),
    );
    await confirm();
    await mkdir(dirname(output), { recursive: true, mode: 0o700 });
    await mkdir(output, { mode: 0o700 });
    preparedOutput = output;
    await chmod(output, 0o700);
    await writeOverlay(output, overlay);

    const now = new Date().toISOString();
    await directory.batch(
      [
        {
          sql: `INSERT INTO edge_nodes (
              node_id, tenant_id, label, node_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'edge_gateway', 'active', ?, ?)`,
          args: [nodeId, tenant.id, label, now, now],
        },
        {
          sql: `INSERT INTO edge_node_credentials (
              credential_id, node_id, status, credential_salt,
              credential_digest, created_at, updated_at, expires_at
            ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?)`,
          args: [credentialId, nodeId, salt, digest, now, now, credentialExpiresAt],
        },
        {
          sql: `INSERT INTO directory_audit_logs (
              occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
            ) VALUES (?, 'factory', 'edge_gateway.kit', ?, 'edge_node', ?, ?)`,
          args: [
            now,
            tenant.id,
            nodeId,
            canonicalJson({
              label,
              hardware_profile_id: hardwareProfile,
              tenant_public_id: tenant.publicId,
              credential_id: credentialId,
              credential_expires_at: credentialExpiresAt,
            }),
          ],
        },
      ],
      "write",
    );
    directoryCommitted = true;
    console.log(
      JSON.stringify(
        {
          status: "kitted",
          node_id: nodeId,
          tenant: tenant.publicId,
          output,
          note: "Parent and MQTT credentials exist only in protected files inside this overlay.",
        },
        null,
        2,
      ),
    );
  } finally {
    directory.close();
  }
} catch (error) {
  if (preparedOutput && !directoryCommitted) {
    await rm(preparedOutput, { recursive: true, force: true });
  } else if (preparedOutput) {
    console.error(
      `The node was registered. Preserve its one-time credentials in ${preparedOutput}.`,
    );
  }
  throw error;
} finally {
  terminal.close();
}

interface TenantChoice {
  id: string;
  publicId: string;
  displayName: string;
}

async function chooseTenant(client: ReturnType<typeof createClient>, supplied: string | undefined): Promise<TenantChoice> {
  if (supplied) {
    const publicId = normalizePublicTenantId(supplied);
    const result = await client.execute({
      sql: "SELECT id, public_id, display_name FROM tenants WHERE public_id = ? AND status = 'active' LIMIT 1",
      args: [publicId],
    });
    if (!result.rows[0]) {
      throw new Error("active tenant was not found");
    }
    return tenantFromRow(result.rows[0]);
  }
  if (!process.stdin.isTTY) {
    throw new Error("--tenant is required when stdin is not interactive");
  }
  const result = await client.execute(
    "SELECT id, public_id, display_name FROM tenants WHERE status = 'active' ORDER BY lower(display_name), public_id",
  );
  const tenants = result.rows.map(tenantFromRow);
  if (tenants.length === 0) {
    throw new Error("no active tenant exists; provision a tenant first");
  }
  tenants.forEach((tenant, index) => {
    console.log(`${index + 1}. ${tenant.displayName} (${tenant.publicId})`);
  });
  const selection = Number((await terminal.question("出荷先番号: ")).trim());
  if (!Number.isSafeInteger(selection) || selection < 1 || selection > tenants.length) {
    throw new Error("tenant selection is invalid");
  }
  return tenants[selection - 1];
}

async function writeOverlay(root: string, overlay: Map<string, { content: string; mode: number }>): Promise<void> {
  for (const [relativePath, file] of overlay) {
    const target = join(root, ...relativePath.split("/"));
    await mkdir(dirname(target), { recursive: true, mode: 0o700 });
    await writeFile(target, file.content, { encoding: "utf8", mode: file.mode, flag: "wx" });
    await chmod(target, file.mode);
  }
}

function validateOutput(value: string): string {
  if (!isAbsolute(value)) {
    throw new Error("output must be an absolute path");
  }
  const output = resolve(value);
  const repository = resolve(fileURLToPath(new URL("../..", import.meta.url)));
  const home = process.env.HOME ? resolve(process.env.HOME) : "";
  if (output === parse(output).root || output === repository || (home && output === home)) {
    throw new Error("output must not be a filesystem root, home, or repository root");
  }
  const fromRepository = relative(repository, output);
  if (fromRepository === "" || (!fromRepository.startsWith(`..${sep}`) && fromRepository !== "..")) {
    throw new Error("credential-bearing output must be outside the source repository");
  }
  return output;
}

function normalizeOrigin(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("cloud origin must be an HTTPS origin without credentials, path, query, or fragment");
  }
  return url.origin;
}

function normalizeHardwareProfile(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(normalized) || normalized.length > 100) {
    throw new Error("hardware profile is invalid");
  }
  return normalized;
}

function tenantFromRow(row: Record<string, unknown>): TenantChoice {
  return {
    id: String(row.id),
    publicId: String(row.public_id),
    displayName: String(row.display_name),
  };
}

async function requiredInput(label: string, supplied: string | undefined): Promise<string> {
  const value = supplied?.trim() || (process.stdin.isTTY ? (await terminal.question(`${label}: `)).trim() : "");
  if (!value || value.length > 300) {
    throw new Error(`${label} is required and must be at most 300 characters`);
  }
  return value;
}

async function confirm(): Promise<void> {
  if (options.yes) {
    return;
  }
  if (!process.stdin.isTTY) {
    throw new Error("--yes is required when stdin is not interactive");
  }
  const answer = (await terminal.question("登録・出荷ファイル作成を行う場合は KIT と入力してください: ")).trim();
  if (answer !== "KIT") {
    throw new Error("kitting was cancelled");
  }
}

function randomSecret(bytes: number): string {
  const value = new Uint8Array(bytes);
  crypto.getRandomValues(value);
  return base64UrlEncode(value);
}

function boundedInteger(
  value: string | undefined,
  name: string,
  minimum: number,
  maximum: number,
): number {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim() ?? "";
  if (!value) {
    throw new Error(`${name} is not configured`);
  }
  return value;
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
