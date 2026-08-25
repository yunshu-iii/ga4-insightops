-- 目的：导出连续 14 天的全部事件行，供 Google Drive CSV 下载使用。
-- 与 02_extract_ga4_events.sql 的区别：不导出 event_params_json 和 items_json
-- 两个大字段，以避免 Google Drive 的单文件 1 GB 限制。
-- 这不会筛掉任何事件行；仅不保留未展开的原始参数和商品数组。
DECLARE start_suffix STRING DEFAULT '20201101';
DECLARE end_suffix STRING DEFAULT '20201114';

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
