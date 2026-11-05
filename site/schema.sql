-- One row per character. Apply with: npx wrangler d1 execute nickhub --remote --file schema.sql
CREATE TABLE IF NOT EXISTS chars (
  key        TEXT PRIMARY KEY,  -- "<realm>-<name>"
  summary    TEXT NOT NULL,     -- JSON: the leaderboard's small summary
  line       TEXT NOT NULL,     -- JSON: [[level, unix time], ...] for the race chart
  log        BLOB NOT NULL,     -- gzipped JSON: the full log (rows are capped at 2 MB)
  updated_at INTEGER NOT NULL   -- the addon's updatedAt, so an older snapshot never wins
);
