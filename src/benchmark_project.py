"""Record local read-only query latency baselines for InsightOps' audited MySQL tables."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from build_insight_evidence_package import connection_from_env

ROOT = Path(__file__).resolve().parents[1]
ACTUAL_BATCH_ID = "9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27"
ACTUAL_ANOMALY_RUN_ID = "e9975d26-b3c2-4702-b857-622b6c7da4c1"
REPETITIONS = 5

BENCHMARKS = {
    "ga4_purchase_coverage_daily": (
        """
        SELECT event_date, SUM(is_purchase) AS purchase_events,
               SUM(
                 is_purchase = 1
                 AND transaction_id IS NOT NULL
                 AND NULLIF(TRIM(transaction_id), '') IS NOT NULL
                 AND transaction_id NOT IN ('(not set)', 'unknown')
               ) AS valid_transaction_id_purchase_events
        FROM insightops_dw.ga4_event_stg
        WHERE batch_id = %s
        GROUP BY event_date
        ORDER BY event_date
        """,
        (ACTUAL_BATCH_ID,),
    ),
    "ga4_daily_metrics_read": (
        """
        SELECT metric_date, canonical_orders, canonical_revenue_usd,
               valid_transaction_id_coverage
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
        ORDER BY metric_date
        """,
        (ACTUAL_BATCH_ID,),
    ),
    "ga4_anomaly_results_read": (
        """
        SELECT metric_id, metric_date, status, is_business_interpretable
        FROM insightops_ops.metric_anomaly_result
        WHERE run_id = %s AND source_batch_id = %s
        ORDER BY metric_date, metric_id
        """,
        (ACTUAL_ANOMALY_RUN_ID, ACTUAL_BATCH_ID),
    ),
}


def benchmark_query(connection: Any, sql: str, params: tuple[object, ...]) -> dict[str, Any]:
    durations_ms: list[float] = []
    row_count = 0
    with connection.cursor() as cursor:
        for _ in range(REPETITIONS):
            started_at = time.perf_counter()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            durations_ms.append(round((time.perf_counter() - started_at) * 1_000, 3))
            row_count = len(rows)
    return {
        "rows_returned": row_count,
        "repetitions": REPETITIONS,
        "median_ms": round(statistics.median(durations_ms), 3),
        "min_ms": min(durations_ms),
        "max_ms": max(durations_ms),
        "samples_ms": durations_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/performance/latest.json"))
    arguments = parser.parse_args()
    output_path = (ROOT / arguments.output).resolve()
    connection = connection_from_env(arguments.env_file)
    try:
        results = {
            name: benchmark_query(connection, sql, params)
            for name, (sql, params) in BENCHMARKS.items()
        }
    finally:
        connection.close()
    receipt = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scope": "local_read_only_mysql_latency_baseline",
        "results": results,
        "note": (
            "Absolute latency is machine-dependent; compare future runs on the same environment."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
