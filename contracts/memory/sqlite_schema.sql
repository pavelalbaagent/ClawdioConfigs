PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  checksum TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'markdown',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL,
  chunk_order INTEGER NOT NULL,
  heading TEXT,
  content TEXT NOT NULL,
  token_estimate INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES source_documents(id) ON DELETE CASCADE,
  UNIQUE(source_id, chunk_order)
);

CREATE INDEX IF NOT EXISTS idx_memory_chunks_source_id ON memory_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_memory_chunks_content_hash ON memory_chunks(content_hash);

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  embedding_dim INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (chunk_id) REFERENCES memory_chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recall_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query_text TEXT NOT NULL,
  mode TEXT NOT NULL,
  top_k INTEGER NOT NULL,
  results_count INTEGER NOT NULL,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE VIEW IF NOT EXISTS v_memory_chunks AS
SELECT
  c.id AS chunk_id,
  s.path AS source_path,
  c.chunk_order,
  c.heading,
  c.content,
  c.token_estimate,
  e.provider,
  e.model,
  e.embedding_dim,
  c.created_at
FROM memory_chunks c
JOIN source_documents s ON s.id = c.source_id
LEFT JOIN embeddings e ON e.chunk_id = c.id;
