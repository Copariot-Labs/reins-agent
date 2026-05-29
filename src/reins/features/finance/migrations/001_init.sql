CREATE TABLE IF NOT EXISTS finance_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
  amount REAL NOT NULL CHECK (amount > 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  category TEXT NOT NULL DEFAULT '其他',
  description TEXT NOT NULL,
  counterparty TEXT,
  payment_method TEXT,
  occurred_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  raw_text TEXT,
  status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'voided'))
);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_occurred_at
ON finance_transactions (occurred_at);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_type
ON finance_transactions (type);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_category
ON finance_transactions (category);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_status
ON finance_transactions (status);