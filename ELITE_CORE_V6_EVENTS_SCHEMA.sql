-- Elite Core v6: universal event cards
CREATE TABLE IF NOT EXISTS sport_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 sport_id INTEGER NOT NULL,
 external_event_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 title TEXT NOT NULL,
 subtitle TEXT,
 event_status TEXT NOT NULL DEFAULT 'UPCOMING',
 starts_at TEXT,
 ends_at TEXT,
 primary_label TEXT,
 secondary_label TEXT,
 detail_label TEXT,
 action_label TEXT NOT NULL DEFAULT 'Open Event',
 action_path TEXT,
 is_featured INTEGER NOT NULL DEFAULT 0,
 payload_json TEXT NOT NULL DEFAULT '{}',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(sport_id,external_event_id)
);
CREATE TABLE IF NOT EXISTS event_follows(
 user_id INTEGER NOT NULL,
 event_id INTEGER NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(user_id,event_id)
);
CREATE INDEX IF NOT EXISTS idx_sport_events_status_time ON sport_events(event_status,starts_at);
