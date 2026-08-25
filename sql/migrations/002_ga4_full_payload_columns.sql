-- Apply once to an existing InsightOps MySQL database.
-- Fresh databases receive the same columns from sql/ddl/02_raw_tables.sql.
-- This server does not support ALTER TABLE ... ADD COLUMN IF NOT EXISTS, so each
-- statement checks information_schema first and remains safe to rerun.

SET @target_schema = 'insightops_raw';
SET @target_table = 'ga4_event_raw';
SET @target_column = 'event_params_json';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_raw.ga4_event_raw ADD COLUMN event_params_json JSON NULL AFTER purchase_revenue_usd',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @target_column = 'items_json';
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE insightops_raw.ga4_event_raw ADD COLUMN items_json JSON NULL AFTER event_params_json',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = @target_schema AND table_name = @target_table AND column_name = @target_column
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
