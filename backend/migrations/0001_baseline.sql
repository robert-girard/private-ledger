CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT,
  password_salt TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_users_email ON users (email);

CREATE TABLE refresh_token_blocklist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_id TEXT NOT NULL UNIQUE,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  revoked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL
);

CREATE INDEX ix_refresh_token_blocklist_token_id ON refresh_token_blocklist (token_id);

CREATE TABLE merchants (
  id TEXT PRIMARY KEY,
  raw_name TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  category TEXT,
  status TEXT NOT NULL DEFAULT 'unreviewed',
  is_transfer INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_merchants_raw_name ON merchants (raw_name);

CREATE TABLE merchant_aliases (
  id TEXT PRIMARY KEY,
  merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  alias TEXT NOT NULL UNIQUE,
  normalized_alias TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_merchant_aliases_alias ON merchant_aliases (alias);
CREATE INDEX ix_merchant_aliases_normalized_alias ON merchant_aliases (normalized_alias);

CREATE TABLE imports (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_filename TEXT NOT NULL,
  source_bank TEXT,
  import_status TEXT NOT NULL DEFAULT 'pending',
  imported_at TEXT,
  row_count INTEGER NOT NULL DEFAULT 0,
  stored_path TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_imports_user_id ON imports (user_id);

CREATE TABLE transactions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  import_id TEXT REFERENCES imports(id) ON DELETE SET NULL,
  merchant_id TEXT REFERENCES merchants(id) ON DELETE SET NULL,
  posted_on TEXT NOT NULL,
  description TEXT NOT NULL,
  normalized_description TEXT NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CAD',
  category TEXT,
  notes TEXT,
  dedupe_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_transactions_user_id ON transactions (user_id);
CREATE INDEX ix_transactions_import_id ON transactions (import_id);
CREATE INDEX ix_transactions_merchant_id ON transactions (merchant_id);
CREATE INDEX ix_transactions_posted_on ON transactions (posted_on);
CREATE INDEX ix_transactions_normalized_description ON transactions (normalized_description);
CREATE INDEX ix_transactions_dedupe_hash ON transactions (dedupe_hash);

CREATE TABLE subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  merchant_id TEXT REFERENCES merchants(id) ON DELETE SET NULL,
  display_name TEXT NOT NULL,
  category TEXT,
  interval TEXT NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  last_charged_on TEXT,
  next_expected_on TEXT,
  recent_match_transaction_id TEXT REFERENCES transactions(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX ix_subscriptions_merchant_id ON subscriptions (merchant_id);

CREATE TABLE budgets (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  month_start TEXT NOT NULL,
  category TEXT NOT NULL,
  planned_amount NUMERIC(12, 2) NOT NULL,
  spent_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_budgets_user_id ON budgets (user_id);
CREATE INDEX ix_budgets_month_start ON budgets (month_start);
