-- Elite Core v2 Career Passport extension

CREATE TABLE IF NOT EXISTS career_passports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  sport_id INTEGER NOT NULL,
  external_career_id TEXT,
  athlete_name TEXT NOT NULL,
  organization_name TEXT,
  role_name TEXT,
  current_season TEXT,
  career_status TEXT NOT NULL DEFAULT 'ACTIVE',
  headline TEXT,
  profile_path TEXT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  retired_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id,sport_id,external_career_id)
);

CREATE TABLE IF NOT EXISTS passport_stats(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  passport_id INTEGER NOT NULL,
  stat_key TEXT NOT NULL,
  stat_label TEXT NOT NULL,
  stat_value TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 100,
  UNIQUE(passport_id,stat_key)
);

CREATE TABLE IF NOT EXISTS honors(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  sport_id INTEGER NOT NULL,
  passport_id INTEGER,
  external_honor_id TEXT,
  honor_type TEXT NOT NULL,
  title TEXT NOT NULL,
  season_label TEXT,
  event_label TEXT,
  awarded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_major INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(sport_id,external_honor_id)
);

CREATE TABLE IF NOT EXISTS sport_health(
  sport_id INTEGER PRIMARY KEY,
  service_status TEXT NOT NULL DEFAULT 'UNKNOWN',
  message TEXT,
  checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
