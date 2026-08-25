"""Write quality-approved UCI retail lines to the Staging layer."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--quality-run-id", required=True)
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
            cursor.execute(
                """
                SELECT status FROM insightops_ops.data_quality_run
                WHERE run_id = %s AND batch_id = %s
                """,
                (arguments.quality_run_id, arguments.batch_id),
            )
            quality_run = cursor.fetchone()
            if quality_run is None:
                raise ValueError("未找到匹配此批次的质量运行")
            if quality_run[0] != "SUCCEEDED":
                raise ValueError(f"质量运行状态为 {quality_run[0]}，不能进入 Staging")

            cursor.execute(
                """
                INSERT INTO insightops_dw.uci_retail_line_stg (
                  raw_line_id, batch_id, quality_run_id, invoice_no, stock_code,
                  description_text, quantity, invoice_ts, unit_price, customer_id,
                  country_name, line_revenue, is_cancelled, is_exact_duplicate,
                  is_valid_sale_line, is_customer_identified
                )
                WITH ranked AS (
                  SELECT
                    raw.*,
                    ROW_NUMBER() OVER (
                      PARTITION BY raw.invoice_no, raw.stock_code,
                                   COALESCE(raw.description_text, ''), raw.quantity,
                                   raw.invoice_ts, raw.unit_price,
                                   COALESCE(raw.customer_id, ''), raw.country_name
                      ORDER BY raw.source_row_number
                    ) AS duplicate_rank
                  FROM insightops_raw.uci_retail_line_raw AS raw
                  LEFT JOIN insightops_ops.data_quality_reject AS reject_record
                    ON reject_record.run_id = %s
                   AND reject_record.source_row_number = raw.source_row_number
                   AND reject_record.severity = 'BLOCKER'
                  WHERE raw.batch_id = %s AND reject_record.reject_id IS NULL
                )
                SELECT
                  ranked.raw_line_id,
                  ranked.batch_id,
                  %s,
                  ranked.invoice_no,
                  ranked.stock_code,
                  ranked.description_text,
                  ranked.quantity,
                  ranked.invoice_ts,
                  ranked.unit_price,
                  ranked.customer_id,
                  ranked.country_name,
                  ranked.quantity * ranked.unit_price,
                  ranked.invoice_no LIKE 'C%%',
                  ranked.duplicate_rank > 1,
                  NOT (
                    ranked.invoice_no LIKE 'C%%' OR ranked.quantity <= 0
                    OR ranked.unit_price <= 0 OR ranked.duplicate_rank > 1
                  ),
                  ranked.customer_id IS NOT NULL
                FROM ranked
                LEFT JOIN insightops_dw.uci_retail_line_stg AS staged
                  ON staged.raw_line_id = ranked.raw_line_id
                WHERE staged.raw_line_id IS NULL
                """,
                (arguments.quality_run_id, arguments.batch_id, arguments.quality_run_id),
            )
            inserted_rows = cursor.rowcount
        connection.commit()
    finally:
        connection.close()

    print(
        f"UCI Staging 完成：inserted_rows={inserted_rows}，"
        f"quality_run_id={arguments.quality_run_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
