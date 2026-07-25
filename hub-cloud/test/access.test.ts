import { describe, expect, it } from "vitest";

import {
  accessIdentityFromClaims,
  accessTeamOrigin,
  assertAccessTokenTimeClaims,
} from "../src/access";

describe("Cloudflare Access team configuration", () => {
  it("normalizes only the team HTTPS origin", () => {
    expect(accessTeamOrigin("example.cloudflareaccess.com")).toBe("https://example.cloudflareaccess.com");
    expect(accessTeamOrigin("https://example.cloudflareaccess.com/")).toBe(
      "https://example.cloudflareaccess.com",
    );
  });

  it.each([
    "http://example.cloudflareaccess.com",
    "https://example.cloudflareaccess.com/path",
    "https://user@example.cloudflareaccess.com",
    "https://example.com",
    "https://bad..cloudflareaccess.com",
  ])("rejects unsafe team domain %s", (value) => {
    expect(() => accessTeamOrigin(value)).toThrow();
  });
});

describe("Cloudflare Access application claims", () => {
  const validClaims = {
    type: "app",
    email: "ADMIN@Example.COM",
    sub: "access-user-123",
  };

  it("accepts only an application identity and normalizes its email", () => {
    expect(accessIdentityFromClaims(validClaims)).toEqual({
      email: "admin@example.com",
      subject: "access-user-123",
    });
  });

  it.each([
    { ...validClaims, type: "org" },
    { ...validClaims, sub: "" },
    { ...validClaims, email: "invalid" },
    { ...validClaims, email: "admin\u0000@example.com" },
  ])("rejects a non-application or incomplete identity", (claims) => {
    expect(() => accessIdentityFromClaims(claims)).toThrow("authentication failed");
  });

  it("rejects inconsistent or future token time claims", () => {
    expect(() =>
      assertAccessTokenTimeClaims(
        { iat: 1_000, nbf: 1_000, exp: 1_100 },
        1_050,
      ),
    ).not.toThrow();
    expect(() =>
      assertAccessTokenTimeClaims(
        { iat: 1_100, nbf: 1_000, exp: 1_200 },
        1_000,
      ),
    ).toThrow("authentication failed");
    expect(() =>
      assertAccessTokenTimeClaims(
        { iat: 1_000, nbf: 1_000, exp: 999 },
        1_000,
      ),
    ).toThrow("authentication failed");
  });
});
