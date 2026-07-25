import type {
  DirectoryRepositoryContract,
  AccessIdentity,
  NodeRecord,
  NodeType,
  Role,
  SqlClient,
  TenantMembership,
  TenantNodeSummary,
  TenantRecord,
  TenantStatus,
} from "../types";
import { canonicalJson, normalizeTursoDatabaseUrl } from "../database";
import { normalizePublicTenantId } from "../tenant-id";

const ROLES = new Set<Role>(["reader", "operator", "admin"]);
const TENANT_STATUSES = new Set<TenantStatus>(["active", "suspended", "deprovisioning"]);
const NODE_TYPES = new Set<NodeType>(["edge_gateway"]);

export class DirectoryRepository implements DirectoryRepositoryContract {
  constructor(private readonly client: SqlClient) {}

  async listMemberships(identity: AccessIdentity): Promise<TenantMembership[]> {
    const result = await this.client.execute({
      sql: `SELECT t.id, t.public_id, t.display_name, t.status, m.role
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE lower(m.email) = lower(?)
          AND (m.access_subject IS NULL OR m.access_subject = ?)
          AND m.status = 'active'
          AND t.status = 'active'
        ORDER BY lower(t.display_name), t.public_id`,
      args: [identity.email, identity.subject],
    });
    return result.rows.map(membershipFromRow).filter((value): value is TenantMembership => value !== null);
  }

  async resolveMembership(
    publicId: string,
    identity: AccessIdentity,
  ): Promise<(TenantRecord & { role: Role }) | null> {
    await this.bindAccessSubject(publicId, identity);
    const result = await this.client.execute({
      sql: `SELECT t.id, t.public_id, t.display_name, t.status,
          t.turso_database_name, t.turso_database_url,
          t.turso_auth_token_ciphertext, t.credential_key_version, m.role
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE t.public_id = ?
          AND lower(m.email) = lower(?)
          AND m.access_subject = ?
          AND m.status = 'active'
          AND t.status = 'active'
        LIMIT 1`,
      args: [publicId, identity.email, identity.subject],
    });
    if (!result.rows[0]) {
      return null;
    }
    const tenant = tenantFromRow(result.rows[0]);
    const role = roleFromValue(result.rows[0].role);
    return tenant && role ? { ...tenant, role } : null;
  }

  private async bindAccessSubject(publicId: string, identity: AccessIdentity): Promise<void> {
    if (!this.client.batch) {
      throw new Error("directory database client does not support atomic batches");
    }
    const now = new Date().toISOString();
    await this.client.batch(
      [
        {
          sql: `UPDATE tenant_memberships
            SET access_subject = ?, updated_at = ?
            WHERE tenant_id = (
                SELECT id FROM tenants WHERE public_id = ? AND status = 'active' LIMIT 1
              )
              AND lower(email) = lower(?)
              AND status = 'active'
              AND access_subject IS NULL`,
          args: [identity.subject, now, publicId, identity.email],
        },
        {
          sql: `INSERT INTO directory_audit_logs (
              occurred_at, actor, action, tenant_id, resource_type, resource_id, payload
            ) SELECT ?, ?, 'membership.bind_access_subject', id,
                'tenant_membership', ?, ?
              FROM tenants
              WHERE public_id = ? AND changes() = 1`,
          args: [
            now,
            identity.email,
            identity.email,
            canonicalJson({ public_id: publicId }),
            publicId,
          ],
        },
      ],
      "write",
    );
  }

  async findNode(nodeId: string): Promise<NodeRecord | null> {
    const result = await this.client.execute({
      sql: `SELECT n.node_id, n.node_type, n.status AS node_status,
          c.credential_id, c.credential_salt, c.credential_digest,
          c.expires_at,
          t.id, t.public_id, t.display_name, t.status,
          t.turso_database_name, t.turso_database_url,
          t.turso_auth_token_ciphertext, t.credential_key_version
        FROM edge_nodes n
        JOIN tenants t ON t.id = n.tenant_id
        JOIN edge_node_credentials c ON c.node_id = n.node_id
        WHERE n.node_id = ?
          AND n.status = 'active'
          AND t.status = 'active'
          AND c.status = 'active'
          AND (c.expires_at IS NULL OR datetime(c.expires_at) > datetime(?))
        ORDER BY c.created_at DESC, c.credential_id
        LIMIT 3`,
      args: [nodeId, new Date().toISOString()],
    });
    const row = result.rows[0];
    const tenant = row ? tenantFromRow(row) : null;
    const nodeType = row && typeof row.node_type === "string" && NODE_TYPES.has(row.node_type as NodeType) ? (row.node_type as NodeType) : null;
    const credentials = result.rows
      .map(credentialFromRow)
      .filter((value): value is NonNullable<typeof value> => value !== null);
    if (!row || !tenant || !nodeType || credentials.length === 0) {
      return null;
    }
    return {
      nodeId: String(row.node_id),
      nodeType,
      status: "active",
      credentials,
      tenant,
    };
  }

