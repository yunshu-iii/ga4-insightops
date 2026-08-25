"""Build a bounded, query-traceable evidence package for the restricted Insight Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from insight_agent import EvidenceFinding, EvidencePackage, EvidenceReference

PACKAGE_VERSION = "insight_evidence_v1"
QUERY_ID = "ga4_v2_anomaly_results"
SOURCE_TABLE = "insightops_ops.metric_anomaly_result"


def connection_from_env(env_file: Path) -> pymysql.Connection:
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
        cursorclass=pymysql.cursors.DictCursor,
    )


def build_package(
    connection: pymysql.Connection,
    batch_id: str,
    daily_run_id: str,
    anomaly_run_id: str,
) -> EvidencePackage:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT metric_id, metric_date, metric_value, baseline_median, baseline_mad,
                   status, is_business_interpretable, interpretation_note
            FROM insightops_ops.metric_anomaly_result
            WHERE run_id = %s AND source_batch_id = %s
              AND status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')
            ORDER BY metric_date, metric_id
            """,
            (anomaly_run_id, batch_id),
        )
        rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT COUNT(*) AS contribution_count
            FROM insightops_ops.metric_anomaly_contribution AS contribution
            JOIN insightops_ops.metric_anomaly_result AS anomaly
              ON anomaly.anomaly_id = contribution.anomaly_id
            WHERE anomaly.run_id = %s
            """,
            (anomaly_run_id,),
        )
        contribution_count = int(cursor.fetchone()["contribution_count"])
        cursor.execute(
            """
            SELECT metric_date, valid_transaction_id_coverage
            FROM insightops_mart.ga4_daily_metric
            WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
            ORDER BY metric_date
            """,
            (batch_id,),
        )
        coverage_rows = cursor.fetchall()
    findings = [
        EvidenceFinding(
            metric_id=row["metric_id"],
            metric_date=row["metric_date"],
            status=row["status"],
            metric_value=float(row["metric_value"]),
            baseline_median=None
            if row["baseline_median"] is None
            else float(row["baseline_median"]),
            baseline_mad=None if row["baseline_mad"] is None else float(row["baseline_mad"]),
            is_business_interpretable=bool(row["is_business_interpretable"]),
            interpretation_note=row["interpretation_note"],
            evidence=EvidenceReference(
                query_id=QUERY_ID,
                run_id=anomaly_run_id,
                metric_id=row["metric_id"],
                metric_date=row["metric_date"],
                source_table=SOURCE_TABLE,
            ),
        )
        for row in rows
    ]
    interpretable_count = sum(finding.is_business_interpretable for finding in findings)
    low_coverage_dates = [
        row["metric_date"].isoformat()
        for row in coverage_rows
        if row["valid_transaction_id_coverage"] is None
        or float(row["valid_transaction_id_coverage"]) < 0.95
    ]
    limitations = [
        "证据包只包含已审计的日粒度统计结果，不包含原始事件或因果证明。",
        "滚动 MAD 检测需要至少 5 个历史点；短观察窗不能形成稳定生产告警基线。",
    ]
    if low_coverage_dates:
        limitations.append(
            "有效交易号覆盖率低于 95% 的日期：" + "、".join(low_coverage_dates) + "。"
        )
    else:
        limitations.append("该批次各日有效交易号覆盖率均不低于 95%；这不构成因果证明。")
    if contribution_count == 0:
        limitations.append("未生成维度贡献；不得将缺失贡献替换为因果解释。")
    return EvidencePackage(
        package_version=PACKAGE_VERSION,
        generated_at=datetime.now(UTC),
        source_batch_id=batch_id,
        daily_metric_run_id=daily_run_id,
        anomaly_run_id=anomaly_run_id,
        metric_definition_version="ga4_daily_metrics_v2",
        anomaly_definition_version="ga4_mad_anomaly_v2",
        statistical_anomaly_count=len(findings),
        business_interpretable_anomaly_count=interpretable_count,
        suppressed_anomaly_count=len(findings) - interpretable_count,
        contribution_count=contribution_count,
        findings=findings,
        limitations=limitations,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--daily-run-id", required=True)
    parser.add_argument("--anomaly-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    connection = connection_from_env(arguments.env_file)
    try:
        package = build_package(
            connection, arguments.batch_id, arguments.daily_run_id, arguments.anomaly_run_id
        )
    finally:
        connection.close()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"Insight evidence package written: {arguments.output}; "
        f"findings={package.statistical_anomaly_count}; "
        f"business_interpretable={package.business_interpretable_anomaly_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
