CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK (role IN ('home', 'farmer', 'company', 'school', 'research', 'other')),
  scale TEXT NOT NULL CHECK (scale IN ('pots', 'under_100m2', '100_1000m2', 'over_1000m2', 'planning')),
  pain TEXT NOT NULL CHECK (pain IN ('remote_monitoring', 'task_planning', 'watering', 'records')),
  email TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  audience TEXT NOT NULL CHECK (audience IN ('home', 'farmer', 'team')),
  attribution_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_status_created_at ON leads (status, created_at DESC);
