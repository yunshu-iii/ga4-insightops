"""Record quality gates for independently expanded GA4 item and parameter arrays."""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from build_insight_evidence_package import connection_from_env
from ga4_json_derivative_contract import DERIVATIVE_VERSION, allowlist_sql_literals


@dataclass(frozen=True)
class QualityRule:
    rule_id: str
    severity: str
    failed_count_sql: str


def scalar(cursor: object, sql: str, parameters: tuple[object, ...]) -> int:
    cursor.execute(sql, parameters)
    row = cursor.fetchone()
    return int(next(iter(row.values())))


def run_quality_set(
    connection: object,
    *,
    run_id: str,
    batch_id: str,
    dataset_name: str,
    total_rows: int,
    rules: list[QualityRule],
) -> tuple[str, int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO insightops_ops.data_quality_run (
              run_id, batch_id, dataset_name, rule_set_version, status, total_rows
            ) VALUES (%s, %s, %s, %s, 'RUNNING', %s)
            """,
            (run_id, batch_id, dataset_name, DERIVATIVE_VERSION, total_rows),
        )
    connection.commit()
    failed_rules = 0
    blocker_failed_rules = 0
    try:
        with connection.cursor() as cursor:
            for rule in rules:
                failed_rows = scalar(
                    cursor,
                    rule.failed_count_sql,
                    tuple([batch_id] * rule.failed_count_sql.count("%s")),
                )
                outcome = "FAILED" if failed_rows else "PASSED"
                cursor.execute(
                    """
                    INSERT INTO insightops_ops.data_quality_result (
                      run_id, rule_id, severity, failed_rows, failed_rate, outcome
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        rule.rule_id,
                        rule.severity,
                        failed_rows,
                        failed_rows / total_rows if total_rows else 0,
                        outcome,
                    ),
                )
                failed_rules += int(failed_rows > 0)
                blocker_failed_rules += int(failed_rows > 0 and rule.severity == "BLOCKER")
        status = "BLOCKED" if blocker_failed_rules else "SUCCEEDED"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.data_quality_run
                SET status = %s, failed_rules = %s, blocker_failed_rules = %s,
                    finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (status, failed_rules, blocker_failed_rules, run_id),
            )
        connection.commit()
        return status, failed_rules, blocker_failed_rules
    except Exception as exc:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE insightops_ops.data_quality_run
                SET status = 'FAILED', finished_at = UTC_TIMESTAMP(6), error_message = %s
                WHERE run_id = %s
                """,
                (str(exc)[:65_535], run_id),
            )
        connection.commit()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--item-run-id", default=str(uuid.uuid4()))
    parser.add_argument("--parameter-run-id", default=str(uuid.uuid4()))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    allowlist = allowlist_sql_literals()
    item_rules = [
        QualityRule(
            "B01_items_match_source_array",
            "BLOCKER",
            """
            WITH expected AS (
              SELECT raw.raw_event_id, COALESCE(JSON_LENGTH(raw.items_json), 0) AS expected_rows
              FROM insightops_raw.ga4_event_raw AS raw WHERE raw.batch_id = %s
            ), observed AS (
              SELECT raw_event_id, COUNT(*) AS observed_rows
              FROM insightops_dw.ga4_item_event_stg
              WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
              GROUP BY raw_event_id
            )
            SELECT COUNT(*) AS value FROM expected
            LEFT JOIN observed ON observed.raw_event_id = expected.raw_event_id
            WHERE expected.expected_rows <> COALESCE(observed.observed_rows, 0)
            """,
        ),
        QualityRule(
            "B02_item_key_unique",
            "BLOCKER",
            """
            SELECT COUNT(*) - COUNT(DISTINCT CONCAT(raw_event_id, ':', item_index)) AS value
            FROM insightops_dw.ga4_item_event_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
            """,
        ),
        QualityRule(
            "B03_item_array_bounded",
            "BLOCKER",
            """
            SELECT COUNT(*) AS value FROM insightops_raw.ga4_event_raw
            WHERE batch_id = %s AND COALESCE(JSON_LENGTH(items_json), 0) > 100
            """,
        ),
        QualityRule(
            "W01_item_identity_missing",
            "WARNING",
            """
            SELECT COUNT(*) AS value FROM insightops_dw.ga4_item_event_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
              AND (NULLIF(TRIM(item_id), '') IS NULL OR item_id = '(not set)')
              AND (NULLIF(TRIM(item_name), '') IS NULL OR item_name = '(not set)')
            """,
        ),
        QualityRule(
            "W02_item_amount_negative",
            "WARNING",
            """
            SELECT COUNT(*) AS value FROM insightops_dw.ga4_item_event_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
              AND (item_quantity < 0 OR item_price_usd < 0 OR item_revenue_usd < 0)
            """,
        ),
    ]
    parameter_rules = [
        QualityRule(
            "B01_allowlisted_params_match_source",
            "BLOCKER",
            f"""
            SELECT COUNT(*) AS value
            FROM insightops_raw.ga4_event_raw AS raw
            JOIN JSON_TABLE(
              raw.event_params_json,
              '$[*]' COLUMNS (parameter_name VARCHAR(128) PATH '$.key' NULL ON EMPTY)
            ) AS parameter
            LEFT JOIN insightops_dw.ga4_event_param_stg AS staged
              ON staged.raw_event_id = raw.raw_event_id
             AND staged.parameter_name = parameter.parameter_name
             AND staged.definition_version = 'ga4_json_v1'
            WHERE raw.batch_id = %s
              AND parameter.parameter_name IN ({allowlist})
              AND staged.event_param_stg_id IS NULL
            """,
        ),
        QualityRule(
            "B02_parameter_key_unique",
            "BLOCKER",
            """
            SELECT COUNT(*) - COUNT(DISTINCT CONCAT(raw_event_id, ':', parameter_name)) AS value
            FROM insightops_dw.ga4_event_param_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
            """,
        ),
        QualityRule(
            "B03_parameter_value_not_ambiguous",
            "BLOCKER",
            """
            SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_param_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1'
              AND ((value_string IS NOT NULL) + (value_int IS NOT NULL)
                   + (value_float IS NOT NULL) + (value_double IS NOT NULL)) > 1
            """,
        ),
        QualityRule(
            "W01_parameter_value_empty",
            "WARNING",
            """
            SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_param_stg
            WHERE batch_id = %s AND definition_version = 'ga4_json_v1' AND value_kind = 'null'
            """,
        ),
    ]
    connection = connection_from_env(arguments.env_file)
    try:
        with connection.cursor() as cursor:
            item_rows = scalar(
                cursor,
                """SELECT COUNT(*) AS value FROM insightops_dw.ga4_item_event_stg
                   WHERE batch_id = %s AND definition_version = 'ga4_json_v1'""",
                (arguments.batch_id,),
            )
            parameter_rows = scalar(
                cursor,
                """SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_param_stg
                   WHERE batch_id = %s AND definition_version = 'ga4_json_v1'""",
                (arguments.batch_id,),
            )
        item_status, item_failed, item_blockers = run_quality_set(
            connection,
            run_id=arguments.item_run_id,
            batch_id=arguments.batch_id,
            dataset_name="ga4_item_event_stg",
            total_rows=item_rows,
            rules=item_rules,
        )
        parameter_status, parameter_failed, parameter_blockers = run_quality_set(
            connection,
            run_id=arguments.parameter_run_id,
            batch_id=arguments.batch_id,
            dataset_name="ga4_event_param_stg",
            total_rows=parameter_rows,
            rules=parameter_rules,
        )
    finally:
        connection.close()
    print(
        "GA4 JSON 质量完成："
        f"item_run_id={arguments.item_run_id} status={item_status} failed_rules={item_failed} "
        f"parameter_run_id={arguments.parameter_run_id} status={parameter_status} "
        f"failed_rules={parameter_failed}"
    )
    return 0 if item_blockers == 0 and parameter_blockers == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
