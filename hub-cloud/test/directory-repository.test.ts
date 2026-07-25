import { createClient } from "@libsql/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { DirectoryRepository } from "../src/repositories/directory";
import { applyMigrations } from "../scripts/migrations";
import { EDGE_NODE_ID } from "./helpers";

describe("directory tenant resolution", () => {
  let client: ReturnType<typeof createClient>;
  let repository: DirectoryRepository;

  beforeEach(async () => {
    client = createClient({ url: "file::memory:" });
    await applyMigrations(client, new URL("../migrations/directory/", import.meta.url));
    const now = "2026-07-23T10:00:00.000Z";
    await client.batch(
      [
        tenantInsert("tenant-internal-a", "tenant-a", "database-a", now),
        tenantInsert("tenant-internal-b", "tenant-b", "database-b", now),
        {
          sql: `INSERT INTO tenant_memberships (
              tenant_id, email, role, status, created_at, updated_at
            ) VALUES ('tenant-internal-a', 'alice@example.com', 'admin', 'active', ?, ?)`,
          args: [now, now],
        },
        {
          sql: `INSERT INTO tenant_memberships (
              tenant_id, email, role, status, created_at, updated_at
            ) VALUES ('tenant-internal-b', 'bob@example.com', 'reader', 'active', ?, ?)`,
          args: [now, now],
        },
        {
          sql: `INSERT INTO edge_nodes (
              node_id, tenant_id, label, node_type, status, created_at, updated_at
            ) VALUES (?, 'tenant-internal-a', 'North field', 'edge_gateway',
              'active', ?, ?)`,
          args: [EDGE_NODE_ID, now, now],
        },
        {
          sql: `INSERT INTO edge_node_credentials (
              credential_id, node_id, status, credential_salt,
              credential_digest, created_at, updated_at
            ) VALUES ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', ?, 'active', ?, ?, ?, ?)`,
          args: [EDGE_NODE_ID, "A".repeat(22), "a".repeat(64), now, now],
        },
      ],
      "write",
    );
    repository = new DirectoryRepository(client);
  });

  afterEach(() => {
    client.close();
  });

  it("combines the verified email and public ID before returning DB routing", async () => {
    const alice = { email: "alice@example.com", subject: "access-alice-v1" };
    const memberships = await repository.listMemberships({
      ...alice,
      email: "ALICE@example.com",
    });
    expect(memberships).toEqual([
      {
        id: "tenant-internal-a",
        publicId: "tenant-a",
        displayName: "Tenant tenant-a",
        status: "active",
        role: "admin",
      },
    ]);
    expect(JSON.stringify(memberships)).not.toContain("libsql://");

    await expect(repository.resolveMembership("tenant-b", alice)).resolves.toBeNull();
    await expect(repository.resolveMembership("tenant-a", alice)).resolves.toMatchObject({
      id: "tenant-internal-a",
      databaseName: "database-a",
      databaseUrl: "libsql://database-a-example.turso.io",
      role: "admin",
    });
    await expect(
      repository.resolveMembership("tenant-a", {
        email: alice.email,
        subject: "recreated-access-identity",
      }),
    ).resolves.toBeNull();
    await expect(
      repository.listMemberships({
        email: alice.email,
        subject: "recreated-access-identity",
      }),
    ).resolves.toEqual([]);
    const bindingAudit = await client.execute({
      sql: `SELECT action, actor, resource_id, payload
        FROM directory_audit_logs
        WHERE action = 'membership.bind_access_subject'`,
      args: [],
    });
    expect(bindingAudit.rows).toHaveLength(1);
    expect(bindingAudit.rows[0]).toMatchObject({
      actor: "alice@example.com",
      resource_id: "alice@example.com",
      payload: '{"public_id":"tenant-a"}',
    });
  });

  it("binds an Edge node to the directory-selected tenant", async () => {
    await expect(repository.findNode(EDGE_NODE_ID)).resolves.toMatchObject({
      nodeId: EDGE_NODE_ID,
      nodeType: "edge_gateway",
      tenant: {
        id: "tenant-internal-a",
        publicId: "tenant-a",
        databaseName: "database-a",
      },
      credentials: [
        {
          credentialId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          digest: "a".repeat(64),
        },
      ],
    });
    await expect(repository.listTenantNodes("tenant-internal-b")).resolves.toEqual([]);
    await expect(repository.listTenantNodes("tenant-internal-a")).resolves.toEqual([
      {
        nodeId: EDGE_NODE_ID,
        label: "North field",
        nodeType: "edge_gateway",
        status: "active",
        lastSeenAt: null,
      },
    ]);
  });

  it("does not permit a Local Hub registration in the Cloud directory", async () => {
    await expect(
      client.execute({
        sql: `INSERT INTO edge_nodes (
            node_id, tenant_id, node_type, status, created_at, updated_at
          ) VALUES (?, 'tenant-internal-a', 'local_hub', 'active', ?, ?)`,
        args: [
          "INALH-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          "2026-07-23T10:00:00.000Z",
          "2026-07-23T10:00:00.000Z",
        ],
      }),
    ).rejects.toThrow();
  });

  it("prevents duplicate memberships that differ only by email case", async () => {
    await expect(
      client.execute({
        sql: `INSERT INTO tenant_memberships (
            tenant_id, email, role, status, created_at, updated_at
          ) VALUES ('tenant-internal-a', 'ALICE@example.com', 'reader', 'active', ?, ?)`,
        args: ["2026-07-23T10:00:00.000Z", "2026-07-23T10:00:00.000Z"],
      }),
    ).rejects.toThrow();
  });

  it("prevents removing the last active tenant administrator", async () => {
    await expect(
      client.execute({
        sql: `UPDATE tenant_memberships
          SET status = 'revoked'
          WHERE tenant_id = 'tenant-internal-a' AND email = 'alice@example.com'`,
        args: [],
      }),
    ).rejects.toThrow(/last active tenant admin/);

    const now = "2026-07-23T10:01:00.000Z";
    await client.execute({
      sql: `INSERT INTO tenant_memberships (
          tenant_id, email, role, status, created_at, updated_at
        ) VALUES ('tenant-internal-a', 'second-admin@example.com',
          'admin', 'active', ?, ?)`,
      args: [now, now],
    });
    await expect(
      client.execute({
        sql: `UPDATE tenant_memberships
          SET status = 'revoked'
          WHERE tenant_id = 'tenant-internal-a' AND email = 'alice@example.com'`,
        args: [],
      }),
    ).resolves.toMatchObject({ rowsAffected: 1 });
  });

  it("allows the final administrator to be removed only after deprovisioning begins", async () => {
    await expect(
      client.execute(
        "DELETE FROM tenant_memberships WHERE tenant_id = 'tenant-internal-a'",
      ),
    ).rejects.toThrow(/last active tenant admin/);

    await client.execute(
      "UPDATE tenants SET status = 'deprovisioning' WHERE id = 'tenant-internal-a'",
    );
    await expect(
      client.execute(
        "DELETE FROM tenant_memberships WHERE tenant_id = 'tenant-internal-a'",
      ),
    ).resolves.toMatchObject({ rowsAffected: 1 });
  });

  it("allows two overlapping node credentials but prevents unsafe removal", async () => {
    const now = "2026-07-23T10:01:00.000Z";
    const future = "2027-07-23T10:01:00.000Z";
    await insertCredential(
      client,
      "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      "b".repeat(64),
      now,
      future,
    );
    await expect(
      insertCredential(
        client,
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "c".repeat(64),
        now,
        future,
      ),
    ).rejects.toThrow(/at most two active credentials/);

    await expect(
      client.execute({
        sql: `UPDATE edge_node_credentials
          SET status = 'revoked'
          WHERE credential_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'`,
        args: [],
      }),
    ).resolves.toMatchObject({ rowsAffected: 1 });
    await expect(
      client.execute({
        sql: `UPDATE edge_node_credentials
          SET status = 'revoked'
          WHERE credential_id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'`,
        args: [],
      }),
    ).rejects.toThrow(/last active node credential/);
  });

  it("allows the final node credential to be removed only after node revocation", async () => {
    await expect(
      client.execute({
        sql: "DELETE FROM edge_node_credentials WHERE node_id = ?",
        args: [EDGE_NODE_ID],
      }),
    ).rejects.toThrow(/last active node credential/);

    await client.execute({
      sql: "UPDATE edge_nodes SET status = 'revoked' WHERE node_id = ?",
      args: [EDGE_NODE_ID],
    });
    await expect(
      client.execute({
        sql: "DELETE FROM edge_node_credentials WHERE node_id = ?",
        args: [EDGE_NODE_ID],
      }),
    ).resolves.toMatchObject({ rowsAffected: 1 });
  });

  it("ignores expired credentials and records the credential used for Sync", async () => {
    await insertCredential(
      client,
      "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      "d".repeat(64),
      "2025-01-01T00:00:00.000Z",
      "2025-02-01T00:00:00.000Z",
    );
    const record = await repository.findNode(EDGE_NODE_ID);
    expect(record?.credentials.map((value) => value.credentialId)).toEqual([
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    ]);

    const usedAt = "2026-07-23T10:02:00.000Z";
    await repository.touchNode(
      EDGE_NODE_ID,
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      usedAt,
    );
    const credential = await client.execute({
      sql: `SELECT last_used_at
        FROM edge_node_credentials
        WHERE credential_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'`,
      args: [],
    });
    expect(credential.rows[0]?.last_used_at).toBe(usedAt);
  });
});

function tenantInsert(id: string, publicId: string, databaseName: string, now: string) {
  return {
    sql: `INSERT INTO tenants (
        id, public_id, display_name, status, turso_database_name,
        turso_database_url, turso_auth_token_ciphertext,
        credential_key_version, created_at, updated_at
      ) VALUES (?, ?, ?, 'active', ?, ?, ?, 2, ?, ?)`,
    args: [
      id,
      publicId,
      `Tenant ${publicId}`,
      databaseName,
      `libsql://${databaseName}-example.turso.io`,
      `v2.encrypted.${databaseName}`,
      now,
      now,
    ],
  };
}

async function insertCredential(
  client: ReturnType<typeof createClient>,
  credentialId: string,
  digest: string,
  createdAt: string,
  expiresAt: string,
) {
  return client.execute({
    sql: `INSERT INTO edge_node_credentials (
        credential_id, node_id, status, credential_salt,
        credential_digest, created_at, updated_at, expires_at
      ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?)`,
    args: [
      credentialId,
      EDGE_NODE_ID,
      "B".repeat(22),
      digest,
      createdAt,
      createdAt,
      expiresAt,
    ],
  });
}
