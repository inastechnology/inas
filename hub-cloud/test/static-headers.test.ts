import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

const expectedHeaders = [
  "Content-Security-Policy: default-src 'self'; base-uri 'none'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self'",
  "Cross-Origin-Opener-Policy: same-origin",
  "Cross-Origin-Resource-Policy: same-origin",
  "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()",
  "Referrer-Policy: no-referrer",
  "Strict-Transport-Security: max-age=31536000; includeSubDomains",
  "X-Content-Type-Options: nosniff",
  "X-Frame-Options: DENY",
  "X-Permitted-Cross-Domain-Policies: none",
];

describe("static asset security headers", () => {
  it("applies the Worker security boundary to every static asset", async () => {
    const rules = await readFile(new URL("../public/_headers", import.meta.url), "utf8");

    expect(rules.trimStart().startsWith("/*\n")).toBe(true);
    for (const header of expectedHeaders) {
      expect(rules).toContain(`  ${header}\n`);
    }
  });
});
