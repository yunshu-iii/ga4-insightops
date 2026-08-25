"""Expand independent GA4 item and allowlisted-parameter arrays from approved Raw JSON."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from build_insight_evidence_package import connection_from_env
from ga4_json_derivative_contract import DERIVATIVE_VERSION, allowlist_sql_literals


def scalar(cursor: object, sql: str, parameters: tuple[object, ...]) -> int:
    cursor.execute(sql, parameters)
    row = cursor.fetchone()
    return int(next(iter(row.values())))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--source-quality-run-id", required=True)
    parser.add_argument("--run-id", default=str(uuid.uuid4()))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    allowlist = allowlist_sql_literals()
    connection = connection_from_env(arguments.env_file)
    input_description = json.dumps(
        {
            "batch_id": arguments.batch_id,
            "source_quality_run_id": arguments.source_quality_run_id,
            "definition_version": DERIVATIVE_VERSION,
            "parameter_allowlist": allowlist.split(", "),
            "array_grains": ["one row per raw event item", "one row per raw event allowlisted key"],
        },
        ensure_ascii=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status FROM insightops_ops.data_quality_run
                WHERE run_id = %s AND batch_id = %s
                """,
                (arguments.source_quality_run_id, arguments.batch_id),
            )
            quality = cursor.fetchone()
            if quality is None or quality["status"] != "SUCCEEDED":
                raise ValueError("来源 Raw 质量门禁未成功，不能展开 JSON")
            cursor.execute(
                """
                INSERT INTO insightops_ops.transformation_run (
                  run_id, job_name, definition_version, status, input_description
                ) VALUES (%s, 'build_ga4_json_derivatives', %s, 'RUNNING', %s)
                """,
                (arguments.run_id, DERIVATIVE_VERSION, input_description),
            )
        connection.commit()

        with connection.cursor() as cursor:
            source_event_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) AS value
                FROM insightops_raw.ga4_event_raw AS raw
                LEFT JOIN insightops_ops.data_quality_reject AS rejected
                  ON rejected.run_id = %s
                 AND rejected.source_row_number = raw.source_row_number
                 AND rejected.severity = 'BLOCKER'
                WHERE raw.batch_id = %s AND rejected.reject_id IS NULL
                """,
                (arguments.source_quality_run_id, arguments.batch_id),
            )
            cursor.execute(
                """
                INSERT IGNORE INTO insightops_dw.ga4_item_event_stg (
                  raw_event_id, batch_id, source_quality_run_id, build_run_id, definition_version,
                  event_date, event_name, user_pseudo_id, ga_session_id, transaction_id,
                  device_category, item_index, item_id, item_name, item_brand, item_category,
                  item_category2, item_category3, item_variant, item_list_id, item_list_name,
                  item_list_index, promotion_id, promotion_name, coupon, item_quantity,
                  item_price_usd, item_revenue_usd
                )
                SELECT
                  raw.raw_event_id, raw.batch_id, %s, %s, %s,
                  raw.event_date, raw.event_name, raw.user_pseudo_id, raw.ga_session_id,
                  raw.transaction_id, raw.device_category, item.item_index, item.item_id,
                  item.item_name, item.item_brand, item.item_category, item.item_category2,
                  item.item_category3, item.item_variant, item.item_list_id, item.item_list_name,
                  item.item_list_index, item.promotion_id, item.promotion_name, item.coupon,
                  item.item_quantity, item.item_price_usd, item.item_revenue_usd
                FROM insightops_raw.ga4_event_raw AS raw
                LEFT JOIN insightops_ops.data_quality_reject AS rejected
                  ON rejected.run_id = %s
                 AND rejected.source_row_number = raw.source_row_number
                 AND rejected.severity = 'BLOCKER'
                JOIN JSON_TABLE(
                  raw.items_json,
                  '$[*]' COLUMNS (
                    item_index FOR ORDINALITY,
                    item_id VARCHAR(256) PATH '$.item_id' NULL ON EMPTY,
                    item_name VARCHAR(512) PATH '$.item_name' NULL ON EMPTY,
                    item_brand VARCHAR(256) PATH '$.item_brand' NULL ON EMPTY,
                    item_category VARCHAR(256) PATH '$.item_category' NULL ON EMPTY,
                    item_category2 VARCHAR(256) PATH '$.item_category2' NULL ON EMPTY,
                    item_category3 VARCHAR(256) PATH '$.item_category3' NULL ON EMPTY,
                    item_variant VARCHAR(256) PATH '$.item_variant' NULL ON EMPTY,
                    item_list_id VARCHAR(256) PATH '$.item_list_id' NULL ON EMPTY,
                    item_list_name VARCHAR(512) PATH '$.item_list_name' NULL ON EMPTY,
                    item_list_index VARCHAR(256) PATH '$.item_list_index' NULL ON EMPTY,
                    promotion_id VARCHAR(256) PATH '$.promotion_id' NULL ON EMPTY,
                    promotion_name VARCHAR(512) PATH '$.promotion_name' NULL ON EMPTY,
                    coupon VARCHAR(256) PATH '$.coupon' NULL ON EMPTY,
                    item_quantity DECIMAL(18, 6) PATH '$.quantity' NULL ON EMPTY,
                    item_price_usd DECIMAL(18, 6) PATH '$.price_in_usd' NULL ON EMPTY,
                    item_revenue_usd DECIMAL(18, 6) PATH '$.item_revenue_in_usd' NULL ON EMPTY
                  )
                ) AS item
                WHERE raw.batch_id = %s AND rejected.reject_id IS NULL
                """,
                (
                    arguments.source_quality_run_id,
                    arguments.run_id,
                    DERIVATIVE_VERSION,
                    arguments.source_quality_run_id,
                    arguments.batch_id,
                ),
            )
            inserted_item_rows = cursor.rowcount
            cursor.execute(
                f"""
                INSERT IGNORE INTO insightops_dw.ga4_event_param_stg (
                  raw_event_id, batch_id, source_quality_run_id, build_run_id, definition_version,
                  event_date, event_name, user_pseudo_id, ga_session_id, parameter_name,
                  value_string, value_int, value_float, value_double, value_kind
                )
                SELECT
                  raw.raw_event_id, raw.batch_id, %s, %s, %s,
                  raw.event_date, raw.event_name, raw.user_pseudo_id, raw.ga_session_id,
                  parameter.parameter_name, parameter.value_string, parameter.value_int,
                  parameter.value_float, parameter.value_double,
                  CASE
                    WHEN parameter.value_string IS NOT NULL THEN 'string'
                    WHEN parameter.value_int IS NOT NULL THEN 'int'
                    WHEN parameter.value_float IS NOT NULL THEN 'float'
                    WHEN parameter.value_double IS NOT NULL THEN 'double'
                    ELSE 'null'
                  END
                FROM insightops_raw.ga4_event_raw AS raw
                LEFT JOIN insightops_ops.data_quality_reject AS rejected
                  ON rejected.run_id = %s
                 AND rejected.source_row_number = raw.source_row_number
                 AND rejected.severity = 'BLOCKER'
                JOIN JSON_TABLE(
                  raw.event_params_json,
                  '$[*]' COLUMNS (
                    parameter_name VARCHAR(128) PATH '$.key' NULL ON EMPTY,
                    value_string VARCHAR(2048) PATH '$.value.string_value' NULL ON EMPTY,
                    value_int BIGINT PATH '$.value.int_value' NULL ON EMPTY,
                    value_float DOUBLE PATH '$.value.float_value' NULL ON EMPTY,
                    value_double DOUBLE PATH '$.value.double_value' NULL ON EMPTY
                  )
                ) AS parameter
                WHERE raw.batch_id = %s
                  AND rejected.reject_id IS NULL
                  AND parameter.parameter_name IN ({allowlist})
                """,
                (
                    arguments.source_quality_run_id,
                    arguments.run_id,
                    DERIVATIVE_VERSION,
                    arguments.source_quality_run_id,
                    arguments.batch_id,
                ),
            )
            inserted_parameter_rows = cursor.rowcount
            item_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) AS value FROM insightops_dw.ga4_item_event_stg
                WHERE batch_id = %s AND definition_version = %s
                """,
                (arguments.batch_id, DERIVATIVE_VERSION),
            )
            parameter_rows = scalar(
                cursor,
                """
                SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_param_stg
                WHERE batch_id = %s AND definition_version = %s
                """,
                (arguments.batch_id, DERIVATIVE_VERSION),
            )
            cursor.executemany(
                """
                INSERT INTO insightops_ops.fact_build_audit (
                  run_id, source_name, source_batch_id, input_rows, excluded_rows,
                  output_rows, notes
                ) VALUES (%s, %s, %s, %s, 0, %s, %s)
                """,
                [
                    (
                        arguments.run_id,
                        "GA4_ITEM_JSON",
                        arguments.batch_id,
                        source_event_rows,
                        item_rows,
                        "每行一个 items_json 元素；不与 event_params_json 联结。",
                    ),
                    (
                        arguments.run_id,
                        "GA4_PARAM_JSON",
                        arguments.batch_id,
                        source_event_rows,
                        parameter_rows,
                        "每行一个 allowlist event_params_json 键；保留四种值类型。",
                    ),
                ],
            )
            cursor.execute(
                """
                UPDATE insightops_ops.transformation_run
                SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
                WHERE run_id = %s
                """,
                (inserted_item_rows + inserted_parameter_rows, arguments.run_id),
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
        "GA4 JSON 派生完成："
        f"run_id={arguments.run_id} source_events={source_event_rows} "
        f"item_rows={item_rows} parameter_rows={parameter_rows} "
        f"new_item_rows={inserted_item_rows} new_parameter_rows={inserted_parameter_rows}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
