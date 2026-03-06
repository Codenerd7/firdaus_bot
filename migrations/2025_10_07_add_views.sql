-- Вью с суммой погашений и остатком по каждому займу
DROP VIEW IF EXISTS view_loans_with_repaid;
CREATE VIEW view_loans_with_repaid AS
SELECT
  l.id            AS loan_id,
  l.user_id       AS user_id,
  l.amount        AS loan_amount,
  COALESCE((SELECT SUM(r.amount) FROM transactions r WHERE r.type='repayment' AND r.related_loan_id=l.id),0) AS repaid_amount,
  (l.amount - COALESCE((SELECT SUM(r.amount) FROM transactions r WHERE r.type='repayment' AND r.related_loan_id=l.id),0)) AS remaining,
  COALESCE(l.status,'unpaid') AS status,
  l.created_at    AS loan_date
FROM transactions l
WHERE l.type='loan';

-- Только активные долги (остаток > 0)
DROP VIEW IF EXISTS view_active_loans;
CREATE VIEW view_active_loans AS
SELECT * FROM view_loans_with_repaid WHERE remaining > 0;

-- Долг по пользователю (сумма остатков)
DROP VIEW IF EXISTS view_debts_by_user;
CREATE VIEW view_debts_by_user AS
SELECT user_id, SUM(remaining) AS total_debt
FROM view_active_loans
GROUP BY user_id;

-- Сводка фонда
DROP VIEW IF EXISTS fund_overview_v;
CREATE VIEW fund_overview_v AS
SELECT
  COALESCE((SELECT SUM(amount) FROM transactions WHERE type='contribution'),0) AS total_contributions,
  COALESCE((SELECT SUM(amount) FROM transactions WHERE type='loan'),0)          AS total_loans,
  COALESCE((SELECT SUM(amount) FROM transactions WHERE type='repayment'),0)     AS total_repayments,
  COALESCE((SELECT SUM(amount) FROM transactions WHERE type='adjustment'),0)    AS total_adjustments,
  COALESCE((SELECT SUM(remaining) FROM view_active_loans),0)                    AS total_outstanding,
  (
    COALESCE((SELECT SUM(amount) FROM transactions WHERE type='contribution'),0)
    + COALESCE((SELECT SUM(amount) FROM transactions WHERE type='adjustment'),0)
    - COALESCE((SELECT SUM(remaining) FROM view_active_loans),0)
  ) AS free_funds;

-- Триггер: при каждом возврате автоматом закрывать займ, если выплачено достаточно
DROP TRIGGER IF EXISTS trg_close_loan_when_fully_paid;
CREATE TRIGGER trg_close_loan_when_fully_paid
AFTER INSERT ON transactions
WHEN NEW.type = 'repayment'
BEGIN
  UPDATE transactions
  SET status='paid'
  WHERE id = NEW.related_loan_id
    AND type='loan'
    AND (
      (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='repayment' AND related_loan_id = NEW.related_loan_id)
      >= (SELECT amount FROM transactions WHERE id = NEW.related_loan_id)
    );
END;
