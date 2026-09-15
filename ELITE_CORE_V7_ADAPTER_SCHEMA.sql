-- Elite Core v7: trusted sport adapter publishing + notification delivery

CREATE TABLE IF NOT EXISTS sport_adapter_keys(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER NOT NULL,
  key_name TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_used_at TEXT,
  UNIQUE(sport_id,key_name)
);

CREATE TABLE IF NOT EXISTS sport_publications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sport_id INTEGER NOT NULL,
  publication_type TEXT NOT NULL,
  external_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed_at TEXT,
  status TEXT NOT NULL DEFAULT 'RECEIVED',
  error_text TEXT,
  UNIQUE(sport_id,publication_type,external_id)
);

CREATE TABLE IF NOT EXISTS notification_preferences(
  user_id INTEGER NOT NULL,
  sport_id INTEGER,
  preference_key TEXT NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(user_id,sport_id,preference_key)
);

CREATE TABLE IF NOT EXISTS notification_deliveries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notification_id INTEGER NOT NULL,
  channel TEXT NOT NULL DEFAULT 'IN_APP',
  delivery_status TEXT NOT NULL DEFAULT 'PENDING',
  attempted_at TEXT,
  delivered_at TEXT,
  error_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_publications_received
  ON sport_publications(sport_id,status,received_at);
