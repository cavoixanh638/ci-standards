-- Private D1 database only. Do not export repository inventories to GitHub.
CREATE TABLE IF NOT EXISTS webhook_deliveries (
  delivery_id TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  nonce TEXT NOT NULL,
  received_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS repositories (
  repo_id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('active','archived','inaccessible')),
  visibility TEXT NOT NULL CHECK(visibility IN ('public','private','unknown')),
  source TEXT NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS repo_state_index ON repositories(state);
