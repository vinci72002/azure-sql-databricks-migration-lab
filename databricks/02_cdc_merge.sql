-- Databricks SQL template. Precondition: CDC consumer has landed events into a
-- deduplicated, ordered staging table; source-specific LSN ordering is preserved.
-- Adapt metadata types and operation encoding to the actual CDC connector.
MERGE INTO migration_dev.silver.payments AS t
USING (
  SELECT payment_id, merchant_id, amount_cents, status, op, sequence_id
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY payment_id ORDER BY sequence_id DESC) rn
    FROM migration_dev.bronze.payment_changes
  ) WHERE rn = 1
) AS s
ON t.payment_id = s.payment_id
WHEN MATCHED AND s.sequence_id >= t.sequence_id AND s.op = 'DELETE' THEN DELETE
WHEN MATCHED AND s.sequence_id >= t.sequence_id AND s.op <> 'DELETE' THEN UPDATE SET
 t.merchant_id=s.merchant_id,t.amount_cents=s.amount_cents,t.status=s.status,t.sequence_id=s.sequence_id
WHEN NOT MATCHED AND s.op <> 'DELETE' THEN INSERT
 (payment_id,merchant_id,amount_cents,status,sequence_id)
 VALUES (s.payment_id,s.merchant_id,s.amount_cents,s.status,s.sequence_id);
-- NOTE: Production streaming CDC must handle out-of-order late events even after deletes:
-- retain tombstones/high watermarks and commit CDC offsets with sink transactions.
