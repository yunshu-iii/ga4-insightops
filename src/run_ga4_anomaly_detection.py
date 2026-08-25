"""Detect GA4 daily metric anomalies with a trailing rolling median and MAD."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import pymysql
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db_connection import (
    pymysql_transaction_connection_from_env,
    sqlalchemy_engine_from_env,
)

ANOMALY_VERSION = "ga4_mad_anomaly_v2"
WINDOW_DAYS = 7
MIN_BASELINE_POINTS = 5
ROBUST_Z_THRESHOLD = 3.5
MIN_VALID_TRANSACTION_ID_COVERAGE = 0.95
METRICS = {
    "ga4_observed_sessions": "observed_sessions",
    "ga4_checkout_start_sessions": "checkout_start_sessions",
    "ga4_purchase_event_count": "purchase_events",
    "ga4_valid_transaction_id_coverage": "valid_transaction_id_coverage",
    "ga4_canonical_order_sessions": "canonical_order_sessions",
    "ga4_canonical_orders": "canonical_orders",
    "ga4_canonical_revenue_usd": "canonical_revenue_usd",
    "ga4_checkout_to_canonical_order_rate": "checkout_to_canonical_order_rate",
}
CANONICAL_ORDER_DEPENDENT_METRICS = {
    "ga4_canonical_order_sessions",
    "ga4_canonical_orders",
    "ga4_canonical_revenue_usd",
    "ga4_checkout_to_canonical_order_rate",
}
CONTRIBUTABLE_METRICS = {
    "ga4_canonical_orders": "canonical_orders",
    "ga4_canonical_revenue_usd": "canonical_revenue_usd",
}


def anomaly_status(value: float, median: float, mad: float) -> tuple[str, float | None]:
    if mad == 0:
        if value == median:
            return "NORMAL", None
        return ("ANOMALY_HIGH" if value > median else "ANOMALY_LOW"), None
    robust_z = 0.6745 * (value - median) / mad
    if robust_z >= ROBUST_Z_THRESHOLD:
        return "ANOMALY_HIGH", robust_z
    if robust_z <= -ROBUST_Z_THRESHOLD:
        return "ANOMALY_LOW", robust_z
    return "NORMAL", robust_z


def business_interpretability(
    metric_id: str, coverage_window: pd.Series
) -> tuple[bool, str | None]:
    if metric_id == "ga4_valid_transaction_id_coverage":
        return False, "交易号覆盖率是数据质量守护指标，不作业务表现指标。"
    if metric_id not in CANONICAL_ORDER_DEPENDENT_METRICS:
        return True, None
    if (coverage_window < MIN_VALID_TRANSACTION_ID_COVERAGE).any():
        return (
            False,
            "有效交易号覆盖率低于 95%，包含当前日或滚动基线；规范订单相关检测仅作数据覆盖诊断。",
        )
    return True, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--run-id", default=str(uuid.uuid4()))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    engine = sqlalchemy_engine_from_env(arguments.env_file)
    connection = pymysql_transaction_connection_from_env(arguments.env_file)
    daily = pd.read_sql(
        text(
            """
        SELECT metric_date, observed_sessions, checkout_start_sessions,
               canonical_order_sessions, canonical_orders, canonical_revenue_usd,
               checkout_to_canonical_order_rate, purchase_events,
               valid_transaction_id_purchase_events, valid_transaction_id_coverage
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = :batch_id AND definition_version = 'ga4_daily_metrics_v2'
        ORDER BY metric_date
            """
        ),
        engine,
        params={"batch_id": arguments.batch_id},
    )
    if daily.empty:
        connection.close()
        engine.dispose()
        raise ValueError("未找到 GA4 日指标；请先运行 build_ga4_daily_metrics.py")
    daily["metric_date"] = pd.to_datetime(daily["metric_date"])
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'run_ga4_anomaly_detection', %s, 'RUNNING', %s)
                """,
                (
                    arguments.run_id,
                    ANOMALY_VERSION,
                    json.dumps(
                        {
                            "batch_id": arguments.batch_id,
                            "window_days": WINDOW_DAYS,
                            "min_baseline_points": MIN_BASELINE_POINTS,
                            "robust_z_threshold": ROBUST_Z_THRESHOLD,
                        }
                    ),
                ),
            )
        connection.commit()

        anomaly_rows: list[tuple[object, ...]] = []
        for metric_id, column in METRICS.items():
            values = pd.to_numeric(daily[column], errors="coerce").fillna(0.0)
            for index, value in enumerate(values):
                history = values.iloc[max(0, index - WINDOW_DAYS) : index]
                coverage_window = pd.to_numeric(
                    daily["valid_transaction_id_coverage"].iloc[
                        max(0, index - WINDOW_DAYS) : index + 1
                    ],
                    errors="coerce",
                ).fillna(0.0)
                is_business_interpretable, interpretation_note = business_interpretability(
                    metric_id, coverage_window
                )
                if len(history) < MIN_BASELINE_POINTS:
                    anomaly_rows.append(
                        (
                            len(history),
                            metric_id,
                            daily.metric_date.iloc[index],
                            value,
                            0,
                            0,
                            None,
                            "INSUFFICIENT_HISTORY",
                            is_business_interpretable,
                            interpretation_note,
                        )
                    )
                    continue
                median = float(history.median())
                mad = float((history - median).abs().median())
                status, robust_z = anomaly_status(float(value), median, mad)
                anomaly_rows.append(
                    (
                        len(history),
                        metric_id,
                        daily.metric_date.iloc[index],
                        value,
                        median,
                        mad,
                        robust_z,
                        status,
                        is_business_interpretable,
                        interpretation_note,
                    )
                )

        contribution_rows = 0
        with connection.cursor() as cursor:
            for (
                points,
                metric_id,
                metric_date,
                value,
                median,
                mad,
                robust_z,
                status,
                is_business_interpretable,
                interpretation_note,
            ) in anomaly_rows:
                cursor.execute(
                    """
                    INSERT INTO insightops_ops.metric_anomaly_result (
                      run_id, source_batch_id, metric_id, metric_date, metric_value,
                      baseline_points, baseline_median, baseline_mad, robust_z_score, status,
                      is_business_interpretable, interpretation_note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        arguments.run_id,
                        arguments.batch_id,
                        metric_id,
                        metric_date.date(),
                        value,
                        points,
                        None if status == "INSUFFICIENT_HISTORY" else median,
                        None if status == "INSUFFICIENT_HISTORY" else mad,
                        robust_z,
                        status,
                        is_business_interpretable,
                        interpretation_note,
                    ),
                )
                anomaly_id = cursor.lastrowid
                if (
                    status not in {"ANOMALY_HIGH", "ANOMALY_LOW"}
                    or metric_id not in CONTRIBUTABLE_METRICS
                    or not is_business_interpretable
                ):
                    continue
                contribution_rows += write_contributions(
                    cursor,
                    engine,
                    anomaly_id,
                    arguments.batch_id,
                    metric_date,
                    CONTRIBUTABLE_METRICS[metric_id],
                    value - median,
                )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_ANOMALY', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    len(daily) * len(METRICS),
                    len(anomaly_rows),
                    "滚动 7 天历史中位数与 MAD；至少 5 个历史点；规范订单指标受交易号覆盖守护。",
                ),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4_ANOMALY_CONTRIBUTION', %s, %s, 0, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    len(daily),
                    contribution_rows,
                    "仅对交易号覆盖守护通过的订单数和收入异常做维度贡献切片，不主张因果。",
                ),
            )
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (len(anomaly_rows) + contribution_rows, arguments.run_id),
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
    anomaly_statuses = {"ANOMALY_HIGH", "ANOMALY_LOW"}
    anomaly_count = sum(row[7] in anomaly_statuses for row in anomaly_rows)
    suppressed_count = sum(row[7] in anomaly_statuses and not bool(row[8]) for row in anomaly_rows)
    print(
        f"GA4 异常检测完成：run_id={arguments.run_id}，"
        f"anomalies={anomaly_count}，contributions={contribution_rows}，"
        f"suppressed_anomalies={suppressed_count}"
    )
    return 0


def write_contributions(
    cursor: pymysql.cursors.Cursor,
    engine: Engine,
    anomaly_id: int,
    batch_id: str,
    metric_date: pd.Timestamp,
    metric_column: str,
    total_delta: float,
) -> int:
    dimensions = pd.read_sql(
        text(
            """
        SELECT metric_date, dimension_name, dimension_value, canonical_orders,
               canonical_revenue_usd
        FROM insightops_mart.ga4_daily_dimension_metric
        WHERE source_batch_id = :batch_id AND definition_version = 'ga4_daily_metrics_v2'
            """
        ),
        engine,
        params={"batch_id": batch_id},
    )
    dimensions["metric_date"] = pd.to_datetime(dimensions["metric_date"])
    history_start = metric_date - pd.Timedelta(days=WINDOW_DAYS)
    rows: list[tuple[object, ...]] = []
    for dimension_name, frame in dimensions.groupby("dimension_name"):
        values = sorted(frame.dimension_value.unique())
        history_dates = pd.date_range(history_start, metric_date - pd.Timedelta(days=1), freq="D")
        for dimension_value in values:
            series = frame[frame.dimension_value == dimension_value].set_index("metric_date")[
                metric_column
            ]
            baseline = pd.to_numeric(
                series.reindex(history_dates, fill_value=0), errors="coerce"
            ).fillna(0.0)
            current = float(series.get(metric_date, 0.0))
            baseline_median = float(baseline.median())
            delta = current - baseline_median
            rows.append((dimension_name, dimension_value, current, baseline_median, delta))
    rows.sort(key=lambda row: abs(row[4]), reverse=True)
    cursor.executemany(
        """
        INSERT INTO insightops_ops.metric_anomaly_contribution (
          anomaly_id, dimension_name, dimension_value, current_value, baseline_median,
          contribution_delta, total_delta, contribution_share, contribution_rank
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                anomaly_id,
                name,
                value,
                current,
                baseline,
                delta,
                total_delta,
                None if total_delta == 0 else delta / total_delta,
                rank,
            )
            for rank, (name, value, current, baseline, delta) in enumerate(rows, start=1)
        ],
    )
    return len(rows)


if __name__ == "__main__":
    sys.exit(main())
