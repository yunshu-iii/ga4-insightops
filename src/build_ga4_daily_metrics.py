"""Materialize GA4 daily metrics and device/acquisition cuts from Mart facts."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db_connection import (
    pymysql_transaction_connection_from_env,
    sqlalchemy_engine_from_env,
)

DAILY_VERSION = "ga4_daily_metrics_v2"


def read_frame(engine: Engine, sql: str, batch_id: str) -> pd.DataFrame:
    return pd.read_sql(text(sql), engine, params={"batch_id": batch_id})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--run-id", default=str(uuid.uuid4()))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    engine = sqlalchemy_engine_from_env(arguments.env_file)
    connection = pymysql_transaction_connection_from_env(arguments.env_file)
    session_sql = """
      SELECT metric_date, observed_sessions, checkout_start_sessions,
             checkout_to_canonical_order_sessions AS canonical_order_sessions
      FROM insightops_mart.ga4_daily_funnel_metric
      WHERE source_batch_id = :batch_id AND definition_version = 'ga4_session_funnel_v1'
    """
    order_sql = """
      SELECT DATE(order_ts) AS metric_date, COUNT(*) AS canonical_orders,
             SUM(revenue_usd) AS canonical_revenue_usd
      FROM insightops_mart.ga4_order_fact
      WHERE source_batch_id = :batch_id AND definition_version = 'ga4_order_v1'
      GROUP BY DATE(order_ts)
    """
    purchase_sql = """
      SELECT
        event_date AS metric_date,
        SUM(is_purchase) AS purchase_events,
        SUM(
          is_purchase = 1
          AND transaction_id IS NOT NULL
          AND NULLIF(TRIM(transaction_id), '') IS NOT NULL
          AND transaction_id NOT IN ('(not set)', 'unknown')
        ) AS valid_transaction_id_purchase_events
      FROM insightops_dw.ga4_event_stg
      WHERE batch_id = :batch_id
      GROUP BY event_date
    """
    try:
        sessions = read_frame(engine, session_sql, arguments.batch_id)
        if sessions.empty:
            raise ValueError("未找到 GA4 会话漏斗事实")
        orders = read_frame(engine, order_sql, arguments.batch_id)
        purchases = read_frame(engine, purchase_sql, arguments.batch_id)
        daily = (
            sessions.merge(orders, on="metric_date", how="left")
            .merge(purchases, on="metric_date", how="left")
            .fillna(0)
        )
        daily["checkout_to_canonical_order_rate"] = (
            daily["canonical_order_sessions"] / daily["checkout_start_sessions"]
        ).where(daily["checkout_start_sessions"] > 0)
        daily["valid_transaction_id_coverage"] = (
            daily["valid_transaction_id_purchase_events"] / daily["purchase_events"]
        ).where(daily["purchase_events"] > 0)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'build_ga4_daily_metrics', %s, 'RUNNING', %s)
                """,
                (
                    arguments.run_id,
                    DAILY_VERSION,
                    json.dumps(
                        {"batch_id": arguments.batch_id, "dimensions": ["device", "acquisition"]}
                    ),
                ),
            )
            cursor.executemany(
                """
                INSERT INTO insightops_mart.ga4_daily_metric (
                  source_batch_id, build_run_id, definition_version, metric_date,
                  observed_sessions, checkout_start_sessions, canonical_order_sessions,
                  canonical_orders, canonical_revenue_usd, checkout_to_canonical_order_rate,
                  purchase_events, valid_transaction_id_purchase_events,
                  valid_transaction_id_coverage
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  build_run_id = VALUES(build_run_id),
                  observed_sessions = VALUES(observed_sessions),
                  checkout_start_sessions = VALUES(checkout_start_sessions),
                  canonical_order_sessions = VALUES(canonical_order_sessions),
                  canonical_orders = VALUES(canonical_orders),
                  canonical_revenue_usd = VALUES(canonical_revenue_usd),
                  checkout_to_canonical_order_rate = VALUES(checkout_to_canonical_order_rate),
                  purchase_events = VALUES(purchase_events),
                  valid_transaction_id_purchase_events =
                    VALUES(valid_transaction_id_purchase_events),
                  valid_transaction_id_coverage = VALUES(valid_transaction_id_coverage)
                """,
                [
                    (
                        arguments.batch_id,
                        arguments.run_id,
                        DAILY_VERSION,
                        row.metric_date,
                        int(row.observed_sessions),
                        int(row.checkout_start_sessions),
                        int(row.canonical_order_sessions),
                        int(row.canonical_orders),
                        float(row.canonical_revenue_usd),
                        None
                        if pd.isna(row.checkout_to_canonical_order_rate)
                        else float(row.checkout_to_canonical_order_rate),
                        int(row.purchase_events),
                        int(row.valid_transaction_id_purchase_events),
                        None
                        if pd.isna(row.valid_transaction_id_coverage)
                        else float(row.valid_transaction_id_coverage),
                    )
                    for row in daily.itertuples(index=False)
                ],
            )
        connection.commit()

        dimension_rows: list[tuple[object, ...]] = []
        for dimension_name, session_column, order_expression in [
            ("device_category", "device_category", "device_category"),
            (
                "acquisition_channel",
                "CONCAT(first_acquisition_source_name, ' / ', first_acquisition_medium_name)",
                "CONCAT(first_acquisition_source_name, ' / ', first_acquisition_medium_name)",
            ),
        ]:
            session_cut = pd.read_sql(
                text(
                    f"""
                    SELECT session_date AS metric_date, {session_column} AS dimension_value,
                           COUNT(*) AS observed_sessions,
                           SUM(has_begin_checkout) AS checkout_start_sessions,
                           SUM(has_checkout_to_canonical_order) AS canonical_order_sessions
                    FROM insightops_mart.ga4_session_fact
                    WHERE source_batch_id = :batch_id
                      AND definition_version = 'ga4_session_funnel_v1'
                    GROUP BY session_date, {session_column}
                    """
                ),
                engine,
                params={"batch_id": arguments.batch_id},
            )
            order_cut = pd.read_sql(
                text(
                    f"""
                    SELECT DATE(order_ts) AS metric_date, {order_expression} AS dimension_value,
                           COUNT(*) AS canonical_orders, SUM(revenue_usd) AS canonical_revenue_usd
                    FROM insightops_mart.ga4_order_fact
                    WHERE source_batch_id = :batch_id AND definition_version = 'ga4_order_v1'
                    GROUP BY DATE(order_ts), {order_expression}
                    """
                ),
                engine,
                params={"batch_id": arguments.batch_id},
            )
            merged = session_cut.merge(
                order_cut, on=["metric_date", "dimension_value"], how="outer"
            ).fillna(0)
            dimension_rows.extend(
                (
                    arguments.batch_id,
                    arguments.run_id,
                    DAILY_VERSION,
                    row.metric_date,
                    dimension_name,
                    str(row.dimension_value),
                    int(row.observed_sessions),
                    int(row.checkout_start_sessions),
                    int(row.canonical_order_sessions),
                    int(row.canonical_orders),
                    float(row.canonical_revenue_usd),
                )
                for row in merged.itertuples(index=False)
            )
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO insightops_mart.ga4_daily_dimension_metric (
                  source_batch_id, build_run_id, definition_version, metric_date, dimension_name,
                  dimension_value, observed_sessions, checkout_start_sessions,
                  canonical_order_sessions, canonical_orders, canonical_revenue_usd
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  build_run_id = VALUES(build_run_id),
                  observed_sessions = VALUES(observed_sessions),
                  checkout_start_sessions = VALUES(checkout_start_sessions),
                  canonical_order_sessions = VALUES(canonical_order_sessions),
                  canonical_orders = VALUES(canonical_orders),
                  canonical_revenue_usd = VALUES(canonical_revenue_usd)
                """,
                dimension_rows,
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_DAILY_METRIC', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    len(sessions),
                    len(daily),
                    "日指标来自会话漏斗与规范订单事实。",
                ),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_DAILY_DIMENSION', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    len(daily),
                    len(dimension_rows),
                    "按设备和首次获客渠道切片。",
                ),
            )
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (len(daily) + len(dimension_rows), arguments.run_id),
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
        engine.dispose()
    print(
        f"GA4 日指标构建完成：run_id={arguments.run_id}，"
        f"daily_rows={len(daily)}，dimension_rows={len(dimension_rows)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
