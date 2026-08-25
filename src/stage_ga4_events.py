"""Write quality-approved GA4 Raw events into the Staging layer."""

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
                SELECT COUNT(*)
                FROM insightops_raw.ga4_event_raw AS raw
                LEFT JOIN insightops_ops.data_quality_reject AS reject_record
                  ON reject_record.run_id = %s
                 AND reject_record.source_row_number = raw.source_row_number
                 AND reject_record.severity = 'BLOCKER'
                WHERE raw.batch_id = %s AND reject_record.reject_id IS NULL
                """,
                (arguments.quality_run_id, arguments.batch_id),
            )
            eligible_rows = int(cursor.fetchone()[0])

            cursor.execute(
                """
                INSERT INTO insightops_dw.ga4_event_stg (
                  raw_event_id, batch_id, quality_run_id, event_date, event_ts,
                  user_pseudo_id, event_name, ga_session_id, page_location, page_path,
                  device_category, country_name, first_acquisition_source_name,
                  first_acquisition_medium_name, transaction_id, purchase_revenue_usd,
                  is_purchase, is_order_eligible
                )
                SELECT
                  raw.raw_event_id,
                  raw.batch_id,
                  %s,
                  raw.event_date,
                  raw.event_ts,
                  raw.user_pseudo_id,
                  raw.event_name,
                  raw.ga_session_id,
                  raw.page_location,
                  COALESCE(
                    NULLIF(
                      REGEXP_REPLACE(
                        REGEXP_REPLACE(raw.page_location, '^https?://[^/]+', ''),
                        '[?#].*$',
                        ''
                      ),
                      ''
                    ),
                    '/'
                  ),
                  raw.device_category,
                  raw.country_name,
                  raw.first_acquisition_source_name,
                  raw.first_acquisition_medium_name,
                  raw.transaction_id,
                  raw.purchase_revenue_usd,
                  raw.event_name = 'purchase',
                  raw.event_name = 'purchase'
                    AND raw.transaction_id IS NOT NULL
                    AND raw.purchase_revenue_usd IS NOT NULL
                FROM insightops_raw.ga4_event_raw AS raw
                LEFT JOIN insightops_ops.data_quality_reject AS reject_record
                  ON reject_record.run_id = %s
                 AND reject_record.source_row_number = raw.source_row_number
                 AND reject_record.severity = 'BLOCKER'
                LEFT JOIN insightops_dw.ga4_event_stg AS staged
                  ON staged.raw_event_id = raw.raw_event_id
                WHERE raw.batch_id = %s
                  AND reject_record.reject_id IS NULL
                  AND staged.raw_event_id IS NULL
                """,
                (arguments.quality_run_id, arguments.quality_run_id, arguments.batch_id),
            )
            inserted_rows = cursor.rowcount
        connection.commit()
    finally:
        connection.close()

    print(
        f"GA4 Staging 完成：eligible_rows={eligible_rows}，inserted_rows={inserted_rows}，"
        f"quality_run_id={arguments.quality_run_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
