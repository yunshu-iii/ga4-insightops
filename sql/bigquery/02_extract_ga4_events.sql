-- 目的：导出连续 14 天开发样本。导出前可调整日期参数。
-- 注意：这里按日期筛选，适合接入和漏斗开发；最终作品集改用按 user_pseudo_id 的稳定抽样。
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
  -- 该 2020 年公开样例没有 collected_traffic_source；这里是用户首次获得来源，
  -- 不是当前会话的最后点击归因。
  COALESCE(traffic_source.source, 'unknown') AS first_acquisition_source_name,
  COALESCE(traffic_source.medium, 'unknown') AS first_acquisition_medium_name,
  ecommerce.transaction_id,
  ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd,
  TO_JSON_STRING(event_params) AS event_params_json,
  TO_JSON_STRING(items) AS items_json
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN start_suffix AND end_suffix;
