import { describe, expect, it } from "vitest";

import { normalizeIssuer } from "../src/access";

describe("Access helpers", () => {
  it("normalizes team domains to issuer URLs", () => {
    expect(normalizeIssuer("athena.cloudflareaccess.com/")).toBe("https://athena.cloudflareaccess.com");
    expect(normalizeIssuer("https://athena.cloudflareaccess.com/")).toBe("https://athena.cloudflareaccess.com");
  });

  it("returns an empty issuer for unset values", () => {
    expect(normalizeIssuer("")).toBe("");
    expect(normalizeIssuer(undefined)).toBe("");
  });
});
