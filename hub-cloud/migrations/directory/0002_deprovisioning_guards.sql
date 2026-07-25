DROP TRIGGER IF EXISTS tenant_memberships_keep_one_admin_update;
DROP TRIGGER IF EXISTS tenant_memberships_keep_one_admin_delete;
DROP TRIGGER IF EXISTS edge_node_credentials_keep_one_update;
DROP TRIGGER IF EXISTS edge_node_credentials_keep_one_delete;

CREATE TRIGGER tenant_memberships_keep_one_admin_update
BEFORE UPDATE OF role, status ON tenant_memberships
WHEN OLD.role = 'admin' AND OLD.status = 'active'
  AND (NEW.role <> 'admin' OR NEW.status <> 'active')
  AND EXISTS (
    SELECT 1 FROM tenants
    WHERE id = OLD.tenant_id
      AND status <> 'deprovisioning'
  )
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

CREATE TRIGGER tenant_memberships_keep_one_admin_delete
BEFORE DELETE ON tenant_memberships
WHEN OLD.role = 'admin' AND OLD.status = 'active'
  AND EXISTS (
    SELECT 1 FROM tenants
    WHERE id = OLD.tenant_id
      AND status <> 'deprovisioning'
  )
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

CREATE TRIGGER edge_node_credentials_keep_one_update
BEFORE UPDATE OF status ON edge_node_credentials
WHEN OLD.status = 'active'
  AND (OLD.expires_at IS NULL OR datetime(OLD.expires_at) > datetime('now'))
  AND NEW.status <> 'active'
  AND EXISTS (
    SELECT 1 FROM edge_nodes
    WHERE node_id = OLD.node_id
      AND status = 'active'
  )
  AND NOT EXISTS (
    SELECT 1 FROM edge_node_credentials
    WHERE node_id = OLD.node_id
      AND credential_id <> OLD.credential_id
      AND status = 'active'
      AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
  )
BEGIN
  SELECT RAISE(ABORT, 'cannot revoke the last active node credential');
END;

CREATE TRIGGER edge_node_credentials_keep_one_delete
BEFORE DELETE ON edge_node_credentials
WHEN OLD.status = 'active'
  AND (OLD.expires_at IS NULL OR datetime(OLD.expires_at) > datetime('now'))
  AND EXISTS (
    SELECT 1 FROM edge_nodes
    WHERE node_id = OLD.node_id
      AND status = 'active'
  )
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
