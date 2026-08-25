"""Run read-only project regression checks against audited artifacts and MySQL evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from build_insight_evidence_package import connection_from_env

ROOT = Path(__file__).resolve().parents[1]
ACTUAL_BATCH_ID = "9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27"
ACTUAL_ANOMALY_RUN_ID = "e9975d26-b3c2-4702-b857-622b6c7da4c1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def count_matching_blocks(artifact: dict[str, Any], block_type: str) -> int:
    return sum(block.get("type") == block_type for block in artifact["manifest"]["blocks"])


def validate_report_structure(artifact: dict[str, Any], label: str) -> dict[str, int]:
    manifest = artifact["manifest"]
    require(artifact["surface"] == "report", f"{label}: surface must be report")
    require(manifest["surface"] == "report", f"{label}: manifest surface must be report")
    require(artifact["snapshot"]["status"] == "ready", f"{label}: report snapshot is not ready")
    require(
        manifest["blocks"][0]["body"] == f"# {manifest['title']}",
        f"{label}: title block drift",
    )
    source_ids = {source["id"] for source in artifact["sources"]}
    require(source_ids, f"{label}: report has no sources")
    for collection in ("cards", "charts", "tables"):
        for item in manifest.get(collection, []):
            require(
                item.get("sourceId") in source_ids,
                f"{label}: {collection} item {item.get('id')} lacks a known source",
            )
    chart_ids = {chart["id"] for chart in manifest.get("charts", [])}
    table_ids = {table["id"] for table in manifest.get("tables", [])}
    for block in manifest["blocks"]:
        if block["type"] == "chart":
            require(block.get("chartId") in chart_ids, f"{label}: dangling chart block")
        if block["type"] == "table":
            require(block.get("tableId") in table_ids, f"{label}: dangling table block")
    require(count_matching_blocks(artifact, "chart") == 1, f"{label}: expected one chart block")
    require(count_matching_blocks(artifact, "table") == 1, f"{label}: expected one table block")
    return {
        "blocks": len(manifest["blocks"]),
        "cards": len(manifest.get("cards", [])),
        "charts": len(manifest.get("charts", [])),
        "tables": len(manifest.get("tables", [])),
    }


def validate_report_artifact(path: Path) -> dict[str, int]:
    return validate_report_structure(json.loads(path.read_text()), str(path))


def scalar(cursor: Any, sql: str, params: tuple[object, ...]) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    require(row is not None, "Database check unexpectedly returned no row")
    return next(iter(row.values()))


def database_checks(connection: Any, synthetic_manifest: dict[str, Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        ga4_staging_rows = scalar(
            cursor,
            "SELECT COUNT(*) AS value FROM insightops_dw.ga4_event_stg WHERE batch_id = %s",
            (ACTUAL_BATCH_ID,),
        )
        require(ga4_staging_rows == 640_055, f"GA4 Staging rows drifted: {ga4_staging_rows}")
        actual_daily_days = scalar(
            cursor,
            """
            SELECT COUNT(*) AS value
            FROM insightops_mart.ga4_daily_metric
            WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
            """,
            (ACTUAL_BATCH_ID,),
        )
        require(
            actual_daily_days == 14, f"Actual GA4 daily metric days drifted: {actual_daily_days}"
        )
        cursor.execute(
            """
            SELECT SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')) AS statistical_anomalies,
                   SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 1)
                     AS interpretable_anomalies,
                   SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 0)
                     AS suppressed_anomalies,
                   COUNT(*) AS total_results
            FROM insightops_ops.metric_anomaly_result
            WHERE run_id = %s AND source_batch_id = %s
            """,
            (ACTUAL_ANOMALY_RUN_ID, ACTUAL_BATCH_ID),
        )
        actual_anomaly = cursor.fetchone()
        require(
            actual_anomaly
            == {
                "statistical_anomalies": DecimalValue(20),
                "interpretable_anomalies": DecimalValue(0),
                "suppressed_anomalies": DecimalValue(20),
                "total_results": 112,
            },
            f"Actual GA4 anomaly guardrail drifted: {actual_anomaly}",
        )

        synthetic_results: list[dict[str, Any]] = []
        for case in synthetic_manifest["cases"]:
            cursor.execute(
                """
                SELECT status, JSON_EXTRACT(input_description, '$.synthetic_case') AS synthetic_case
                FROM insightops_ops.transformation_run
                WHERE run_id = %s
                """,
                (case["daily_run_id"],),
            )
            seeded_run = cursor.fetchone()
            require(seeded_run is not None, f"Missing synthetic seed run for {case['case_name']}")
            require(
                seeded_run["status"] == "SUCCEEDED", f"Synthetic seed failed: {case['case_name']}"
            )
            require(
                str(seeded_run["synthetic_case"]).lower() == "true",
                f"Synthetic marker missing: {case['case_name']}",
            )
            cursor.execute(
                """
                SELECT SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')) AS statistical_anomalies,
                       SUM(
                         status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')
                         AND is_business_interpretable = 1
                       ) AS business_interpretable_anomalies
                FROM insightops_ops.metric_anomaly_result
                WHERE run_id = %s AND source_batch_id = %s
                """,
                (case["anomaly_run_id"], case["batch_id"]),
            )
            observed = cursor.fetchone()
            cursor.execute(
                """
                SELECT COUNT(*) AS contribution_count
                FROM insightops_ops.metric_anomaly_contribution AS contribution
                JOIN insightops_ops.metric_anomaly_result AS anomaly
                  ON anomaly.anomaly_id = contribution.anomaly_id
                WHERE anomaly.run_id = %s
                """,
                (case["anomaly_run_id"],),
            )
            contribution_count = cursor.fetchone()["contribution_count"]
            expected = case["expected"]
            require(
                int(observed["statistical_anomalies"] or 0) == expected["statistical_anomalies"],
                f"Synthetic statistical anomaly drift: {case['case_name']}",
            )
            require(
                int(observed["business_interpretable_anomalies"] or 0)
                == expected["business_interpretable_anomalies"],
                f"Synthetic interpretability drift: {case['case_name']}",
            )
            require(
                contribution_count == expected["contributions"],
                f"Synthetic contribution drift: {case['case_name']}",
            )
            synthetic_results.append(
                {
                    "case_name": case["case_name"],
                    "statistical_anomalies": int(observed["statistical_anomalies"] or 0),
                    "business_interpretable_anomalies": int(
                        observed["business_interpretable_anomalies"] or 0
                    ),
                    "contributions": contribution_count,
                }
            )
    return {
        "ga4_staging_rows": ga4_staging_rows,
        "actual_daily_metric_days": actual_daily_days,
        "actual_anomaly_guardrail": {key: int(value) for key, value in actual_anomaly.items()},
        "synthetic_cases": synthetic_results,
    }


def DecimalValue(value: int) -> int:
    """Keep expected aggregate literals visually distinct from nullable MySQL sums."""

    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--synthetic-manifest",
        type=Path,
        default=Path("artifacts/evidence_packages/synthetic/synthetic_ga4_anomaly_manifest.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/regression/latest.json"))
    arguments = parser.parse_args()
    output_path = (ROOT / arguments.output).resolve()
    receipt: dict[str, Any] = {"checked_at": datetime.now(UTC).isoformat()}
    try:
        synthetic_manifest = json.loads((ROOT / arguments.synthetic_manifest).read_text())
        require(synthetic_manifest["synthetic_case"] is True, "Synthetic manifest marker missing")
        report_checks = {
            "normal_week": validate_report_artifact(
                ROOT / "artifacts/reports/normal_week/artifact.json"
            ),
            "synthetic_anomaly": validate_report_artifact(
                ROOT / "artifacts/reports/synthetic_anomaly/artifact.json"
            ),
        }
        connection = connection_from_env(arguments.env_file)
        try:
            data_checks = database_checks(connection, synthetic_manifest)
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
