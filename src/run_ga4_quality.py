"""Run the versioned GA4 Raw data-quality gate and record evidence in MySQL."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pymysql
from dotenv import load_dotenv


@dataclass(frozen=True)
class QualityRule:
    rule_id: str
    severity: str
    failed_count_sql: str
    rejected_rows_sql: str | None = None


RAW_FILTER = "batch_id = %s"
RULE_SET_VERSION = "ga4_raw_v2"

REQUIRED_FIELDS_PREDICATE = """
event_date IS NULL OR event_ts IS NULL OR TRIM(user_pseudo_id) = '' OR
TRIM(event_name) = '' OR TRIM(ga_session_id) = '' OR TRIM(page_location) = '' OR
TRIM(device_category) = '' OR TRIM(country_name) = '' OR
TRIM(first_acquisition_source_name) = '' OR TRIM(first_acquisition_medium_name) = ''
"""

RULES = [
    QualityRule(
        "B01_batch_succeeded",
        "BLOCKER",
        """
        SELECT CASE WHEN EXISTS (
          SELECT 1 FROM insightops_ops.ingestion_batch
          WHERE batch_id = %s AND status = 'SUCCEEDED'
        ) THEN 0 ELSE 1 END
        """,
    ),
    QualityRule(
        "B02_rows_present",
        "BLOCKER",
        f"""
        SELECT CASE WHEN COUNT(*) > 0 THEN 0 ELSE 1 END
        FROM insightops_raw.ga4_event_raw WHERE {RAW_FILTER}
        """,
    ),
    QualityRule(
        "B03_date_within_batch_range",
        "BLOCKER",
        """
        SELECT COUNT(*)
        FROM insightops_raw.ga4_event_raw AS raw
        JOIN insightops_ops.ingestion_batch AS batch ON batch.batch_id = raw.batch_id
        WHERE raw.batch_id = %s
          AND (raw.event_date < batch.extract_start_date OR raw.event_date > batch.extract_end_date)
        """,
        """
        SELECT raw.source_row_number
        FROM insightops_raw.ga4_event_raw AS raw
        JOIN insightops_ops.ingestion_batch AS batch ON batch.batch_id = raw.batch_id
        WHERE raw.batch_id = %s
          AND (raw.event_date < batch.extract_start_date OR raw.event_date > batch.extract_end_date)
        """,
    ),
    QualityRule(
        "B04_timestamp_matches_event_date",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND DATE(event_ts) <> event_date
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND DATE(event_ts) <> event_date
        """,
    ),
    QualityRule(
        "B05_required_fields_populated",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND ({REQUIRED_FIELDS_PREDICATE})
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND ({REQUIRED_FIELDS_PREDICATE})
        """,
    ),
    QualityRule(
        "B06_valid_device_category",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND device_category NOT IN ('desktop', 'mobile', 'tablet')
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND device_category NOT IN ('desktop', 'mobile', 'tablet')
        """,
    ),
    QualityRule(
        "B07_valid_page_location",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND page_location NOT REGEXP '^https?://'
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND page_location NOT REGEXP '^https?://'
        """,
    ),
    QualityRule(
        "B08_nonnegative_purchase_revenue",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND purchase_revenue_usd < 0
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND purchase_revenue_usd < 0
        """,
    ),
    QualityRule(
        "B09_revenue_only_on_purchase",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND purchase_revenue_usd IS NOT NULL AND event_name <> 'purchase'
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND purchase_revenue_usd IS NOT NULL AND event_name <> 'purchase'
        """,
    ),
    QualityRule(
        "B10_purchase_has_revenue",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND event_name = 'purchase'
          AND purchase_revenue_usd IS NULL
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND event_name = 'purchase'
          AND purchase_revenue_usd IS NULL
        """,
    ),
    QualityRule(
        "B11_unique_source_row_number",
        "BLOCKER",
        f"""
        SELECT COUNT(*) - COUNT(DISTINCT source_row_number)
        FROM insightops_raw.ga4_event_raw WHERE {RAW_FILTER}
        """,
    ),
    QualityRule(
        "W01_unknown_acquisition",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER}
          AND (first_acquisition_source_name = 'unknown'
               OR first_acquisition_medium_name = 'unknown')
        """,
    ),
    QualityRule(
        "W02_duplicate_purchase_transaction",
        "WARNING",
        """
        SELECT COUNT(*)
        FROM insightops_raw.ga4_event_raw AS raw
        JOIN (
          SELECT transaction_id
          FROM insightops_raw.ga4_event_raw
          WHERE batch_id = %s AND event_name = 'purchase' AND transaction_id IS NOT NULL
          GROUP BY transaction_id HAVING COUNT(*) > 1
        ) AS duplicates ON duplicates.transaction_id = raw.transaction_id
        WHERE raw.batch_id = %s AND raw.event_name = 'purchase'
        """,
    ),
    QualityRule(
        "W03_purchase_missing_transaction_id",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.ga4_event_raw
        WHERE {RAW_FILTER} AND event_name = 'purchase' AND transaction_id IS NULL
        """,
    ),
]


