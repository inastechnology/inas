import { spawnSync } from "node:child_process";

const databaseName =
  process.env.DIRECTORY_TURSO_DATABASE_NAME?.trim() || "inas-cloud-directory";
if (!/^[a-z][a-z0-9-]{2,62}$/.test(databaseName)) {
  throw new Error("DIRECTORY_TURSO_DATABASE_NAME is invalid");
}

const apply = process.argv.includes("--apply");
const before = protectionStatus(databaseName);
if (!apply) {
  console.log(
    JSON.stringify(
      {
        status: before ? "already_enabled" : "planned",
        database: databaseName,
        delete_protection: before,
        action: before ? null : "enable delete protection",
      },
      null,
      2,
    ),
  );
  process.exit(0);
}

if (!before) {
  runTurso(["db", "config", "delete-protection", "enable", databaseName]);
}
const after = protectionStatus(databaseName);
if (!after) {
  throw new Error(`Delete protection verification failed for ${databaseName}`);
}
console.log(
  JSON.stringify(
    {
      status: "protected",
      database: databaseName,
      delete_protection: true,
    },
    null,
    2,
  ),
);

function protectionStatus(name: string): boolean {
  const output = runTurso(["db", "config", "delete-protection", "show", name]);
  if (/Delete Protection on/i.test(output)) {
    return true;
  }
  if (/Delete Protection off/i.test(output)) {
    return false;
  }
  throw new Error(`Could not determine delete protection for ${name}`);
}

function runTurso(args: string[]): string {
  const result = spawnSync("turso", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    const detail = `${result.stdout}\n${result.stderr}`.trim().slice(0, 1_000);
    throw new Error(`turso ${args.slice(0, 4).join(" ")} failed: ${detail}`);
  }
  return `${result.stdout}\n${result.stderr}`;
}
