-- 说明：首次容器初始化会自动执行此文件；已有容器需手动执行一次。

CREATE TABLE IF NOT EXISTS insightops_ops.ingestion_batch (
  batch_id CHAR(36) NOT NULL,
  source_system VARCHAR(32) NOT NULL,
  source_file VARCHAR(512) NOT NULL,
  source_sha256 CHAR(64) NOT NULL,
  extract_start_date DATE NULL,
  extract_end_date DATE NULL,
  status ENUM('RUNNING', 'SUCCEEDED', 'FAILED') NOT NULL,
  rows_loaded BIGINT UNSIGNED NOT NULL DEFAULT 0,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  finished_at DATETIME(6) NULL,
  error_message TEXT NULL,
  PRIMARY KEY (batch_id),
  KEY idx_ingestion_batch_status_started (status, started_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_raw.ga4_event_raw (
  raw_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  batch_id CHAR(36) NOT NULL,
  source_row_number INT UNSIGNED NOT NULL,
  event_date DATE NOT NULL,
  event_ts DATETIME(6) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  event_name VARCHAR(128) NOT NULL,
  ga_session_id VARCHAR(64) NOT NULL,
  page_location TEXT NOT NULL,
  device_category VARCHAR(32) NOT NULL,
  country_name VARCHAR(128) NOT NULL,
  first_acquisition_source_name VARCHAR(256) NOT NULL,
  first_acquisition_medium_name VARCHAR(128) NOT NULL,
  transaction_id VARCHAR(128) NULL,
  purchase_revenue_usd DECIMAL(18, 6) NULL,
  event_params_json JSON NULL,
  items_json JSON NULL,
  ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (raw_event_id),
  UNIQUE KEY uq_ga4_event_raw_batch_row (batch_id, source_row_number),
  KEY idx_ga4_event_raw_batch (batch_id),
  KEY idx_ga4_event_raw_date_event (event_date, event_name),
  KEY idx_ga4_event_raw_user_session (user_pseudo_id, ga_session_id),
  CONSTRAINT fk_ga4_event_raw_batch
    FOREIGN KEY (batch_id) REFERENCES insightops_ops.ingestion_batch (batch_id)
) ENGINE=InnoDB;
