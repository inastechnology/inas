import { describe, expect, it } from "vitest";

import {
  decryptTenantCredential,
  encryptTenantCredential,
  generateMasterKey,
  generateNodeCredential,
  nodeCredentialDigest,
  verifyNodeCredential,
} from "../src/crypto";

describe("tenant credential envelopes", () => {
  it("binds ciphertext to tenant identity and exact Turso routing", async () => {
    const key = generateMasterKey();
    const context = {
      tenantId: "tenant-internal-a",
      databaseName: "inas-tenant-a",
      databaseUrl: "libsql://inas-tenant-a-example.turso.io",
    };
    const encrypted = await encryptTenantCredential(key, context, "database-token");
    await expect(decryptTenantCredential(key, context, encrypted)).resolves.toBe("database-token");
    await expect(
      decryptTenantCredential(key, { ...context, tenantId: "tenant-internal-b" }, encrypted),
    ).rejects.toThrow("cannot be decrypted");
    await expect(
      decryptTenantCredential(
        key,
        { ...context, databaseUrl: "libsql://attacker-example.turso.io" },
        encrypted,
      ),
    ).rejects.toThrow(
      "cannot be decrypted",
    );
    expect(encrypted).not.toContain("database-token");
  });
});

describe("node credentials", () => {
  it("stores a salted digest rather than the bearer token", async () => {
    const credential = generateNodeCredential();
    const digest = await nodeCredentialDigest(credential.token, credential.salt);
    expect(credential.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(digest).toMatch(/^[0-9a-f]{64}$/);
    expect(digest).not.toContain(credential.token);
    await expect(verifyNodeCredential(credential.token, credential.salt, digest)).resolves.toBe(true);
    const replacement = credential.token.endsWith("A") ? "B" : "A";
    await expect(
      verifyNodeCredential(`${credential.token.slice(0, -1)}${replacement}`, credential.salt, digest),
    ).resolves.toBe(false);
  });
});
