DROP INDEX IF EXISTS idx_leads_notification_status_created_at;

ALTER TABLE leads DROP COLUMN notification_status;
ALTER TABLE leads DROP COLUMN notification_sent_at;
ALTER TABLE leads DROP COLUMN notification_error_code;
