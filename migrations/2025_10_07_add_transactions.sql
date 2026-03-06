-- Таблица транзакций (обновлённая)
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('contribution','loan','repayment','adjustment')),
    amount INTEGER NOT NULL,
    receipt_last4 TEXT,         -- последние 4 цифры квитанции (для взносов)
    status TEXT DEFAULT NULL,   -- для займов: 'paid' или 'unpaid'
    related_loan_id INTEGER,    -- связь возврата с займом (если нужно)
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);

-- ALTER для уже существующей таблицы (выполнять по необходимости):
-- ALTER TABLE transactions ADD COLUMN receipt_last4 TEXT;
-- ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT NULL;
-- ALTER TABLE transactions ADD COLUMN related_loan_id INTEGER;

-- Тестовые данные (по желанию):
-- INSERT INTO transactions(user_id, type, amount, receipt_last4, created_at) VALUES
-- (12345,'contribution',15000,'8421',datetime('now','-1 day')),
-- (12345,'contribution',10000,'7310',datetime('now','-10 day'));
-- INSERT INTO transactions(user_id, type, amount, status) VALUES
-- (12345,'loan',30000,'unpaid');
-- INSERT INTO transactions(user_id, type, amount, related_loan_id) VALUES
-- (12345,'repayment',5000, (SELECT id FROM transactions WHERE user_id=12345 AND type='loan' ORDER BY id DESC LIMIT 1));
