-- 已有容器需要手动执行一次。会话与漏斗事实只从通过质量门禁的 GA4 Staging 构建。

CREATE TABLE IF NOT EXISTS insightops_mart.ga4_session_fact (
  ga4_session_fact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  source_quality_run_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  ga_session_id VARCHAR(64) NOT NULL,
  session_start_ts DATETIME(6) NOT NULL,
  session_end_ts DATETIME(6) NOT NULL,
  session_date DATE NOT NULL,
  landing_page_path VARCHAR(2048) NOT NULL,
  device_category VARCHAR(32) NOT NULL,
  country_name VARCHAR(128) NOT NULL,
  first_acquisition_source_name VARCHAR(256) NOT NULL,
  first_acquisition_medium_name VARCHAR(128) NOT NULL,
  event_count INT UNSIGNED NOT NULL,
  page_view_count INT UNSIGNED NOT NULL,
  has_session_start TINYINT(1) NOT NULL,
  has_view_item TINYINT(1) NOT NULL,
  has_add_to_cart TINYINT(1) NOT NULL,
  has_begin_checkout TINYINT(1) NOT NULL,
  has_purchase_event TINYINT(1) NOT NULL,
  has_checkout_to_purchase_event TINYINT(1) NOT NULL,
  has_canonical_order TINYINT(1) NOT NULL,
  has_checkout_to_canonical_order TINYINT(1) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (ga4_session_fact_id),
  UNIQUE KEY uq_ga4_session_fact_version (
    source_batch_id, user_pseudo_id, ga_session_id, definition_version
  ),
  KEY idx_ga4_session_fact_date (session_date),
  KEY idx_ga4_session_fact_checkout (has_begin_checkout, has_checkout_to_canonical_order),
  CONSTRAINT fk_ga4_session_fact_quality
    FOREIGN KEY (source_quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id),
  CONSTRAINT fk_ga4_session_fact_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_mart.ga4_daily_funnel_metric (
  ga4_daily_funnel_metric_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  metric_date DATE NOT NULL,
  observed_sessions BIGINT UNSIGNED NOT NULL,
  sessions_with_session_start BIGINT UNSIGNED NOT NULL,
  product_view_sessions BIGINT UNSIGNED NOT NULL,
  add_to_cart_sessions BIGINT UNSIGNED NOT NULL,
  checkout_start_sessions BIGINT UNSIGNED NOT NULL,
  checkout_to_purchase_event_sessions BIGINT UNSIGNED NOT NULL,
  checkout_to_canonical_order_sessions BIGINT UNSIGNED NOT NULL,
  checkout_to_purchase_event_rate DECIMAL(12, 8) NULL,
  checkout_to_canonical_order_rate DECIMAL(12, 8) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (ga4_daily_funnel_metric_id),
  UNIQUE KEY uq_ga4_daily_funnel_version (source_batch_id, metric_date, definition_version),
  KEY idx_ga4_daily_funnel_date (metric_date),
  CONSTRAINT fk_ga4_daily_funnel_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;
