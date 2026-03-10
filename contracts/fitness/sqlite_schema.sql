PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS programs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  start_date TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_days (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id INTEGER NOT NULL,
  day_index INTEGER NOT NULL,
  day_name TEXT NOT NULL,
  focus TEXT,
  is_rest_day INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
  UNIQUE(program_id, day_index)
);

CREATE TABLE IF NOT EXISTS exercises (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  muscle_group TEXT,
  equipment TEXT,
  movement_pattern TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS day_exercises (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  training_day_id INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL,
  slot_order INTEGER NOT NULL,
  target_rep_min INTEGER,
  target_rep_max INTEGER,
  target_sets INTEGER,
  progression_rule TEXT,
  set_style TEXT NOT NULL DEFAULT 'straight',
  superset_label TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (training_day_id) REFERENCES training_days(id) ON DELETE CASCADE,
  FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
  UNIQUE(training_day_id, slot_order)
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  program_id INTEGER NOT NULL,
  session_date TEXT NOT NULL,
  training_day_index INTEGER NOT NULL,
  training_day_code TEXT,
  status TEXT NOT NULL DEFAULT 'in_progress',
  bodyweight_kg REAL,
  readiness_score INTEGER,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS set_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL,
  set_order INTEGER NOT NULL,
  set_type TEXT NOT NULL DEFAULT 'straight',
  reps INTEGER,
  weight_kg REAL,
  weight_mode TEXT,
  rir REAL,
  rest_seconds INTEGER,
  myorep_cluster TEXT,
  superset_label TEXT,
  effort_note TEXT,
  raw_input_text TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
  UNIQUE(session_id, exercise_id, set_order)
);

CREATE TABLE IF NOT EXISTS runtime_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_set_logs_session ON set_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_day_exercises_day ON day_exercises(training_day_id);