  async listTenantNodes(tenantId: string): Promise<TenantNodeSummary[]> {
    const result = await this.client.execute({
      sql: `SELECT node_id, label, node_type, status, last_seen_at
        FROM edge_nodes
        WHERE tenant_id = ?
        ORDER BY lower(COALESCE(label, node_id)), node_id`,
      args: [tenantId],
    });
    return result.rows.map(nodeSummaryFromRow).filter((value): value is TenantNodeSummary => value !== null);
  }

  async touchNode(nodeId: string, credentialId: string, at: string): Promise<void> {
    if (!this.client.batch) {
      throw new Error("directory database client does not support atomic batches");
    }
    await this.client.batch([
      {
        sql: "UPDATE edge_nodes SET last_seen_at = ?, updated_at = ? WHERE node_id = ? AND status = 'active'",
        args: [at, at, nodeId],
      },
      {
        sql: `UPDATE edge_node_credentials
          SET last_used_at = ?, updated_at = ?
          WHERE credential_id = ? AND node_id = ? AND status = 'active'`,
        args: [at, at, credentialId, nodeId],
      },
    ], "write");
  }
}

function credentialFromRow(row: Record<string, unknown>) {
  if (
    typeof row.credential_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      row.credential_id,
    ) ||
    typeof row.credential_salt !== "string" ||
    !/^[A-Za-z0-9_-]{22}$/.test(row.credential_salt) ||
    typeof row.credential_digest !== "string" ||
    !/^[0-9a-f]{64}$/.test(row.credential_digest)
  ) {
    return null;
  }
  return {
    credentialId: row.credential_id,
    salt: row.credential_salt,
    digest: row.credential_digest,
    expiresAt:
      row.expires_at === null || row.expires_at === undefined
        ? null
        : String(row.expires_at),
  };
}

function nodeSummaryFromRow(row: Record<string, unknown>): TenantNodeSummary | null {
  const nodeType =
    typeof row.node_type === "string" && NODE_TYPES.has(row.node_type as NodeType)
      ? (row.node_type as NodeType)
      : null;
  const status = row.status === "active" || row.status === "revoked" ? row.status : null;
  if (!nodeType || !status) {
    return null;
  }
  return {
    nodeId: String(row.node_id),
    label: row.label === null || row.label === undefined ? null : String(row.label),
    nodeType,
    status,
    lastSeenAt: row.last_seen_at === null || row.last_seen_at === undefined ? null : String(row.last_seen_at),
  };
}

function membershipFromRow(row: Record<string, unknown>): TenantMembership | null {
  const role = roleFromValue(row.role);
  const status = tenantStatusFromValue(row.status);
  if (!role || !status) {
    return null;
  }
  return {
    id: String(row.id),
    publicId: String(row.public_id),
    displayName: String(row.display_name),
    status,
    role,
  };
}

function tenantFromRow(row: Record<string, unknown>): TenantRecord | null {
  const status = tenantStatusFromValue(row.status);
  const credentialKeyVersion = Number(row.credential_key_version);
  let publicId: string;
  let databaseUrl: string;
  try {
    publicId = normalizePublicTenantId(String(row.public_id));
    databaseUrl = normalizeTursoDatabaseUrl(String(row.turso_database_url), "tenant database URL");
  } catch {
    return null;
  }
  if (
    !status ||
    !Number.isSafeInteger(credentialKeyVersion) ||
    credentialKeyVersion !== 2 ||
    typeof row.turso_auth_token_ciphertext !== "string" ||
    !row.turso_auth_token_ciphertext.startsWith("v2.") ||
    typeof row.turso_database_name !== "string" ||
    !/^[a-z][a-z0-9-]{2,62}$/.test(row.turso_database_name)
  ) {
    return null;
  }
  return {
    id: String(row.id),
    publicId,
    displayName: String(row.display_name),
    status,
    databaseName: row.turso_database_name,
    databaseUrl,
    encryptedAuthToken: row.turso_auth_token_ciphertext,
    credentialKeyVersion,
  };
}

function roleFromValue(value: unknown): Role | null {
  return typeof value === "string" && ROLES.has(value as Role) ? (value as Role) : null;
}

function tenantStatusFromValue(value: unknown): TenantStatus | null {
  return typeof value === "string" && TENANT_STATUSES.has(value as TenantStatus) ? (value as TenantStatus) : null;
}
