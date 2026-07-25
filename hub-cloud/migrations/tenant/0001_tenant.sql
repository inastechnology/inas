CREATE TABLE IF NOT EXISTS schema_migrations (
  name TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_events (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('sync', 'management')),
  origin_node_id TEXT,
  sequence INTEGER,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  direction TEXT NOT NULL,
  device_id TEXT,
  payload TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (origin_node_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_device_events_occurred_at
  ON device_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_device_events_device_time
  ON device_events (device_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_device_events_type_time
  ON device_events (event_type, occurred_at);

CREATE TABLE IF NOT EXISTS command_results (
  result_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL,
  origin_node_id TEXT NOT NULL,
  status TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  error_code TEXT,
  message TEXT,
  payload TEXT,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_command_results_command
  ON command_results (command_id, occurred_at);

CREATE TABLE IF NOT EXISTS node_health (
  node_id TEXT PRIMARY KEY,
  reported_at TEXT NOT NULL,
  status TEXT NOT NULL,
  software_version TEXT NOT NULL,
  hardware_profile_id TEXT,
  outbox_depth INTEGER NOT NULL,
  mqtt_connected INTEGER NOT NULL,
  storage_total_bytes INTEGER,
  storage_free_bytes INTEGER NOT NULL,
  capabilities TEXT NOT NULL,
  details TEXT
);

CREATE TABLE IF NOT EXISTS desired_resources (
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  target_node_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  operation TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  payload TEXT,
  PRIMARY KEY (resource_type, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_desired_resources_target
  ON desired_resources (target_node_id, resource_type, resource_id);

CREATE TABLE IF NOT EXISTS commands (
  command_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  command_type TEXT NOT NULL,
  target_node_id TEXT NOT NULL,
  device_id TEXT,
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'cancelled')),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commands_target_status_expiry
  ON commands (target_node_id, status, expires_at);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_occurred_at
  ON audit_logs (occurred_at);
