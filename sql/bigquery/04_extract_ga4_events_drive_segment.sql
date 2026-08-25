-- 目的：导出完整 GA4 公开样例的一个连续分段，供 Google Drive CSV 下载。
-- 使用方式：每次只修改 start_suffix/end_suffix；导出后将文件重命名为
-- ga4_ecommerce_events_YYYYMMDD_YYYYMMDD.csv。不要添加 event_params_json/items_json，
-- 否则可能超过无结算账号下的单文件导出限制。
DECLARE start_suffix STRING DEFAULT '20201101';
DECLARE end_suffix STRING DEFAULT '20201107';

SELECT
  PARSE_DATE('%Y%m%d', event_date) AS event_date,
  TIMESTAMP_MICROS(event_timestamp) AS event_ts,
  user_pseudo_id,
  event_name,
  CAST((
    SELECT value.int_value
    FROM UNNEST(event_params)
    WHERE key = 'ga_session_id'
  ) AS STRING) AS ga_session_id,
  (
    SELECT value.string_value
    FROM UNNEST(event_params)
    WHERE key = 'page_location'
  ) AS page_location,
  device.category AS device_category,
  geo.country AS country_name,
  COALESCE(traffic_source.source, 'unknown') AS first_acquisition_source_name,
  COALESCE(traffic_source.medium, 'unknown') AS first_acquisition_medium_name,
  ecommerce.transaction_id,
  ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN start_suffix AND end_suffix;
