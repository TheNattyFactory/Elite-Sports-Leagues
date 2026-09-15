-- Optional EBL-side audit table for Elite account linkage.
-- Core remains the canonical store for the link.
CREATE TABLE IF NOT EXISTS elite_link_audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ebl_user_id INTEGER NOT NULL,
  elite_user_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_elite_link_audit_user
ON elite_link_audit(ebl_user_id,created_at DESC);
