CREATE TABLE IF NOT EXISTS insightops_raw.uci_retail_line_raw (
  raw_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  batch_id CHAR(36) NOT NULL,
  source_row_number INT UNSIGNED NOT NULL,
  invoice_no VARCHAR(32) NOT NULL,
  stock_code VARCHAR(64) NOT NULL,
  description_text TEXT NULL,
  quantity INT NOT NULL,
  invoice_ts DATETIME NOT NULL,
  unit_price DECIMAL(18, 6) NOT NULL,
  customer_id VARCHAR(32) NULL,
  country_name VARCHAR(128) NOT NULL,
  ingested_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (raw_line_id),
  UNIQUE KEY uq_uci_raw_batch_row (batch_id, source_row_number),
  KEY idx_uci_raw_batch_invoice (batch_id, invoice_no),
  KEY idx_uci_raw_date (invoice_ts),
  CONSTRAINT fk_uci_raw_batch FOREIGN KEY (batch_id)
    REFERENCES insightops_ops.ingestion_batch (batch_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_dw.uci_retail_line_stg (
  stg_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  raw_line_id BIGINT UNSIGNED NOT NULL,
  batch_id CHAR(36) NOT NULL,
  quality_run_id CHAR(36) NOT NULL,
  invoice_no VARCHAR(32) NOT NULL,
  stock_code VARCHAR(64) NOT NULL,
  description_text TEXT NULL,
  quantity INT NOT NULL,
  invoice_ts DATETIME NOT NULL,
  unit_price DECIMAL(18, 6) NOT NULL,
  customer_id VARCHAR(32) NULL,
  country_name VARCHAR(128) NOT NULL,
  line_revenue DECIMAL(18, 6) NOT NULL,
  is_cancelled TINYINT(1) NOT NULL,
  is_exact_duplicate TINYINT(1) NOT NULL,
  is_valid_sale_line TINYINT(1) NOT NULL,
  is_customer_identified TINYINT(1) NOT NULL,
  staged_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (stg_line_id),
  UNIQUE KEY uq_uci_stg_raw (raw_line_id),
  KEY idx_uci_stg_batch_invoice (batch_id, invoice_no),
  KEY idx_uci_stg_valid_date (is_valid_sale_line, invoice_ts),
  CONSTRAINT fk_uci_stg_raw FOREIGN KEY (raw_line_id)
    REFERENCES insightops_raw.uci_retail_line_raw (raw_line_id),
  CONSTRAINT fk_uci_stg_quality FOREIGN KEY (quality_run_id)
    REFERENCES insightops_ops.data_quality_run (run_id)
) ENGINE=InnoDB;
