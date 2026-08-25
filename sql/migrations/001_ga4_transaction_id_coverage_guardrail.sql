-- Apply once to an existing InsightOps MySQL database.
-- Fresh databases receive the same columns from sql/ddl/09_daily_metrics_anomalies.sql.
-- This server does not support ALTER TABLE ... ADD COLUMN IF NOT EXISTS, so each
-- statement checks information_schema first and remains safe to rerun.

SET @target_schema = 'insightops_mart';
SET @target_table = 'ga4_daily_metric';
SET @target_column = 'purchase_events';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_mart.ga4_daily_metric ADD COLUMN purchase_events BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER checkout_to_canonical_order_rate',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @target_column = 'valid_transaction_id_purchase_events';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_mart.ga4_daily_metric ADD COLUMN valid_transaction_id_purchase_events BIGINT UNSIGNED NOT NULL DEFAULT 0 AFTER purchase_events',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @target_column = 'valid_transaction_id_coverage';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_mart.ga4_daily_metric ADD COLUMN valid_transaction_id_coverage DECIMAL(12, 8) NULL AFTER valid_transaction_id_purchase_events',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @target_schema = 'insightops_ops';
SET @target_table = 'metric_anomaly_result';
SET @target_column = 'is_business_interpretable';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_ops.metric_anomaly_result ADD COLUMN is_business_interpretable TINYINT(1) NOT NULL DEFAULT 1 AFTER status',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @target_column = 'interpretation_note';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_ops.metric_anomaly_result ADD COLUMN interpretation_note VARCHAR(512) NULL AFTER is_business_interpretable',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
