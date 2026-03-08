CREATE TABLE IF NOT EXISTS braindump_items (
  id TEXT PRIMARY KEY,
  short_text TEXT NOT NULL,
  category TEXT NOT NULL,
  tags_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'inbox',
  review_bucket TEXT NOT NULL DEFAULT 'weekly',
  source TEXT NOT NULL DEFAULT 'agent_channel',
  captured_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_reviewed_at TEXT,
  next_review_at TEXT,
  promoted_to_type TEXT,
  promoted_to_id TEXT,
  archived_at TEXT,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS braindump_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  action TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  next_review_at TEXT,
  FOREIGN KEY (item_id) REFERENCES braindump_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS braindump_category_defaults (
  category TEXT PRIMARY KEY,
  review_bucket TEXT NOT NULL,
  default_tags_json TEXT NOT NULL DEFAULT '[]',
  auto_archive_days INTEGER,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_braindump_items_status ON braindump_items(status);
CREATE INDEX IF NOT EXISTS idx_braindump_items_category ON braindump_items(category);
CREATE INDEX IF NOT EXISTS idx_braindump_items_next_review_at ON braindump_items(next_review_at);
CREATE INDEX IF NOT EXISTS idx_braindump_reviews_item_id ON braindump_reviews(item_id);
