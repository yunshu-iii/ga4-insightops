-- 已有容器需要手动执行一次。订单事实只从通过质量门禁的 Staging 构建。

CREATE TABLE IF NOT EXISTS insightops_ops.transformation_run (
  run_id CHAR(36) NOT NULL,
  job_name VARCHAR(128) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  status ENUM('RUNNING', 'SUCCEEDED', 'FAILED') NOT NULL,
  input_description JSON NOT NULL,
  rows_written BIGINT UNSIGNED NOT NULL DEFAULT 0,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  finished_at DATETIME(6) NULL,
  error_message TEXT NULL,
  PRIMARY KEY (run_id),
  KEY idx_transformation_run_job_status (job_name, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_mart.uci_order_fact (
  uci_order_fact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  source_quality_run_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  invoice_no VARCHAR(32) NOT NULL,
  order_ts DATETIME NOT NULL,
  customer_id VARCHAR(32) NULL,
  country_name VARCHAR(128) NOT NULL,
  valid_line_count INT UNSIGNED NOT NULL,
  total_quantity BIGINT NOT NULL,
  gmv_gbp DECIMAL(20, 6) NOT NULL,
  is_customer_identified TINYINT(1) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (uci_order_fact_id),
  UNIQUE KEY uq_uci_order_fact_version (source_batch_id, invoice_no, definition_version),
  KEY idx_uci_order_fact_customer (customer_id, order_ts),
  KEY idx_uci_order_fact_date (order_ts),
  CONSTRAINT fk_uci_order_fact_quality
    FOREIGN KEY (source_quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id),
  CONSTRAINT fk_uci_order_fact_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_mart.ga4_order_fact (
  ga4_order_fact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_batch_id CHAR(36) NOT NULL,
  source_quality_run_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  transaction_id VARCHAR(128) NOT NULL,
  order_ts DATETIME(6) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  country_name VARCHAR(128) NOT NULL,
  device_category VARCHAR(32) NOT NULL,
  first_acquisition_source_name VARCHAR(256) NOT NULL,
  first_acquisition_medium_name VARCHAR(128) NOT NULL,
  purchase_event_count INT UNSIGNED NOT NULL,
  revenue_usd DECIMAL(20, 6) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (ga4_order_fact_id),
  UNIQUE KEY uq_ga4_order_fact_version (source_batch_id, transaction_id, definition_version),
  KEY idx_ga4_order_fact_date (order_ts),
  KEY idx_ga4_order_fact_user (user_pseudo_id, order_ts),
  KEY idx_ga4_order_fact_acquisition (first_acquisition_source_name, first_acquisition_medium_name),
  CONSTRAINT fk_ga4_order_fact_quality
    FOREIGN KEY (source_quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id),
  CONSTRAINT fk_ga4_order_fact_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_ops.fact_build_audit (
  audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id CHAR(36) NOT NULL,
  source_name VARCHAR(32) NOT NULL,
  source_batch_id CHAR(36) NOT NULL,
  input_rows BIGINT UNSIGNED NOT NULL,
  excluded_rows BIGINT UNSIGNED NOT NULL DEFAULT 0,
  output_rows BIGINT UNSIGNED NOT NULL,
  notes VARCHAR(1024) NOT NULL,
  recorded_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (audit_id),
  UNIQUE KEY uq_fact_build_audit_run_source (run_id, source_name),
  CONSTRAINT fk_fact_build_audit_run
    FOREIGN KEY (run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;
