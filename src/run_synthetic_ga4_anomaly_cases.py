"""Run isolated synthetic anomaly cases through detection, evidence, and the Insight Agent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from build_insight_evidence_package import build_package, connection_from_env
from insight_agent import answer_from_evidence
from synthetic_ga4_cases import SYNTHETIC_CASES, case_rows, dimension_rows, synthetic_batch_id

DAILY_VERSION = "ga4_daily_metrics_v2"
ROOT = Path(__file__).resolve().parents[1]


def root_connection(env_file: Path) -> pymysql.Connection:
    load_dotenv(env_file)
    password = os.environ.get("MYSQL_ROOT_PASSWORD")
    if not password:
        raise RuntimeError("未找到 MYSQL_ROOT_PASSWORD；请提供 .env 文件")
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )


def write_case(connection: pymysql.Connection, case_name: str, daily_run_id: str) -> str:
    """Write only an isolated derived-metric fixture, annotated as synthetic in run audit."""

    batch_id = synthetic_batch_id(case_name)
    daily = case_rows(case_name)
    dimensions = dimension_rows(case_name)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO insightops_ops.transformation_run (
              run_id, job_name, definition_version, status, input_description
            ) VALUES (%s, 'seed_synthetic_ga4_daily_metrics', %s, 'RUNNING', %s)
            """,
            (
                daily_run_id,
                DAILY_VERSION,
                json.dumps(
                    {
                        "synthetic_case": True,
                        "case_name": case_name,
                        "scope": "derived_metrics_only",
                    }
                ),
            ),
        )
        cursor.executemany(
            """
            INSERT INTO insightops_mart.ga4_daily_metric (
              source_batch_id, build_run_id, definition_version, metric_date,
              observed_sessions, checkout_start_sessions, canonical_order_sessions,
              canonical_orders, canonical_revenue_usd, checkout_to_canonical_order_rate,
              purchase_events, valid_transaction_id_purchase_events,
              valid_transaction_id_coverage
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              build_run_id = VALUES(build_run_id),
              observed_sessions = VALUES(observed_sessions),
              checkout_start_sessions = VALUES(checkout_start_sessions),
              canonical_order_sessions = VALUES(canonical_order_sessions),
              canonical_orders = VALUES(canonical_orders),
              canonical_revenue_usd = VALUES(canonical_revenue_usd),
              checkout_to_canonical_order_rate = VALUES(checkout_to_canonical_order_rate),
              purchase_events = VALUES(purchase_events),
              valid_transaction_id_purchase_events = VALUES(valid_transaction_id_purchase_events),
              valid_transaction_id_coverage = VALUES(valid_transaction_id_coverage)
            """,
            [
                (
                    batch_id,
                    daily_run_id,
                    DAILY_VERSION,
                    row["metric_date"],
                    row["observed_sessions"],
                    row["checkout_start_sessions"],
                    row["canonical_order_sessions"],
                    row["canonical_orders"],
                    row["canonical_revenue_usd"],
                    row["checkout_to_canonical_order_rate"],
                    row["purchase_events"],
                    row["valid_transaction_id_purchase_events"],
                    row["valid_transaction_id_coverage"],
                )
                for row in daily
            ],
        )
        cursor.executemany(
            """
            INSERT INTO insightops_mart.ga4_daily_dimension_metric (
              source_batch_id, build_run_id, definition_version, metric_date, dimension_name,
              dimension_value, observed_sessions, checkout_start_sessions,
              canonical_order_sessions, canonical_orders, canonical_revenue_usd
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              build_run_id = VALUES(build_run_id),
              observed_sessions = VALUES(observed_sessions),
              checkout_start_sessions = VALUES(checkout_start_sessions),
              canonical_order_sessions = VALUES(canonical_order_sessions),
              canonical_orders = VALUES(canonical_orders),
              canonical_revenue_usd = VALUES(canonical_revenue_usd)
            """,
            [
                (
                    batch_id,
                    daily_run_id,
                    DAILY_VERSION,
                    row["metric_date"],
                    row["dimension_name"],
                    row["dimension_value"],
                    row["observed_sessions"],
                    row["checkout_start_sessions"],
                    row["canonical_order_sessions"],
                    row["canonical_orders"],
                    row["canonical_revenue_usd"],
                )
                for row in dimensions
            ],
        )
        cursor.execute(
            """
            UPDATE insightops_ops.transformation_run
            SET status = 'SUCCEEDED', rows_written = %s, finished_at = UTC_TIMESTAMP(6)
            WHERE run_id = %s
            """,
            (len(daily) + len(dimensions), daily_run_id),
        )
    connection.commit()
    return batch_id


def run_case(case_name: str, env_file: Path, output_directory: Path) -> dict[str, object]:
    """Run one fixture through the real detector, evidence builder, agent, and assertions."""

    case = SYNTHETIC_CASES[case_name]
    daily_run_id = str(uuid.uuid4())
    anomaly_run_id = str(uuid.uuid4())
    connection = root_connection(env_file)
    try:
        batch_id = write_case(connection, case_name, daily_run_id)
    finally:
        connection.close()

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "src" / "run_ga4_anomaly_detection.py"),
            "--batch-id",
            batch_id,
            "--run-id",
            anomaly_run_id,
            "--env-file",
            str(env_file),
        ],
        check=True,
        cwd=ROOT,
    )
    connection = connection_from_env(env_file)
    try:
        package = build_package(connection, batch_id, daily_run_id, anomaly_run_id)
    finally:
        connection.close()
    response = answer_from_evidence("该场景是否可作为业务异常解释？", package)

    business_claims = sum(claim.claim_type == "business_finding" for claim in response.claims)
    data_quality_claims = sum(
        claim.claim_type == "data_quality_diagnostic" for claim in response.claims
    )
    observed = {
        "statistical_anomalies": package.statistical_anomaly_count,
        "business_interpretable_anomalies": package.business_interpretable_anomaly_count,
        "contributions": package.contribution_count,
        "business_claims": business_claims,
        "data_quality_claims": data_quality_claims,
    }
    expected = {
        "statistical_anomalies": case.expected_statistical_anomalies,
        "business_interpretable_anomalies": case.expected_interpretable_anomalies,
        "contributions": case.expected_contributions,
        "business_claims": case.expected_business_claims,
        "data_quality_claims": case.expected_data_quality_claims,
    }
    if observed != expected:
        raise AssertionError(
            f"{case_name} Golden Question failed: expected={expected}, observed={observed}"
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    package_path = output_directory / f"synthetic_{case_name}_evidence.json"
    response_path = output_directory / f"synthetic_{case_name}_agent_response.json"
    package_path.write_text(
        json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )
    response_path.write_text(
        json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )
    return {
        "synthetic_case": True,
        "case_name": case_name,
        "batch_id": batch_id,
        "daily_run_id": daily_run_id,
        "anomaly_run_id": anomaly_run_id,
        "observed": observed,
        "expected": expected,
        "evidence_package": str(package_path.relative_to(ROOT)),
        "agent_response": str(response_path.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output-directory", type=Path, default=Path("artifacts/evidence_packages/synthetic")
    )
    parser.add_argument("--case", choices=sorted(SYNTHETIC_CASES), action="append")
    arguments = parser.parse_args()
    selected_cases = arguments.case or list(SYNTHETIC_CASES)
    output_directory = (ROOT / arguments.output_directory).resolve()
    results = [
        run_case(case_name, arguments.env_file, output_directory) for case_name in selected_cases
    ]
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "synthetic_case": True,
        "cases": results,
    }
    manifest_path = output_directory / "synthetic_ga4_anomaly_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
