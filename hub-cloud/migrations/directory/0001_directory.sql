CREATE TABLE IF NOT EXISTS schema_migrations (
  name TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  customer_reference TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'suspended', 'deprovisioning')),
  turso_database_name TEXT NOT NULL UNIQUE,
  turso_database_url TEXT NOT NULL,
  turso_auth_token_ciphertext TEXT NOT NULL,
  credential_key_version INTEGER NOT NULL DEFAULT 2 CHECK (credential_key_version = 2),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL COLLATE NOCASE,
  access_subject TEXT CHECK (
    access_subject IS NULL OR
    (length(access_subject) BETWEEN 1 AND 512)
  ),
  role TEXT NOT NULL CHECK (role IN ('reader', 'operator', 'admin')),
  status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, email),
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_email
  ON tenant_memberships (email, status, tenant_id);

CREATE TRIGGER IF NOT EXISTS tenant_memberships_keep_one_admin_update
BEFORE UPDATE OF role, status ON tenant_memberships
WHEN OLD.role = 'admin' AND OLD.status = 'active'
  AND (NEW.role <> 'admin' OR NEW.status <> 'active')
  AND NOT EXISTS (
    SELECT 1 FROM tenant_memberships
    WHERE tenant_id = OLD.tenant_id
      AND email <> OLD.email
      AND role = 'admin'
      AND status = 'active'
  )
BEGIN
  SELECT RAISE(ABORT, 'cannot remove the last active tenant admin');
END;

CREATE TRIGGER IF NOT EXISTS tenant_memberships_keep_one_admin_delete
BEFORE DELETE ON tenant_memberships
WHEN OLD.role = 'admin' AND OLD.status = 'active'
  AND NOT EXISTS (
    SELECT 1 FROM tenant_memberships
    WHERE tenant_id = OLD.tenant_id
      AND email <> OLD.email
      AND role = 'admin'
      AND status = 'active'
  )
BEGIN
  SELECT RAISE(ABORT, 'cannot delete the last active tenant admin');
END;

CREATE TABLE IF NOT EXISTS edge_nodes (
  node_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  label TEXT,
  node_type TEXT NOT NULL CHECK (node_type = 'edge_gateway'),
  status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT,
  FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX IF NOT EXISTS idx_edge_nodes_tenant
  ON edge_nodes (tenant_id, status, node_id);

CREATE TABLE IF NOT EXISTS edge_node_credentials (
  credential_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
  credential_salt TEXT NOT NULL,
  credential_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT CHECK (
    expires_at IS NULL OR
    (datetime(expires_at) IS NOT NULL AND datetime(expires_at) > datetime(created_at))
  ),
  last_used_at TEXT,
  FOREIGN KEY (node_id) REFERENCES edge_nodes(node_id),
  UNIQUE (node_id, credential_digest)
);

CREATE INDEX IF NOT EXISTS idx_edge_node_credentials_node
  ON edge_node_credentials (node_id, status, expires_at, credential_id);

CREATE TRIGGER IF NOT EXISTS edge_node_credentials_limit_active_insert
BEFORE INSERT ON edge_node_credentials
WHEN NEW.status = 'active'
  AND (NEW.expires_at IS NULL OR datetime(NEW.expires_at) > datetime('now'))
  AND (
  SELECT COUNT(*) FROM edge_node_credentials
  WHERE node_id = NEW.node_id
    AND status = 'active'
    AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
) >= 2
BEGIN
  SELECT RAISE(ABORT, 'a node may have at most two active credentials');
END;

CREATE TRIGGER IF NOT EXISTS edge_node_credentials_limit_active_update
BEFORE UPDATE OF status ON edge_node_credentials
WHEN NEW.status = 'active'
  AND OLD.status <> 'active'
  AND (NEW.expires_at IS NULL OR datetime(NEW.expires_at) > datetime('now'))
  AND (
  SELECT COUNT(*) FROM edge_node_credentials
  WHERE node_id = NEW.node_id
    AND status = 'active'
    AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
) >= 2
BEGIN
  SELECT RAISE(ABORT, 'a node may have at most two active credentials');
END;

CREATE TRIGGER IF NOT EXISTS edge_node_credentials_keep_one_update
BEFORE UPDATE OF status ON edge_node_credentials
WHEN OLD.status = 'active'
  AND (OLD.expires_at IS NULL OR datetime(OLD.expires_at) > datetime('now'))
  AND NEW.status <> 'active' AND NOT EXISTS (
  SELECT 1 FROM edge_node_credentials
  WHERE node_id = OLD.node_id
    AND credential_id <> OLD.credential_id
    AND status = 'active'
    AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
)
BEGIN
  SELECT RAISE(ABORT, 'cannot revoke the last active node credential');
END;

CREATE TRIGGER IF NOT EXISTS edge_node_credentials_keep_one_delete
BEFORE DELETE ON edge_node_credentials
WHEN OLD.status = 'active'
  AND (OLD.expires_at IS NULL OR datetime(OLD.expires_at) > datetime('now'))
  AND NOT EXISTS (
  SELECT 1 FROM edge_node_credentials
  WHERE node_id = OLD.node_id
    AND credential_id <> OLD.credential_id
    AND status = 'active'
    AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
)
BEGIN
  SELECT RAISE(ABORT, 'cannot delete the last active node credential');
END;

CREATE TABLE IF NOT EXISTS directory_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  tenant_id TEXT,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_directory_audit_logs_tenant_time
  ON directory_audit_logs (tenant_id, occurred_at);
