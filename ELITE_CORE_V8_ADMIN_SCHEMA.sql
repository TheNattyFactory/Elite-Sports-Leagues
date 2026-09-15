-- Elite Core v8: master administration & operations

CREATE TABLE IF NOT EXISTS core_announcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'INFO',
  audience TEXT NOT NULL DEFAULT 'ALL',
  sport_id INTEGER,
  starts_at TEXT,
  ends_at TEXT,
  created_by_user_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS system_audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER,
  actor_type TEXT NOT NULL DEFAULT 'USER',
  action_type TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  sport_id INTEGER,
  summary TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_roles(
  user_id INTEGER NOT NULL,
  role_key TEXT NOT NULL,
  scope_sport_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id,role_key,scope_sport_id)
);

CREATE TABLE IF NOT EXISTS incident_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER,
  incident_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'LOW',
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN',
  opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TEXT,
  resolution_notes TEXT
);

CREATE TABLE IF NOT EXISTS service_checks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER,
  service_key TEXT NOT NULL,
  status TEXT NOT NULL,
  latency_ms INTEGER,
  message TEXT,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON system_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incident_status ON incident_log(status,severity,opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_checks ON service_checks(service_key,checked_at DESC);
