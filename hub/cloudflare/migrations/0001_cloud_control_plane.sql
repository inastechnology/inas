CREATE TABLE IF NOT EXISTS device_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  direction TEXT NOT NULL,
  device_id TEXT,
  topic TEXT,
  category TEXT,
  action TEXT,
  kind TEXT,
  seq_id TEXT,
  mqtt_rc INTEGER,
  retain INTEGER,
  next_sleep_sec REAL,
  next_wake_at TEXT,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_events_occurred_at ON device_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_device_events_device_id ON device_events (device_id);
CREATE INDEX IF NOT EXISTS idx_device_events_event_type ON device_events (event_type);

CREATE TABLE IF NOT EXISTS admin_users (
  email TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('reader', 'operator', 'admin')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  actor_email TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_occurred_at ON audit_logs (occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_email ON audit_logs (actor_email);