def scalar(cursor: pymysql.cursors.Cursor, sql: str, parameters: tuple[str, ...]) -> int:
    cursor.execute(sql, parameters)
    value = cursor.fetchone()[0]
    return int(value)


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
            total_rows = scalar(
                cursor,
                "SELECT COUNT(*) FROM insightops_raw.ga4_event_raw WHERE batch_id = %s",
                (arguments.batch_id,),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.data_quality_run (
                  run_id, batch_id, dataset_name, rule_set_version, status, total_rows
                ) VALUES (%s, %s, 'ga4_event_raw', %s, 'RUNNING', %s)
                """,
                (arguments.run_id, arguments.batch_id, RULE_SET_VERSION, total_rows),
            )
        connection.commit()

        failed_rules = 0
        blocker_failed_rules = 0
        with connection.cursor() as cursor:
            for rule in RULES:
                parameter_count = rule.failed_count_sql.count("%s")
                failed_rows = scalar(
                    cursor, rule.failed_count_sql, tuple([arguments.batch_id] * parameter_count)
                )
                outcome = "FAILED" if failed_rows else "PASSED"
                failed_rate = failed_rows / total_rows if total_rows else 0
                cursor.execute(
                    """
                    INSERT INTO insightops_ops.data_quality_result (
                      run_id, rule_id, severity, failed_rows, failed_rate, outcome
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        arguments.run_id,
                        rule.rule_id,
                        rule.severity,
                        failed_rows,
                        failed_rate,
                        outcome,
                    ),
                )
                if failed_rows:
                    failed_rules += 1
                    blocker_failed_rules += int(rule.severity == "BLOCKER")
                    if rule.rejected_rows_sql:
                        cursor.execute(rule.rejected_rows_sql, (arguments.batch_id,))
                        source_rows = cursor.fetchall()
                        cursor.executemany(
                            """
                            INSERT IGNORE INTO insightops_ops.data_quality_reject (
                              run_id, batch_id, source_table, source_row_number, rule_id, severity
                            ) VALUES (%s, %s, 'ga4_event_raw', %s, %s, %s)
                            """,
                            [
                                (
                                    arguments.run_id,
                                    arguments.batch_id,
                                    source_row[0],
                                    rule.rule_id,
                                    rule.severity,
                                )
                                for source_row in source_rows
                            ],
                        )
        final_status = "BLOCKED" if blocker_failed_rules else "SUCCEEDED"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.data_quality_run
                SET status = %s, failed_rules = %s, blocker_failed_rules = %s,
                    finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (final_status, failed_rules, blocker_failed_rules, arguments.run_id),
            )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.data_quality_run
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
        f"GA4 质量检查完成：run_id={arguments.run_id}，status={final_status}，"
        f"failed_rules={failed_rules}，blocker_failed_rules={blocker_failed_rules}"
    )
    return 0 if final_status == "SUCCEEDED" else 2


if __name__ == "__main__":
    sys.exit(main())
