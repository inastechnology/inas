import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";


describe("Wrangler exposure defaults", () => {
  it("does not expose workers.dev or deployment preview URLs", () => {
    const configPath = resolve(dirname(fileURLToPath(import.meta.url)), "../wrangler.jsonc");
    const config = JSON.parse(readFileSync(configPath, "utf8"));

    expect(config.workers_dev).toBe(false);
    expect(config.preview_urls).toBe(false);
  });

  it("binds the private system help AI Search instance", () => {
    const configPath = resolve(dirname(fileURLToPath(import.meta.url)), "../wrangler.jsonc");
    const config = JSON.parse(readFileSync(configPath, "utf8"));

    expect(config.ai_search).toEqual([
      { binding: "SYSTEM_HELP_SEARCH", instance_name: "inas-system-help", remote: true },
    ]);
  });
});
