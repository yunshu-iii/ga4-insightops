"""Run the versioned UCI Online Retail Raw data-quality gate in MySQL."""

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
RULE_SET_VERSION = "uci_retail_raw_v1"
CORE_FIELDS_MISSING = """
TRIM(invoice_no) = '' OR TRIM(stock_code) = '' OR invoice_ts IS NULL
OR TRIM(country_name) = ''
"""
EXACT_DUPLICATES = """
SELECT source_row_number
FROM (
  SELECT
    source_row_number,
    ROW_NUMBER() OVER (
      PARTITION BY invoice_no, stock_code, COALESCE(description_text, ''), quantity,
                   invoice_ts, unit_price, COALESCE(customer_id, ''), country_name
      ORDER BY source_row_number
    ) AS duplicate_rank
  FROM insightops_raw.uci_retail_line_raw
  WHERE batch_id = %s
) AS ranked
WHERE duplicate_rank > 1
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
        FROM insightops_raw.uci_retail_line_raw WHERE {RAW_FILTER}
        """,
    ),
    QualityRule(
        "B03_source_row_number_unique",
        "BLOCKER",
        f"""
        SELECT COUNT(*) - COUNT(DISTINCT source_row_number)
        FROM insightops_raw.uci_retail_line_raw WHERE {RAW_FILTER}
        """,
    ),
    QualityRule(
        "B04_date_within_batch_range",
        "BLOCKER",
        """
        SELECT COUNT(*)
        FROM insightops_raw.uci_retail_line_raw AS raw
        JOIN insightops_ops.ingestion_batch AS batch ON batch.batch_id = raw.batch_id
        WHERE raw.batch_id = %s
          AND (DATE(raw.invoice_ts) < batch.extract_start_date
               OR DATE(raw.invoice_ts) > batch.extract_end_date)
        """,
        """
        SELECT raw.source_row_number
        FROM insightops_raw.uci_retail_line_raw AS raw
        JOIN insightops_ops.ingestion_batch AS batch ON batch.batch_id = raw.batch_id
        WHERE raw.batch_id = %s
          AND (DATE(raw.invoice_ts) < batch.extract_start_date
               OR DATE(raw.invoice_ts) > batch.extract_end_date)
        """,
    ),
    QualityRule(
        "B05_core_fields_populated",
        "BLOCKER",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND ({CORE_FIELDS_MISSING})
        """,
        f"""
        SELECT source_row_number FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND ({CORE_FIELDS_MISSING})
        """,
    ),
    QualityRule(
        "W01_exact_duplicate_line",
        "WARNING",
        f"SELECT COUNT(*) FROM ({EXACT_DUPLICATES}) AS duplicates",
    ),
    QualityRule(
        "W02_cancelled_invoice_line",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND invoice_no LIKE 'C%%'
        """,
    ),
    QualityRule(
        "W03_nonpositive_quantity",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND quantity <= 0
        """,
    ),
    QualityRule(
        "W04_nonpositive_unit_price",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND unit_price <= 0
        """,
    ),
    QualityRule(
        "W05_missing_customer_id",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND customer_id IS NULL
        """,
    ),
    QualityRule(
        "W06_missing_description",
        "WARNING",
        f"""
        SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw
        WHERE {RAW_FILTER} AND description_text IS NULL
        """,
    ),
]


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
            total_rows = scalar(
                cursor,
                "SELECT COUNT(*) FROM insightops_raw.uci_retail_line_raw WHERE batch_id = %s",
                (arguments.batch_id,),
            )
            cursor.execute(
                """
                INSERT INTO insightops_ops.data_quality_run (
                  run_id, batch_id, dataset_name, rule_set_version, status, total_rows
                ) VALUES (%s, %s, 'uci_retail_line_raw', %s, 'RUNNING', %s)
                """,
                (arguments.run_id, arguments.batch_id, RULE_SET_VERSION, total_rows),
            )
        connection.commit()

        failed_rules = 0
        blocker_failed_rules = 0
        with connection.cursor() as cursor:
            for rule in RULES:
                parameters = tuple([arguments.batch_id] * rule.failed_count_sql.count("%s"))
                failed_rows = scalar(cursor, rule.failed_count_sql, parameters)
                outcome = "FAILED" if failed_rows else "PASSED"
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
                        failed_rows / total_rows if total_rows else 0,
                        outcome,
                    ),
                )
                if failed_rows:
                    failed_rules += 1
                    blocker_failed_rules += int(rule.severity == "BLOCKER")
                    if rule.rejected_rows_sql:
                        cursor.execute(rule.rejected_rows_sql, (arguments.batch_id,))
                        cursor.executemany(
                            """
                            INSERT IGNORE INTO insightops_ops.data_quality_reject (
                              run_id, batch_id, source_table, source_row_number, rule_id, severity
                            ) VALUES (%s, %s, 'uci_retail_line_raw', %s, %s, %s)
                            """,
                            [
                                (
                                    arguments.run_id,
                                    arguments.batch_id,
                                    row[0],
                                    rule.rule_id,
                                    rule.severity,
                                )
                                for row in cursor.fetchall()
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
        f"UCI 质量检查完成：run_id={arguments.run_id}，status={final_status}，"
        f"failed_rules={failed_rules}，blocker_failed_rules={blocker_failed_rules}"
    )
    return 0 if final_status == "SUCCEEDED" else 2


if __name__ == "__main__":
    sys.exit(main())
