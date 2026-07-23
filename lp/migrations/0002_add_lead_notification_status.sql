ALTER TABLE leads ADD COLUMN notification_status TEXT NOT NULL DEFAULT 'pending'
  CHECK (notification_status IN ('pending', 'sent', 'failed', 'disabled'));

ALTER TABLE leads ADD COLUMN notification_sent_at TEXT;

ALTER TABLE leads ADD COLUMN notification_error_code TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_leads_notification_status_created_at
  ON leads (notification_status, created_at DESC);
