"""Build UCI customer RFM and historical-value proxy facts from valid order facts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import pymysql
from dotenv import load_dotenv

DEFINITION_VERSION = "uci_customer_value_v1"


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
            valid_orders = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_mart.uci_order_fact
                WHERE source_batch_id = %s AND definition_version = 'uci_order_v1'
                """,
                (arguments.batch_id,),
            )
            if not valid_orders:
                raise ValueError("未找到可用于客户价值分析的 UCI 规范订单")
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'build_uci_customer_value', %s, 'RUNNING', %s)
                """,
                (
                    arguments.run_id,
                    DEFINITION_VERSION,
                    json.dumps(
                        {
                            "batch_id": arguments.batch_id,
                            "order_definition_version": "uci_order_v1",
                            "snapshot_policy": "max_order_date_plus_one_day",
                            "ltv_proxy": "historical_value_gbp",
                        }
                    ),
                ),
            )
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT IGNORE INTO insightops_mart.uci_customer_value_fact (
                  source_batch_id, build_run_id, definition_version, snapshot_date,
                  customer_id, country_name, first_order_ts, last_order_ts, recency_days,
                  frequency_orders, historical_value_gbp, average_order_value_gbp,
                  is_repeat_customer, recency_score, frequency_score, monetary_score,
                  rfm_segment
                )
                WITH customer_base AS (
                  SELECT
                    source_batch_id,
                    customer_id,
                    CASE
                      WHEN COUNT(DISTINCT country_name) = 1 THEN MAX(country_name)
                      ELSE 'MULTIPLE'
                    END AS country_name,
                    MIN(order_ts) AS first_order_ts,
                    MAX(order_ts) AS last_order_ts,
                    COUNT(*) AS frequency_orders,
                    SUM(gmv_gbp) AS historical_value_gbp,
                    AVG(gmv_gbp) AS average_order_value_gbp
                  FROM insightops_mart.uci_order_fact
                  WHERE source_batch_id = %s
                    AND definition_version = 'uci_order_v1'
                    AND is_customer_identified = 1
                  GROUP BY source_batch_id, customer_id
                ), calendar AS (
                  SELECT DATE_ADD(MAX(DATE(last_order_ts)), INTERVAL 1 DAY) AS snapshot_date
                  FROM customer_base
                ), scored AS (
                  SELECT
                    customer_base.*,
                    calendar.snapshot_date,
                    DATEDIFF(calendar.snapshot_date, DATE(last_order_ts)) AS recency_days,
                    CEIL(
                      CUME_DIST() OVER (
                        ORDER BY DATEDIFF(calendar.snapshot_date, DATE(last_order_ts)) DESC
                      ) * 5
                    )
                      AS recency_score,
                    CEIL(CUME_DIST() OVER (ORDER BY frequency_orders) * 5) AS frequency_score,
                    CEIL(CUME_DIST() OVER (ORDER BY historical_value_gbp) * 5) AS monetary_score
                  FROM customer_base CROSS JOIN calendar
                )
                SELECT
                  source_batch_id,
                  %s,
                  %s,
                  snapshot_date,
                  customer_id,
                  country_name,
                  first_order_ts,
                  last_order_ts,
                  recency_days,
                  frequency_orders,
                  historical_value_gbp,
                  average_order_value_gbp,
                  frequency_orders > 1,
                  recency_score,
                  frequency_score,
                  monetary_score,
                  CASE
                    WHEN recency_score >= 4 AND frequency_score >= 4 AND monetary_score >= 4
                      THEN 'CHAMPION'
                    WHEN frequency_score >= 4 AND recency_score >= 3 THEN 'LOYAL'
                    WHEN recency_score <= 2 AND frequency_score >= 3 THEN 'AT_RISK'
                    WHEN recency_score >= 4 AND frequency_score <= 2 THEN 'NEW_OR_PROMISING'
                    ELSE 'STANDARD'
                  END
                FROM scored
                """,
                (arguments.batch_id, arguments.run_id, DEFINITION_VERSION),
            )
            customer_inserted_rows = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO insightops_mart.uci_customer_value_summary (
                  source_batch_id, build_run_id, definition_version, snapshot_date,
                  valid_orders, identified_orders, identified_order_coverage,
                  identified_customers, repeat_customers, historical_value_gbp
                )
                SELECT
                  all_orders.source_batch_id,
                  %s,
                  %s,
                  DATE_ADD(all_orders.max_order_date, INTERVAL 1 DAY),
                  all_orders.valid_orders,
                  all_orders.identified_orders,
                  ROUND(
                    CAST(all_orders.identified_orders AS DECIMAL(20, 8))
                    / NULLIF(CAST(all_orders.valid_orders AS DECIMAL(20, 8)), 0),
                    8
                  ),
                  identified.identified_customers,
                  identified.repeat_customers,
                  identified.historical_value_gbp
                FROM (
                  SELECT
                    source_batch_id,
                    COUNT(*) AS valid_orders,
                    SUM(is_customer_identified) AS identified_orders,
                    MAX(DATE(order_ts)) AS max_order_date
                  FROM insightops_mart.uci_order_fact
                  WHERE source_batch_id = %s AND definition_version = 'uci_order_v1'
                  GROUP BY source_batch_id
                ) AS all_orders
                JOIN (
                  SELECT
                    source_batch_id,
                    COUNT(DISTINCT customer_id) AS identified_customers,
                    SUM(is_repeat_customer) AS repeat_customers,
                    SUM(historical_value_gbp) AS historical_value_gbp
                  FROM insightops_mart.uci_customer_value_fact
                  WHERE source_batch_id = %s AND definition_version = %s
                  GROUP BY source_batch_id
                ) AS identified ON identified.source_batch_id = all_orders.source_batch_id
                ON DUPLICATE KEY UPDATE
                  build_run_id = VALUES(build_run_id),
                  valid_orders = VALUES(valid_orders),
                  identified_orders = VALUES(identified_orders),
                  identified_order_coverage = VALUES(identified_order_coverage),
                  identified_customers = VALUES(identified_customers),
                  repeat_customers = VALUES(repeat_customers),
                  historical_value_gbp = VALUES(historical_value_gbp)
                """,
                (
                    arguments.run_id,
                    DEFINITION_VERSION,
                    arguments.batch_id,
                    arguments.batch_id,
                    DEFINITION_VERSION,
                ),
            )
            summary_inserted_rows = cursor.rowcount
            customer_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_mart.uci_customer_value_fact
                WHERE source_batch_id = %s AND definition_version = %s
                """,
                (arguments.batch_id, DEFINITION_VERSION),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'UCI_CUSTOMER_VALUE', %s, %s, %s, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.batch_id,
                    valid_orders,
                    valid_orders
                    - scalar(
                        cursor,
                        """
                        SELECT COUNT(*) FROM insightops_mart.uci_order_fact
                        WHERE source_batch_id = %s AND definition_version = 'uci_order_v1'
                          AND is_customer_identified = 1
                        """,
                        (arguments.batch_id,),
                    ),
                    customer_rows,
                    "仅有客户 ID 的有效订单进入 RFM；historical_value_gbp 是观察期累计消费代理。",
                ),
            )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (customer_inserted_rows + summary_inserted_rows, arguments.run_id),
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
        "UCI 客户价值构建完成："
        f"run_id={arguments.run_id}，customers={customer_inserted_rows}，"
        f"summaries={summary_inserted_rows}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
