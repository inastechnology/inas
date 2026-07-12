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

CREATE TABLE IF NOT EXISTS sensor_measurement_definitions (
  metric TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  unit TEXT,
  category TEXT NOT NULL,
  device_kinds TEXT NOT NULL,
  value_type TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sensor_measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  device_kind TEXT,
  measured_at TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT,
  quality TEXT NOT NULL DEFAULT 'ok',
  raw_value REAL,
  source TEXT NOT NULL DEFAULT 'mqtt_status',
  payload TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(metric) REFERENCES sensor_measurement_definitions(metric)
);

CREATE INDEX IF NOT EXISTS idx_sensor_measurements_device_time ON sensor_measurements (device_id, measured_at);
CREATE INDEX IF NOT EXISTS idx_sensor_measurements_metric_time ON sensor_measurements (metric, measured_at);
CREATE INDEX IF NOT EXISTS idx_sensor_measurements_device_metric_time ON sensor_measurements (device_id, metric, measured_at);
