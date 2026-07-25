import { createClient as createDatabaseClient } from "@libsql/client";
import { createClient as createPlatformClient } from "@tursodatabase/api";
import { chmod, lstat, mkdir, writeFile } from "node:fs/promises";
import { createInterface } from "node:readline/promises";
import { dirname, isAbsolute, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { generateMasterKey } from "../src/crypto";
import { normalizeTursoDatabaseUrl } from "../src/database";
import { applyMigrations } from "./migrations";
import { isTursoHttpError } from "./turso-error";

const DATABASE_NAME = /^[a-z][a-z0-9-]{2,62}$/;
const options = parseArgs({
  options: {
    "database-name": { type: "string", default: "inas-cloud-directory" },
    output: { type: "string", short: "o" },
    "adopt-existing": { type: "boolean", default: false },
    yes: { type: "boolean", short: "y", default: false },
  },
  strict: true,
}).values;
const terminal = createInterface({ input: process.stdin, output: process.stdout });
let createdDatabase = false;
let databaseName = "";

try {
  const tursoOrg = requiredEnvironment("TURSO_ORG");
  const tursoToken = requiredEnvironment("TURSO_PLATFORM_TOKEN");
  const tursoGroup = process.env.TURSO_GROUP?.trim() || "default";
  databaseName = normalizeDatabaseName(options["database-name"] ?? "");
  const output = validateOutput(
    await requiredInput("credential env出力先（新規・リポジトリ外）", options.output),
  );
  await requireMissing(output);
  console.log(
    JSON.stringify(
      {
        action: "bootstrap-cloud-directory",
        organization: tursoOrg,
        group: tursoGroup,
        database_name: databaseName,
        credential_output: output,
      },
      null,
      2,
    ),
  );
  await confirm();

  const platform = createPlatformClient({ org: tursoOrg, token: tursoToken });
  let database;
  try {
    database = await platform.databases.get(databaseName);
    if (!options["adopt-existing"]) {
      throw new Error(
        `Turso DB ${databaseName} already exists. Use the original directory credentials, ` +
          "or inspect an empty orphan and pass --adopt-existing.",
      );
    }
  } catch (error) {
    if (!isTursoHttpError(error, 404)) {
      throw error;
    }
    database = await platform.databases.create(databaseName, { group: tursoGroup });
    createdDatabase = true;
  }

  const token = await platform.databases.createToken(databaseName, {
    authorization: "full-access",
  });
  const databaseUrl = normalizeTursoDatabaseUrl(
    `libsql://${database.hostname}`,
    "provisioned directory database URL",
  );
  const client = createDatabaseClient({ url: databaseUrl, authToken: token.jwt });
  try {
    await applyMigrations(client, new URL("../migrations/directory/", import.meta.url));
    const tenants = await client.execute("SELECT COUNT(*) AS count FROM tenants");
    if (!createdDatabase && Number(tenants.rows[0].count) > 0) {
      throw new Error(
        "The adopted directory contains tenants. Recover its original TENANT_CREDENTIAL_MASTER_KEY; " +
          "creating a replacement key would make tenant database credentials unreadable.",
      );
    }
  } finally {
    client.close();
  }

  await mkdir(dirname(output), { recursive: true, mode: 0o700 });
  const content = [
    `DIRECTORY_TURSO_DATABASE_URL=${databaseUrl}`,
    `DIRECTORY_TURSO_AUTH_TOKEN=${token.jwt}`,
    `TENANT_CREDENTIAL_MASTER_KEY=${generateMasterKey()}`,
    "",
  ].join("\n");
  await writeFile(output, content, { encoding: "utf8", mode: 0o600, flag: "wx" });
  await chmod(output, 0o600);
  console.log(
    JSON.stringify(
      {
        status: "bootstrapped",
        database_name: databaseName,
        credential_output: output,
        next: [
          "Load this mode-0600 file only in the factory shell.",
          "Configure DIRECTORY_TURSO_DATABASE_URL in wrangler.jsonc.",
          "Set DIRECTORY_TURSO_AUTH_TOKEN and TENANT_CREDENTIAL_MASTER_KEY with wrangler secret put.",
          "Never copy this file to an Edge Gateway or commit it.",
        ],
      },
      null,
      2,
    ),
  );
} catch (error) {
  if (createdDatabase) {
    console.error(
      `Bootstrap stopped after Turso DB ${databaseName} was created. ` +
        "It was intentionally not deleted; inspect it before using --adopt-existing.",
    );
  }
  throw error;
} finally {
  terminal.close();
}

function normalizeDatabaseName(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (!DATABASE_NAME.test(normalized)) {
    throw new Error("database name must be 3-63 lowercase letters, numbers, or hyphens and start with a letter");
  }
  return normalized;
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
    throw new Error("credential output must be outside the source repository");
  }
  return output;
}

async function requiredInput(label: string, supplied: string | undefined): Promise<string> {
  const value = supplied?.trim() || (process.stdin.isTTY ? (await terminal.question(`${label}: `)).trim() : "");
  if (!value || value.length > 500) {
    throw new Error(`${label} is required and must be at most 500 characters`);
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
  const answer = (await terminal.question("Directory DBを作成する場合は BOOTSTRAP と入力してください: ")).trim();
  if (answer !== "BOOTSTRAP") {
    throw new Error("bootstrap was cancelled");
  }
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
