-- Run matching logic on the source SQL database separately and compare with target
-- at a common consistent CDC watermark (not live moving tables).
SELECT COUNT(*) AS row_count,
       SUM(amount_cents) AS amount_cents,
       COUNT(DISTINCT payment_id) AS distinct_payment_ids
FROM migration_dev.silver.payments;

-- Check key uniqueness (should return 0 rows)
SELECT payment_id, COUNT(*) AS n
FROM migration_dev.silver.payments
GROUP BY payment_id HAVING COUNT(*) > 1;

-- Sample by merchant to localize mismatches
SELECT merchant_id, COUNT(*) AS n, SUM(amount_cents) AS amount_cents
FROM migration_dev.silver.payments
GROUP BY merchant_id;
