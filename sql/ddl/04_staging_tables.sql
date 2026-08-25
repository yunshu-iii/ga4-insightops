-- 已有容器需要手动执行一次。Staging 只接收通过当前质量门禁的 Raw 记录。

CREATE TABLE IF NOT EXISTS insightops_dw.ga4_event_stg (
  stg_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_event_id BIGINT UNSIGNED NOT NULL,
  batch_id CHAR(36) NOT NULL,
  quality_run_id CHAR(36) NOT NULL,
  event_date DATE NOT NULL,
  event_ts DATETIME(6) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  event_name VARCHAR(128) NOT NULL,
  ga_session_id VARCHAR(64) NOT NULL,
  page_location TEXT NOT NULL,
  page_path VARCHAR(2048) NOT NULL,
  device_category VARCHAR(32) NOT NULL,
  country_name VARCHAR(128) NOT NULL,
  first_acquisition_source_name VARCHAR(256) NOT NULL,
  first_acquisition_medium_name VARCHAR(128) NOT NULL,
  transaction_id VARCHAR(128) NULL,
  purchase_revenue_usd DECIMAL(18, 6) NULL,
  is_purchase TINYINT(1) NOT NULL,
  is_order_eligible TINYINT(1) NOT NULL,
  staged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (stg_event_id),
  UNIQUE KEY uq_ga4_event_stg_raw_event (raw_event_id),
  KEY idx_ga4_event_stg_batch_date_event (batch_id, event_date, event_name),
  KEY idx_ga4_event_stg_user_session (user_pseudo_id, ga_session_id),
  KEY idx_ga4_event_stg_order (transaction_id, is_order_eligible),
  CONSTRAINT fk_ga4_event_stg_raw
    FOREIGN KEY (raw_event_id) REFERENCES insightops_raw.ga4_event_raw (raw_event_id),
  CONSTRAINT fk_ga4_event_stg_quality_run
    FOREIGN KEY (quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id)
) ENGINE=InnoDB;
