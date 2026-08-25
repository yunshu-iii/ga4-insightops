-- Existing databases use sql/migrations/003_ga4_json_derivative_tables.sql once.
-- Each table has one independent array grain and never joins items to event parameters.

CREATE TABLE IF NOT EXISTS insightops_dw.ga4_item_event_stg (
  item_event_stg_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_event_id BIGINT UNSIGNED NOT NULL,
  batch_id CHAR(36) NOT NULL,
  source_quality_run_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  event_date DATE NOT NULL,
  event_name VARCHAR(128) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  ga_session_id VARCHAR(64) NOT NULL,
  transaction_id VARCHAR(128) NULL,
  device_category VARCHAR(32) NOT NULL,
  item_index INT UNSIGNED NOT NULL,
  item_id VARCHAR(256) NULL,
  item_name VARCHAR(512) NULL,
  item_brand VARCHAR(256) NULL,
  item_category VARCHAR(256) NULL,
  item_category2 VARCHAR(256) NULL,
  item_category3 VARCHAR(256) NULL,
  item_variant VARCHAR(256) NULL,
  item_list_id VARCHAR(256) NULL,
  item_list_name VARCHAR(512) NULL,
  item_list_index VARCHAR(256) NULL,
  promotion_id VARCHAR(256) NULL,
  promotion_name VARCHAR(512) NULL,
  coupon VARCHAR(256) NULL,
  item_quantity DECIMAL(18, 6) NULL,
  item_price_usd DECIMAL(18, 6) NULL,
  item_revenue_usd DECIMAL(18, 6) NULL,
  staged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (item_event_stg_id),
  UNIQUE KEY uq_ga4_item_event_version (batch_id, raw_event_id, item_index, definition_version),
  KEY idx_ga4_item_event_batch_date (batch_id, event_date),
  KEY idx_ga4_item_event_item (item_id, item_name),
  KEY idx_ga4_item_event_transaction (transaction_id),
  CONSTRAINT fk_ga4_item_event_raw
    FOREIGN KEY (raw_event_id) REFERENCES insightops_raw.ga4_event_raw (raw_event_id),
  CONSTRAINT fk_ga4_item_event_quality
    FOREIGN KEY (source_quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id),
  CONSTRAINT fk_ga4_item_event_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_dw.ga4_event_param_stg (
  event_param_stg_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_event_id BIGINT UNSIGNED NOT NULL,
  batch_id CHAR(36) NOT NULL,
  source_quality_run_id CHAR(36) NOT NULL,
  build_run_id CHAR(36) NOT NULL,
  definition_version VARCHAR(32) NOT NULL,
  event_date DATE NOT NULL,
  event_name VARCHAR(128) NOT NULL,
  user_pseudo_id VARCHAR(128) NOT NULL,
  ga_session_id VARCHAR(64) NOT NULL,
  parameter_name VARCHAR(128) NOT NULL,
  value_string VARCHAR(2048) NULL,
  value_int BIGINT NULL,
  value_float DOUBLE NULL,
  value_double DOUBLE NULL,
  value_kind ENUM('string', 'int', 'float', 'double', 'null') NOT NULL,
  staged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (event_param_stg_id),
  UNIQUE KEY uq_ga4_event_param_version (batch_id, raw_event_id, parameter_name, definition_version),
  KEY idx_ga4_event_param_batch_name (batch_id, parameter_name),
  KEY idx_ga4_event_param_date_event (event_date, event_name),
  CONSTRAINT fk_ga4_event_param_raw
    FOREIGN KEY (raw_event_id) REFERENCES insightops_raw.ga4_event_raw (raw_event_id),
  CONSTRAINT fk_ga4_event_param_quality
    FOREIGN KEY (source_quality_run_id) REFERENCES insightops_ops.data_quality_run (run_id),
  CONSTRAINT fk_ga4_event_param_build
    FOREIGN KEY (build_run_id) REFERENCES insightops_ops.transformation_run (run_id)
) ENGINE=InnoDB;
