CREATE TABLE IF NOT EXISTS gmail_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source_label TEXT,
  query_text TEXT,
  batch_limit INTEGER NOT NULL,
  dry_run INTEGER NOT NULL DEFAULT 1,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  skipped_existing_count INTEGER NOT NULL DEFAULT 0,
  processed_count INTEGER NOT NULL DEFAULT 0,
  applied_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS gmail_messages (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT,
  from_name TEXT,
  from_email TEXT,
  subject TEXT,
  snippet TEXT,
  excerpt TEXT,
  label_ids_json TEXT NOT NULL DEFAULT '[]',
  sender_type TEXT,
  intent_tags_json TEXT NOT NULL DEFAULT '[]',
  has_links INTEGER NOT NULL DEFAULT 0,
  has_attachments INTEGER NOT NULL DEFAULT 0,
  attachment_count INTEGER NOT NULL DEFAULT 0,
  raw_headers_json TEXT,
  message_ts TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_processed_at TEXT,
  last_action TEXT,
  last_action_applied INTEGER NOT NULL DEFAULT 0,
  action_reason TEXT,
  manual_review_required INTEGER NOT NULL DEFAULT 0,
  model_required INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gmail_attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  part_id TEXT,
  filename TEXT,
  mime_type TEXT,
  attachment_id TEXT,
  size_bytes INTEGER,
  stored_to_drive INTEGER NOT NULL DEFAULT 0,
  drive_file_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(message_id, part_id, filename, attachment_id)
);

CREATE TABLE IF NOT EXISTS gmail_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  message_id TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  primary_action TEXT NOT NULL,
  secondary_actions_json TEXT NOT NULL DEFAULT '[]',
  sender_type TEXT,
  intent_tags_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL,
  reason TEXT,
  manual_review_required INTEGER NOT NULL DEFAULT 0,
  model_required INTEGER NOT NULL DEFAULT 0,
  applied INTEGER NOT NULL DEFAULT 0,
  dry_run INTEGER NOT NULL DEFAULT 1,
  error_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_last_processed_at ON gmail_messages(last_processed_at);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_from_email ON gmail_messages(from_email);
CREATE INDEX IF NOT EXISTS idx_gmail_decisions_message_id ON gmail_decisions(message_id);
CREATE INDEX IF NOT EXISTS idx_gmail_decisions_run_id ON gmail_decisions(run_id);
