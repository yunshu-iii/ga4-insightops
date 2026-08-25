-- GA4 Raw 质量规则的可审计 SQL 说明。
-- 实际执行与结果写入由 src/run_ga4_quality.py 完成。
-- 指定批次：SET @batch_id = '9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27';

-- 规则示例：事件日期必须处于 ingestion_batch 登记的提取范围内。
SELECT COUNT(*) AS failed_rows
FROM insightops_raw.ga4_event_raw AS raw
JOIN insightops_ops.ingestion_batch AS batch ON batch.batch_id = raw.batch_id
WHERE raw.batch_id = @batch_id
  AND (raw.event_date < batch.extract_start_date OR raw.event_date > batch.extract_end_date);

-- 规则示例：购买收入只能出现在 purchase 事件上，且不得为负数。
SELECT COUNT(*) AS failed_rows
FROM insightops_raw.ga4_event_raw
WHERE batch_id = @batch_id
  AND (purchase_revenue_usd < 0
       OR (purchase_revenue_usd IS NOT NULL AND event_name <> 'purchase'));
