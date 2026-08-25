CREATE TABLE IF NOT EXISTS insightops_mart.ga4_daily_metric (
  ga4_daily_metric_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  metric_date DATE NOT NULL,
  observed_sessions BIGINT UNSIGNED NOT NULL,
  checkout_start_sessions BIGINT UNSIGNED NOT NULL,
  canonical_order_sessions BIGINT UNSIGNED NOT NULL,
  canonical_orders BIGINT UNSIGNED NOT NULL,
  canonical_revenue_usd DECIMAL(20, 6) NOT NULL,
  checkout_to_canonical_order_rate DECIMAL(12, 8) NULL,
  purchase_events BIGINT UNSIGNED NOT NULL DEFAULT 0,
  valid_transaction_id_purchase_events BIGINT UNSIGNED NOT NULL DEFAULT 0,
  valid_transaction_id_coverage DECIMAL(12, 8) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (ga4_daily_metric_id),
  UNIQUE KEY uq_ga4_daily_metric_version (source_batch_id, metric_date, definition_version),
  KEY idx_ga4_daily_metric_date (metric_date),
  CONSTRAINT fk_ga4_daily_metric_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_mart.ga4_daily_dimension_metric (
  ga4_daily_dimension_metric_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  metric_date DATE NOT NULL,
  dimension_name VARCHAR(64) NOT NULL,
  dimension_value VARCHAR(512) NOT NULL,
  observed_sessions BIGINT UNSIGNED NOT NULL,
  checkout_start_sessions BIGINT UNSIGNED NOT NULL,
  canonical_order_sessions BIGINT UNSIGNED NOT NULL,
  canonical_orders BIGINT UNSIGNED NOT NULL,
  canonical_revenue_usd DECIMAL(20, 6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (ga4_daily_dimension_metric_id),
  UNIQUE KEY uq_ga4_daily_dimension_metric_version (
    source_batch_id, metric_date, dimension_name, dimension_value, definition_version
  ),
  KEY idx_ga4_daily_dimension_metric_date_dimension (metric_date, dimension_name),
  CONSTRAINT fk_ga4_daily_dimension_metric_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_ops.metric_anomaly_result (
  anomaly_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id CHAR(36) NOT NULL,
  source_batch_id CHAR(36) NOT NULL,
  metric_id VARCHAR(128) NOT NULL,
  metric_date DATE NOT NULL,
  metric_value DECIMAL(24, 8) NOT NULL,
  baseline_points INT UNSIGNED NOT NULL,
  baseline_median DECIMAL(24, 8) NULL,
  baseline_mad DECIMAL(24, 8) NULL,
  robust_z_score DECIMAL(24, 8) NULL,
  status ENUM('INSUFFICIENT_HISTORY', 'NORMAL', 'ANOMALY_HIGH', 'ANOMALY_LOW') NOT NULL,
  is_business_interpretable TINYINT(1) NOT NULL DEFAULT 1,
  interpretation_note VARCHAR(512) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (anomaly_id),
  UNIQUE KEY uq_metric_anomaly_run_metric_date (run_id, metric_id, metric_date),
  KEY idx_metric_anomaly_status_date (status, metric_date),
  CONSTRAINT fk_metric_anomaly_run
    FOREIGN KEY (run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_ops.metric_anomaly_contribution (
  contribution_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  anomaly_id BIGINT UNSIGNED NOT NULL,
  dimension_name VARCHAR(64) NOT NULL,
  dimension_value VARCHAR(512) NOT NULL,
  current_value DECIMAL(24, 8) NOT NULL,
  baseline_median DECIMAL(24, 8) NOT NULL,
  contribution_delta DECIMAL(24, 8) NOT NULL,
  total_delta DECIMAL(24, 8) NOT NULL,
  contribution_share DECIMAL(24, 8) NULL,
  contribution_rank INT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (contribution_id),
  UNIQUE KEY uq_metric_contribution_anomaly_dimension (
    anomaly_id, dimension_name, dimension_value
  ),
  KEY idx_metric_contribution_rank (anomaly_id, contribution_rank),
  CONSTRAINT fk_metric_contribution_anomaly
    FOREIGN KEY (anomaly_id) REFERENCES insightops_ops.metric_anomaly_result (anomaly_id)
) ENGINE=InnoDB;
