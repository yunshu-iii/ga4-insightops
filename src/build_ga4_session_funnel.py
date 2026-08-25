"""Build GA4 session and daily checkout-funnel facts from approved Staging events."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import pymysql
from dotenv import load_dotenv

DEFINITION_VERSION = "ga4_session_funnel_v1"
PLACEHOLDER_TRANSACTION_IDS = ("(not set)", "unknown")


def scalar(cursor: pymysql.cursors.Cursor, sql: str, parameters: tuple[str, ...]) -> int:
    cursor.execute(sql, parameters)
    return int(cursor.fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--run-id", default=str(uuid.uuid4()))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()

    load_dotenv(arguments.env_file)
    password = os.environ.get("MYSQL_ROOT_PASSWORD")
    if not password:
        raise RuntimeError("未找到 MYSQL_ROOT_PASSWORD；请提供 .env 文件")

    connection = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            approved_events = scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM insightops_dw.ga4_event_stg AS staged
                JOIN insightops_ops.data_quality_run AS quality
                  ON quality.run_id = staged.quality_run_id
                WHERE staged.batch_id = %s AND quality.status = 'SUCCEEDED'
                """,
                (arguments.batch_id,),
            )
            if not approved_events:
                raise ValueError("未找到已通过质量门禁的 GA4 Staging 事件")
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'build_ga4_session_funnel', %s, 'RUNNING', %s)
                """,
                (
                    arguments.run_id,
                    DEFINITION_VERSION,
                    json.dumps(
                        {
                            "batch_id": arguments.batch_id,
                            "placeholder_transaction_ids": list(PLACEHOLDER_TRANSACTION_IDS),
                            "primary_funnel": "begin_checkout -> purchase",
                        }
                    ),
                ),
            )
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT IGNORE INTO insightops_mart.ga4_session_fact (
                  source_batch_id, source_quality_run_id, build_run_id, definition_version,
                  user_pseudo_id, ga_session_id, session_start_ts, session_end_ts, session_date,
                  landing_page_path, device_category, country_name,
                  first_acquisition_source_name, first_acquisition_medium_name,
                  event_count, page_view_count, has_session_start, has_view_item,
                  has_add_to_cart, has_begin_checkout, has_purchase_event,
                  has_checkout_to_purchase_event, has_canonical_order,
                  has_checkout_to_canonical_order
                )
                WITH ranked AS (
                  SELECT
                    staged.*,
                    ROW_NUMBER() OVER (
                      PARTITION BY staged.user_pseudo_id, staged.ga_session_id
                      ORDER BY staged.event_ts, staged.stg_event_id
                    ) AS session_event_rank
                  FROM insightops_dw.ga4_event_stg AS staged
                  WHERE staged.batch_id = %s
                ), session_rollup AS (
                  SELECT
                    batch_id,
                    MIN(quality_run_id) AS quality_run_id,
                    user_pseudo_id,
                    ga_session_id,
                    MIN(event_ts) AS session_start_ts,
                    MAX(event_ts) AS session_end_ts,
                    DATE(MIN(event_ts)) AS session_date,
                    MAX(CASE WHEN session_event_rank = 1 THEN page_path END) AS landing_page_path,
                    MAX(CASE WHEN session_event_rank = 1 THEN device_category END)
                      AS device_category,
                    MAX(CASE WHEN session_event_rank = 1 THEN country_name END) AS country_name,
                    MAX(CASE WHEN session_event_rank = 1 THEN first_acquisition_source_name END)
                      AS first_acquisition_source_name,
                    MAX(CASE WHEN session_event_rank = 1 THEN first_acquisition_medium_name END)
                      AS first_acquisition_medium_name,
                    COUNT(*) AS event_count,
                    SUM(event_name = 'page_view') AS page_view_count,
                    MAX(event_name = 'session_start') AS has_session_start,
                    MAX(event_name = 'view_item') AS has_view_item,
                    MAX(event_name = 'add_to_cart') AS has_add_to_cart,
                    MAX(event_name = 'begin_checkout') AS has_begin_checkout,
                    MAX(event_name = 'purchase') AS has_purchase_event,
                    MIN(CASE WHEN event_name = 'begin_checkout' THEN event_ts END)
                      AS begin_checkout_ts,
                    MIN(CASE WHEN event_name = 'purchase' THEN event_ts END) AS purchase_event_ts,
                    MIN(
                      CASE
                        WHEN is_order_eligible = 1
                         AND transaction_id NOT IN (%s, %s) THEN event_ts
                      END
                    ) AS canonical_order_ts
                  FROM ranked
                  GROUP BY batch_id, user_pseudo_id, ga_session_id
                )
                SELECT
                  batch_id,
                  quality_run_id,
                  %s,
                  %s,
                  user_pseudo_id,
                  ga_session_id,
                  session_start_ts,
                  session_end_ts,
                  session_date,
                  landing_page_path,
                  device_category,
                  country_name,
                  first_acquisition_source_name,
                  first_acquisition_medium_name,
                  event_count,
                  page_view_count,
                  has_session_start,
                  has_view_item,
                  has_add_to_cart,
                  has_begin_checkout,
                  has_purchase_event,
                  begin_checkout_ts IS NOT NULL AND purchase_event_ts >= begin_checkout_ts,
                  canonical_order_ts IS NOT NULL,
                  begin_checkout_ts IS NOT NULL AND canonical_order_ts >= begin_checkout_ts
                FROM session_rollup
                """,
                (
                    arguments.batch_id,
                    *PLACEHOLDER_TRANSACTION_IDS,
                    arguments.run_id,
                    DEFINITION_VERSION,
                ),
            )
            session_inserted_rows = cursor.rowcount
            session_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_mart.ga4_session_fact
                WHERE source_batch_id = %s AND definition_version = %s
                """,
                (arguments.batch_id, DEFINITION_VERSION),
            )
            cursor.execute(
                """
                INSERT INTO insightops_mart.ga4_daily_funnel_metric (
                  source_batch_id, build_run_id, definition_version, metric_date,
                  observed_sessions, sessions_with_session_start, product_view_sessions,
                  add_to_cart_sessions, checkout_start_sessions,
                  checkout_to_purchase_event_sessions, checkout_to_canonical_order_sessions,
                  checkout_to_purchase_event_rate, checkout_to_canonical_order_rate
                )
                SELECT
                  source_batch_id,
                  %s,
                  %s,
                  session_date,
                  COUNT(*),
                  SUM(has_session_start),
                  SUM(has_view_item),
                  SUM(has_add_to_cart),
                  SUM(has_begin_checkout),
                  SUM(has_checkout_to_purchase_event),
                  SUM(has_checkout_to_canonical_order),
                  ROUND(
                    CAST(SUM(has_checkout_to_purchase_event) AS DECIMAL(20, 8))
                    / NULLIF(CAST(SUM(has_begin_checkout) AS DECIMAL(20, 8)), 0),
                    8
                  ),
                  ROUND(
                    CAST(SUM(has_checkout_to_canonical_order) AS DECIMAL(20, 8))
                    / NULLIF(CAST(SUM(has_begin_checkout) AS DECIMAL(20, 8)), 0),
                    8
                  )
                FROM insightops_mart.ga4_session_fact
                WHERE source_batch_id = %s AND definition_version = %s
                GROUP BY source_batch_id, session_date
                """,
                (arguments.run_id, DEFINITION_VERSION, arguments.batch_id, DEFINITION_VERSION),
            )
            daily_inserted_rows = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_SESSION', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    approved_events,
                    session_rows,
                    "全量已通过质量门禁的事件按 user_pseudo_id + ga_session_id 聚合。",
                ),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_DAILY_FUNNEL', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    session_rows,
                    daily_inserted_rows,
                    (
                        "主漏斗为 begin_checkout 到同会话 purchase/规范订单；"
                        "add_to_cart 仅作覆盖守护。"
                    ),
                ),
            )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (session_inserted_rows + daily_inserted_rows, arguments.run_id),
            )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'FAILED', finished_at = UTC_TIMESTAMP(6), error_message = %s
                WHERE run_id = %s
                """,
                (str(exc)[:65_535], arguments.run_id),
            )
        connection.commit()
        raise
    finally:
        connection.close()

    print(
        "GA4 会话与漏斗构建完成："
        f"run_id={arguments.run_id}，sessions={session_inserted_rows}，"
        f"daily_metrics={daily_inserted_rows}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
