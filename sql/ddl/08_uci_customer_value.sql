-- 已有容器需要手动执行一次。客户价值事实只使用有客户 ID 的有效 UCI 订单。

CREATE TABLE IF NOT EXISTS insightops_mart.uci_customer_value_fact (
  uci_customer_value_fact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  snapshot_date DATE NOT NULL,
  customer_id VARCHAR(32) NOT NULL,
  country_name VARCHAR(128) NOT NULL,
  first_order_ts DATETIME NOT NULL,
  last_order_ts DATETIME NOT NULL,
  recency_days INT UNSIGNED NOT NULL,
  frequency_orders INT UNSIGNED NOT NULL,
  historical_value_gbp DECIMAL(20, 6) NOT NULL,
  average_order_value_gbp DECIMAL(20, 6) NOT NULL,
  is_repeat_customer TINYINT(1) NOT NULL,
  recency_score TINYINT UNSIGNED NOT NULL,
  frequency_score TINYINT UNSIGNED NOT NULL,
  monetary_score TINYINT UNSIGNED NOT NULL,
  rfm_segment VARCHAR(32) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (uci_customer_value_fact_id),
  UNIQUE KEY uq_uci_customer_value_version (
    source_batch_id, customer_id, definition_version, snapshot_date
  ),
  KEY idx_uci_customer_value_segment (rfm_segment),
  KEY idx_uci_customer_value_value (historical_value_gbp),
  CONSTRAINT fk_uci_customer_value_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_mart.uci_customer_value_summary (
  uci_customer_value_summary_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  snapshot_date DATE NOT NULL,
  valid_orders BIGINT UNSIGNED NOT NULL,
  identified_orders BIGINT UNSIGNED NOT NULL,
  identified_order_coverage DECIMAL(12, 8) NOT NULL,
  identified_customers BIGINT UNSIGNED NOT NULL,
  repeat_customers BIGINT UNSIGNED NOT NULL,
  historical_value_gbp DECIMAL(20, 6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (uci_customer_value_summary_id),
  UNIQUE KEY uq_uci_customer_value_summary_version (
    source_batch_id, definition_version, snapshot_date
  ),
  CONSTRAINT fk_uci_customer_value_summary_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;
