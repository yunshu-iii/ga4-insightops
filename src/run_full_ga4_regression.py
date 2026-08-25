"""Read-only regression checks for the accepted 92-day full-payload GA4 batch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from build_insight_evidence_package import connection_from_env
from build_report_artifacts import (
    FULL_GA4_ANOMALY_RUN_ID,
    FULL_GA4_BATCH_ID,
    FULL_GA4_DAILY_RUN_ID,
    FULL_GA4_QUALITY_RUN_ID,
)
from run_project_regression import require, validate_report_artifact

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "rows_loaded": 4_295_584,
    "staging_rows": 4_295_584,
    "daily_days": 92,
    "purchase_events": 5_692,
    "valid_transaction_id_purchase_events": 4_786,
    "canonical_orders": 4_451,
    "statistical_anomalies": 71,
    "business_interpretable_anomalies": 24,
    "suppressed_anomalies": 47,
    "total_results": 736,
    "contribution_count": 15,
}


def row_as_ints(row: dict[str, Any]) -> dict[str, Any]:
    return {key: int(value) if value is not None else None for key, value in row.items()}


def database_checks(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, rows_loaded
            FROM insightops_ops.ingestion_batch
            WHERE batch_id = %s
            """,
            (FULL_GA4_BATCH_ID,),
        )
        ingestion = cursor.fetchone()
        require(ingestion is not None, "Full GA4 ingestion receipt is missing")
        require(ingestion["status"] == "SUCCEEDED", "Full GA4 ingestion did not succeed")
        require(
            ingestion["rows_loaded"] == EXPECTED["rows_loaded"],
            f"Full GA4 ingestion rows drifted: {ingestion['rows_loaded']}",
        )
        cursor.execute(
            "SELECT COUNT(*) AS value FROM insightops_raw.ga4_event_raw WHERE batch_id = %s",
            (FULL_GA4_BATCH_ID,),
        )
        raw_rows = cursor.fetchone()["value"]
        cursor.execute(
            "SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_stg WHERE batch_id = %s",
            (FULL_GA4_BATCH_ID,),
        )
        staging_rows = cursor.fetchone()["value"]
        require(raw_rows == EXPECTED["rows_loaded"], f"Full GA4 Raw rows drifted: {raw_rows}")
        require(
            staging_rows == EXPECTED["staging_rows"],
            f"Full GA4 staging rows drifted: {staging_rows}",
        )
        cursor.execute(
            """
            SELECT status, total_rows, failed_rules, blocker_failed_rules
            FROM insightops_ops.data_quality_run
            WHERE run_id = %s AND batch_id = %s
            """,
            (FULL_GA4_QUALITY_RUN_ID, FULL_GA4_BATCH_ID),
        )
        quality = cursor.fetchone()
        require(quality is not None, "Full GA4 quality receipt is missing")
        require(quality["status"] == "SUCCEEDED", "Full GA4 quality run did not succeed")
        require(quality["total_rows"] == EXPECTED["rows_loaded"], "Quality row count drifted")
        require(quality["blocker_failed_rules"] == 0, "A full GA4 BLOCKER rule failed")
        cursor.execute(
            """
            SELECT COUNT(*) AS daily_days,
                   SUM(purchase_events) AS purchase_events,
                   SUM(valid_transaction_id_purchase_events)
                     AS valid_transaction_id_purchase_events,
                   SUM(canonical_orders) AS canonical_orders
            FROM insightops_mart.ga4_daily_metric
            WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
            """,
            (FULL_GA4_BATCH_ID,),
        )
        daily = row_as_ints(cursor.fetchone())
        for key in (
            "daily_days",
            "purchase_events",
            "valid_transaction_id_purchase_events",
            "canonical_orders",
        ):
            require(daily[key] == EXPECTED[key], f"Full GA4 {key} drifted: {daily[key]}")
        cursor.execute(
            """
            SELECT COUNT(*) AS total_results,
                   SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')) AS statistical_anomalies,
                   SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 1)
                     AS business_interpretable_anomalies,
                   SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 0)
                     AS suppressed_anomalies
            FROM insightops_ops.metric_anomaly_result
            WHERE run_id = %s AND source_batch_id = %s
            """,
            (FULL_GA4_ANOMALY_RUN_ID, FULL_GA4_BATCH_ID),
        )
        anomaly = row_as_ints(cursor.fetchone())
        for key in (
            "total_results",
            "statistical_anomalies",
            "business_interpretable_anomalies",
            "suppressed_anomalies",
        ):
            require(anomaly[key] == EXPECTED[key], f"Full GA4 {key} drifted: {anomaly[key]}")
        cursor.execute(
            """
            SELECT COUNT(*) AS value
            FROM insightops_ops.metric_anomaly_contribution AS contribution
            JOIN insightops_ops.metric_anomaly_result AS anomaly
              ON anomaly.anomaly_id = contribution.anomaly_id
            WHERE anomaly.run_id = %s
            """,
            (FULL_GA4_ANOMALY_RUN_ID,),
        )
        contributions = cursor.fetchone()["value"]
        require(
            contributions == EXPECTED["contribution_count"],
            f"Full GA4 contribution count drifted: {contributions}",
        )
    return {
        "batch_id": FULL_GA4_BATCH_ID,
        "daily_run_id": FULL_GA4_DAILY_RUN_ID,
        "anomaly_run_id": FULL_GA4_ANOMALY_RUN_ID,
        "quality_run_id": FULL_GA4_QUALITY_RUN_ID,
        "raw_rows": raw_rows,
        "staging_rows": staging_rows,
        "quality": quality,
        "daily": daily,
        "anomaly": anomaly,
        "contribution_count": contributions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/regression/full_ga4_latest.json")
    )
    arguments = parser.parse_args()
    output_path = (ROOT / arguments.output).resolve()
    receipt: dict[str, Any] = {"checked_at": datetime.now(UTC).isoformat()}
    try:
        report_checks = validate_report_artifact(
            ROOT / "artifacts/reports/full_ga4_92d/artifact.json"
        )
        connection = connection_from_env(arguments.env_file)
        try:
            data_checks = database_checks(connection)
        finally:
            connection.close()
        receipt.update(status="PASSED", report_checks=report_checks, data_checks=data_checks)
    except Exception as exc:
        receipt.update(status="FAILED", error=str(exc))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        raise
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
