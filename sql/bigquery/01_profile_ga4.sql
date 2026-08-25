-- 目的：确认 GA4 公开样例的事件、用户和日期覆盖。
-- 运行前：在 BigQuery Console 中选择你的 Google Cloud 项目。
SELECT
  COUNT(*) AS event_count,
  COUNT(DISTINCT user_pseudo_id) AS user_count,
  COUNT(DISTINCT event_date) AS day_count,
  MIN(PARSE_DATE('%Y%m%d', event_date)) AS first_event_date,
  MAX(PARSE_DATE('%Y%m%d', event_date)) AS last_event_date
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`;
