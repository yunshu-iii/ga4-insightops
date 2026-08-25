-- 说明：已有容器需要手动执行一次；后续质量检查写入 Ops 审计层。

CREATE TABLE IF NOT EXISTS insightops_ops.data_quality_run (
  run_id CHAR(36) NOT NULL,
  batch_id CHAR(36) NOT NULL,
  dataset_name VARCHAR(128) NOT NULL,
  rule_set_version VARCHAR(32) NOT NULL,
  status ENUM('RUNNING', 'SUCCEEDED', 'BLOCKED', 'FAILED') NOT NULL,
  total_rows BIGINT UNSIGNED NOT NULL DEFAULT 0,
  failed_rules INT UNSIGNED NOT NULL DEFAULT 0,
  blocker_failed_rules INT UNSIGNED NOT NULL DEFAULT 0,
  started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  finished_at DATETIME(6) NULL,
  error_message TEXT NULL,
  PRIMARY KEY (run_id),
  KEY idx_quality_run_batch_status (batch_id, status),
  CONSTRAINT fk_quality_run_batch
    FOREIGN KEY (batch_id) REFERENCES insightops_ops.ingestion_batch (batch_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_ops.data_quality_result (
  run_id CHAR(36) NOT NULL,
  rule_id VARCHAR(64) NOT NULL,
  severity ENUM('BLOCKER', 'WARNING') NOT NULL,
  failed_rows BIGINT UNSIGNED NOT NULL,
  failed_rate DECIMAL(12, 8) NOT NULL,
  outcome ENUM('PASSED', 'FAILED') NOT NULL,
  checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, rule_id),
  CONSTRAINT fk_quality_result_run
    FOREIGN KEY (run_id) REFERENCES insightops_ops.data_quality_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insightops_ops.data_quality_reject (
  reject_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id CHAR(36) NOT NULL,
  batch_id CHAR(36) NOT NULL,
  source_table VARCHAR(128) NOT NULL,
  source_row_number INT UNSIGNED NOT NULL,
  rule_id VARCHAR(64) NOT NULL,
  severity ENUM('BLOCKER', 'WARNING') NOT NULL,
  rejected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (reject_id),
  UNIQUE KEY uq_quality_reject_run_rule_row (run_id, rule_id, source_row_number),
  KEY idx_quality_reject_batch_rule (batch_id, rule_id),
  CONSTRAINT fk_quality_reject_run
    FOREIGN KEY (run_id) REFERENCES insightops_ops.data_quality_run (run_id)
) ENGINE=InnoDB;
