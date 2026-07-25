import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import {
  REQUIRED_WORKER_SECRETS,
  validateHubCloudConfig,
} from "../src/security-config";

const configPath = new URL("../wrangler.jsonc", import.meta.url);
const config = JSON.parse(await readFile(configPath, "utf8")) as unknown;
const errors = validateHubCloudConfig(config);

if (process.argv.includes("--check-remote-secrets") && errors.length === 0) {
  const executable = process.platform === "win32" ? "wrangler.cmd" : "wrangler";
  const result = spawnSync(
    executable,
    ["secret", "list", "--config", fileURLToPath(configPath), "--format", "json"],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  if (result.status !== 0) {
    errors.push("could not verify the deployed Worker secrets with Wrangler");
  } else {
    try {
      const values = JSON.parse(result.stdout) as unknown;
      const names = new Set(
        Array.isArray(values)
          ? values
              .map((value) =>
                typeof value === "object" &&
                value !== null &&
                typeof (value as { name?: unknown }).name === "string"
                  ? (value as { name: string }).name
                  : "",
              )
              .filter(Boolean)
          : [],
      );
      for (const secret of REQUIRED_WORKER_SECRETS) {
        if (!names.has(secret)) {
          errors.push(`deployed Worker secret is missing: ${secret}`);
        }
      }
    } catch {
      errors.push("Wrangler returned an invalid secret inventory");
    }
  }
}

if (errors.length > 0) {
  console.error("Hub Cloud security preflight failed:");
  for (const error of errors) {
    console.error(`- ${error}`);
  }
  process.exitCode = 1;
} else {
  console.log("Hub Cloud security preflight passed.");
}
