import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

export const cloudflareDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const manifest = JSON.parse(readFileSync(resolve(cloudflareDir, "data/system-help-manifest.json"), "utf8"));
export const bucket = "inas-system-help-docs";

export function wrangler(args, options = {}) {
  const executable = process.env.WRANGLER_BIN || "npx";
  const commandArgs = process.env.WRANGLER_BIN ? args : ["wrangler", ...args];
  const result = spawnSync(executable, commandArgs, {
    cwd: cloudflareDir,
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
    timeout: options.timeout ?? 120_000,
  });
  if (result.status !== 0 && !options.allowFailure) {
    const detail = result.error?.message || (options.capture ? result.stderr || result.stdout : "");
    throw new Error(`wrangler ${args[0]} failed${detail ? `: ${detail.trim()}` : ""}`);
  }
  return result;
}

export function validateDocuments() {
  const seen = new Set();
  return manifest.documents.map((document) => {
    if (!document.key.startsWith("system-help/") || !document.key.endsWith(".md") || seen.has(document.key)) {
      throw new Error(`invalid or duplicate document key: ${document.key}`);
    }
    seen.add(document.key);
    const path = resolve(cloudflareDir, document.path);
    const content = readFileSync(path, "utf8");
    if (!content.startsWith("# ") || content.length < 100) {
      throw new Error(`system help document is incomplete: ${document.path}`);
    }
    return { ...document, path, content };
  });
}
