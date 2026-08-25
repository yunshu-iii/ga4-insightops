"""Build versioned, deduplicated UCI and GA4 order facts from approved Staging data."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import pymysql
from dotenv import load_dotenv

UCI_DEFINITION_VERSION = "uci_order_v1"
GA4_DEFINITION_VERSION = "ga4_order_v1"
PLACEHOLDER_TRANSACTION_IDS = ("(not set)", "unknown")


def scalar(cursor: pymysql.cursors.Cursor, sql: str, parameters: tuple[str, ...]) -> int:
    cursor.execute(sql, parameters)
    return int(cursor.fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uci-batch-id", required=True)
    parser.add_argument("--ga4-batch-id", required=True)
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
    input_description = json.dumps(
        {
            "uci_batch_id": arguments.uci_batch_id,
            "ga4_batch_id": arguments.ga4_batch_id,
            "uci_definition_version": UCI_DEFINITION_VERSION,
            "ga4_definition_version": GA4_DEFINITION_VERSION,
            "ga4_placeholder_transaction_ids": list(PLACEHOLDER_TRANSACTION_IDS),
        },
        ensure_ascii=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'build_order_facts', 'order_facts_v1', 'RUNNING', %s)
                """,
                (arguments.run_id, input_description),
            )
        connection.commit()

        with connection.cursor() as cursor:
            uci_input_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_dw.uci_retail_line_stg
                WHERE batch_id = %s AND is_valid_sale_line = 1
                """,
                (arguments.uci_batch_id,),
            )
            uci_order_rows = scalar(
                cursor,
                """
                SELECT COUNT(DISTINCT invoice_no) FROM insightops_dw.uci_retail_line_stg
                WHERE batch_id = %s AND is_valid_sale_line = 1
                """,
                (arguments.uci_batch_id,),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO insightops_mart.uci_order_fact (
                  source_batch_id, source_quality_run_id, build_run_id, definition_version,
                  invoice_no, order_ts, customer_id, country_name, valid_line_count,
                  total_quantity, gmv_gbp, is_customer_identified
                )
                SELECT
                  staged.batch_id,
                  MIN(staged.quality_run_id),
                  %s,
                  %s,
                  staged.invoice_no,
                  MIN(staged.invoice_ts),
                  MAX(staged.customer_id),
                  MAX(staged.country_name),
                  COUNT(*),
                  SUM(staged.quantity),
                  SUM(staged.line_revenue),
                  MAX(staged.is_customer_identified)
                FROM insightops_dw.uci_retail_line_stg AS staged
                WHERE staged.batch_id = %s AND staged.is_valid_sale_line = 1
                GROUP BY staged.batch_id, staged.invoice_no
                """,
                (arguments.run_id, UCI_DEFINITION_VERSION, arguments.uci_batch_id),
            )
            uci_inserted_rows = cursor.rowcount
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'UCI', %s, %s, %s, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.uci_batch_id,
                    uci_input_rows,
                    0,
                    uci_order_rows,
                    "仅聚合 is_valid_sale_line = 1；客户 ID 缺失不排除订单。",
                ),
            )

            ga4_event_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_dw.ga4_event_stg
                WHERE batch_id = %s AND is_order_eligible = 1
                """,
                (arguments.ga4_batch_id,),
            )
            ga4_placeholder_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) FROM insightops_dw.ga4_event_stg
                WHERE batch_id = %s
                  AND is_order_eligible = 1
                  AND transaction_id IN (%s, %s)
                """,
                (arguments.ga4_batch_id, *PLACEHOLDER_TRANSACTION_IDS),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO insightops_mart.ga4_order_fact (
                  source_batch_id, source_quality_run_id, build_run_id, definition_version,
                  transaction_id, order_ts, user_pseudo_id, country_name, device_category,
                  first_acquisition_source_name, first_acquisition_medium_name,
                  purchase_event_count, revenue_usd
                )
                WITH eligible AS (
                  SELECT
                    staged.*,
                    COUNT(*) OVER (PARTITION BY staged.transaction_id) AS purchase_event_count,
                    ROW_NUMBER() OVER (
                      PARTITION BY staged.transaction_id
                      ORDER BY staged.event_ts, staged.stg_event_id
                    ) AS transaction_rank
                  FROM insightops_dw.ga4_event_stg AS staged
                  WHERE staged.batch_id = %s
                    AND staged.is_order_eligible = 1
                    AND NULLIF(TRIM(staged.transaction_id), '') IS NOT NULL
                    AND staged.transaction_id NOT IN (%s, %s)
                )
                SELECT
                  eligible.batch_id,
                  eligible.quality_run_id,
                  %s,
                  %s,
                  eligible.transaction_id,
                  eligible.event_ts,
                  eligible.user_pseudo_id,
                  eligible.country_name,
                  eligible.device_category,
                  eligible.first_acquisition_source_name,
                  eligible.first_acquisition_medium_name,
                  eligible.purchase_event_count,
                  eligible.purchase_revenue_usd
                FROM eligible
                WHERE eligible.transaction_rank = 1
                """,
                (
                    arguments.ga4_batch_id,
                    *PLACEHOLDER_TRANSACTION_IDS,
                    arguments.run_id,
                    GA4_DEFINITION_VERSION,
                ),
            )
            ga4_inserted_rows = cursor.rowcount
            ga4_order_rows = scalar(
                cursor,
                """
                SELECT COUNT(DISTINCT transaction_id) FROM insightops_dw.ga4_event_stg
                WHERE batch_id = %s
                  AND is_order_eligible = 1
                  AND NULLIF(TRIM(transaction_id), '') IS NOT NULL
                  AND transaction_id NOT IN (%s, %s)
                """,
                (arguments.ga4_batch_id, *PLACEHOLDER_TRANSACTION_IDS),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, 'GA4', %s, %s, %s, %s, %s)
                """,
                (
                    arguments.run_id,
                    arguments.ga4_batch_id,
                    ga4_event_rows,
                    ga4_placeholder_rows,
                    ga4_order_rows,
                    "排除占位交易号；同一交易号以最早事件保留一条规范订单。",
                ),
            )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (uci_inserted_rows + ga4_inserted_rows, arguments.run_id),
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
        "订单事实构建完成："
        f"run_id={arguments.run_id}，uci_inserted_rows={uci_inserted_rows}，"
        f"ga4_inserted_rows={ga4_inserted_rows}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
