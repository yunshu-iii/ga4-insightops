# ruff: noqa: E501
"""Build auditable Markdown and portable HTML inputs for the weekly and synthetic reports."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from build_insight_evidence_package import connection_from_env

ROOT = Path(__file__).resolve().parents[1]
ACTUAL_BATCH_ID = "9a2d8d7c-0f5b-4c57-a54d-98c59b9c5a27"
ACTUAL_DAILY_RUN_ID = "8a9acff4-fa36-4921-b1c0-8d8fe4f2ef9d"
ACTUAL_ANOMALY_RUN_ID = "e9975d26-b3c2-4702-b857-622b6c7da4c1"
FULL_GA4_BATCH_ID = "55c6501e-5403-43a4-b4d5-1a422d87b9d5"
FULL_GA4_DAILY_RUN_ID = "3d901694-d802-4231-8f02-f7d25fea7a76"
FULL_GA4_ANOMALY_RUN_ID = "5f4195cc-0b42-4fbb-bc2c-fc728b46b9b8"
FULL_GA4_QUALITY_RUN_ID = "0d9b0ba3-04fd-4adf-a1c8-e2543c79b01f"


def json_value(value: Any) -> Any:
    """Convert database values to the JSON-safe, reviewable artifact surface."""

    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def as_rows(cursor: Any) -> list[dict[str, Any]]:
    return [{key: json_value(value) for key, value in row.items()} for row in cursor.fetchall()]


def source(
    source_id: str, label: str, sql: str, tables: list[str], filters: list[str]
) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "query": {
            "engine": "mysql",
            "language": "sql",
            "sql": sql.strip(),
            "description": label,
            "tables_used": tables,
            "filters": filters,
        },
    }


def report_artifact(
    *,
    title: str,
    generated_at: str,
    sources: list[dict[str, Any]],
    datasets: dict[str, list[dict[str, Any]]],
    cards: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "generatedAt": generated_at,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": sources,
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": datasets,
        },
        "sources": sources,
    }


def normal_report(connection: Any, generated_at: str) -> tuple[str, dict[str, Any]]:
    daily_sql = """
        SELECT DATE_FORMAT(metric_date, '%%Y-%%m-%%d') AS metric_date,
               purchase_events, valid_transaction_id_purchase_events,
               valid_transaction_id_coverage, canonical_orders, canonical_revenue_usd
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
        ORDER BY metric_date
    """
    summary_sql = """
        SELECT COUNT(*) AS day_count,
               SUM(purchase_events) AS purchase_events,
               SUM(valid_transaction_id_purchase_events) AS valid_transaction_id_purchase_events,
               SUM(canonical_orders) AS canonical_orders,
               SUM(canonical_revenue_usd) AS canonical_revenue_usd
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
    """
    anomaly_sql = """
        SELECT SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')) AS statistical_anomalies,
               SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 1)
                 AS business_interpretable_anomalies,
               SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 0)
                 AS suppressed_anomalies
        FROM insightops_ops.metric_anomaly_result
        WHERE run_id = %s AND source_batch_id = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(daily_sql, (ACTUAL_BATCH_ID,))
        daily = as_rows(cursor)
        cursor.execute(summary_sql, (ACTUAL_BATCH_ID,))
        summary = as_rows(cursor)[0]
        cursor.execute(anomaly_sql, (ACTUAL_ANOMALY_RUN_ID, ACTUAL_BATCH_ID))
        anomaly_summary = as_rows(cursor)[0]
    if len(daily) != 14:
        raise AssertionError(f"Expected 14 actual GA4 days, found {len(daily)}")
    coverage_rate = summary["valid_transaction_id_purchase_events"] / summary["purchase_events"]
    zero_coverage_days = sum(row["valid_transaction_id_coverage"] == 0 for row in daily)
    summary_row = {
        **summary,
        **anomaly_summary,
        "overall_valid_transaction_id_coverage": coverage_rate,
        "zero_coverage_days": zero_coverage_days,
        "contribution_count": 0,
    }
    sources = [
        source(
            "normal_daily_metrics",
            "GA4 守护版日指标（14 日公开开发样例）",
            daily_sql.replace("%s", f"'{ACTUAL_BATCH_ID}'"),
            ["insightops_mart.ga4_daily_metric"],
            ["definition_version = ga4_daily_metrics_v2", "14 日公开开发样例"],
        ),
        source(
            "normal_anomaly_results",
            "GA4 守护版异常检测结果",
            anomaly_sql.replace("%s", f"'{ACTUAL_ANOMALY_RUN_ID}'", 1).replace(
                "%s", f"'{ACTUAL_BATCH_ID}'", 1
            ),
            ["insightops_ops.metric_anomaly_result"],
            ["run_id = e9975d26-b3c2-4702-b857-622b6c7da4c1"],
        ),
    ]
    markdown = f"""# GA4 公开样例：14 日监测周报

## Executive Summary

- **本周期不能得出业务增长或下滑结论。** 异常检测发现 {anomaly_summary["statistical_anomalies"]} 条统计异常，但其中 {anomaly_summary["business_interpretable_anomalies"]} 条满足业务解释条件；所有订单键依赖异常均受交易号覆盖守护抑制。
- **数据可用性是本周首要问题。** 648 条购买事件中仅 190 条带有效交易号，整体有效覆盖率为 {coverage_rate:.1%}；14 天中有 {zero_coverage_days} 天为 0% 覆盖率。
- **不应据此调整渠道、设备、收入或订单策略。** 当前没有可用维度贡献；下一步应补取带稳定交易号与完整嵌套字段的 GA4 数据后重跑。

## 交易号覆盖率决定了本周结论的边界

覆盖率折线展示每个自然日“购买事件中带有效交易号的比例”。前 10 天为 0%，这会使规范订单、收入及其转化率失去可靠的业务解释基础；后续回升不改变滚动基线内仍含低覆盖日的事实。

## 每日指标用于审计，不用于业务归因

下表保留日粒度购买事件、有效交易号、规范订单和收入。规范订单/收入的 0 或跳变在本样例中首先是导出或标识覆盖待核验信号，而非业务表现判断。

## Recommended Next Steps

1. 从 GA4 导出或接入包含稳定 `transaction_id`、`event_params` 与 `items` 的完整事件载荷。
2. 对完整数据重新运行 Raw 质量门禁、日指标、95% 覆盖守护和 MAD 检测。
3. 仅在覆盖守护通过后，再将订单/收入异常交由人工复核渠道与设备构成。

## Further Questions

- 交易号缺失是否来自当前 BigQuery 导出字段选择，而非站点购买埋点？
- 完整载荷是否能恢复商品、优惠券和支付等漏斗诊断字段？

## Caveats and Assumptions

- 数据为公开匿名化开发样例，仅覆盖 2020 年 11 月 1–14 日，不能代表真实生产业务。
- MAD 检测只使用此前最多 7 天、至少 5 个历史点；短观察窗不能形成稳定生产告警基线。
- 维度贡献描述构成而不证明因果；本周期守护下未生成贡献记录。
"""
    artifact = report_artifact(
        title="GA4 公开样例：14 日监测周报",
        generated_at=generated_at,
        sources=sources,
        datasets={"normal_summary": [summary_row], "normal_daily_metrics": daily},
        cards=[
            {
                "id": "normal_anomalies",
                "description": "受守护版 MAD 检测标记的统计异常数。",
                "dataset": "normal_summary",
                "sourceId": "normal_anomaly_results",
                "metrics": [
                    {"label": "统计异常", "field": "statistical_anomalies", "format": "number"},
                    {
                        "label": "可作业务解释",
                        "field": "business_interpretable_anomalies",
                        "format": "number",
                    },
                ],
            },
            {
                "id": "normal_coverage",
                "description": "购买事件中有效交易号的整体覆盖率。",
                "dataset": "normal_summary",
                "sourceId": "normal_daily_metrics",
                "metrics": [
                    {
                        "label": "有效交易号覆盖率",
                        "field": "overall_valid_transaction_id_coverage",
                        "format": "percent",
                    },
                    {"label": "购买事件", "field": "purchase_events", "format": "number"},
                ],
            },
        ],
        charts=[
            {
                "id": "normal_coverage_trend",
                "title": "每日有效交易号覆盖率",
                "subtitle": "2020 年 11 月 1–14 日；购买事件中带有效交易号的比例",
                "type": "line",
                "dataset": "normal_daily_metrics",
                "sourceId": "normal_daily_metrics",
                "valueFormat": "percent",
                "encodings": {
                    "x": {"field": "metric_date", "type": "temporal", "label": "日期"},
                    "y": {
                        "field": "valid_transaction_id_coverage",
                        "type": "quantitative",
                        "label": "有效交易号覆盖率",
                        "format": "percent",
                    },
                    "tooltip": [
                        {"field": "purchase_events", "type": "quantitative", "label": "购买事件"},
                        {
                            "field": "valid_transaction_id_purchase_events",
                            "type": "quantitative",
                            "label": "有效交易号购买事件",
                        },
                    ],
                },
            }
        ],
        tables=[
            {
                "id": "normal_daily_table",
                "title": "每日审计指标",
                "subtitle": "公开开发样例的日粒度购买、交易号覆盖、规范订单与收入",
                "dataset": "normal_daily_metrics",
                "sourceId": "normal_daily_metrics",
                "defaultSort": {"field": "metric_date", "direction": "asc"},
                "columns": [
                    {"field": "metric_date", "label": "日期", "type": "date"},
                    {"field": "purchase_events", "label": "购买事件", "format": "number"},
                    {
                        "field": "valid_transaction_id_purchase_events",
                        "label": "有效交易号购买事件",
                        "format": "number",
                    },
                    {
                        "field": "valid_transaction_id_coverage",
                        "label": "交易号覆盖率",
                        "format": "percent",
                    },
                    {"field": "canonical_orders", "label": "规范订单", "format": "number"},
                    {
                        "field": "canonical_revenue_usd",
                        "label": "规范订单收入",
                        "format": "currency",
                    },
                ],
            }
        ],
        blocks=[
            {"id": "title", "type": "markdown", "body": "# GA4 公开样例：14 日监测周报"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "body": markdown.split("## 交易号覆盖率决定了本周结论的边界")[0].split(
                    "# GA4 公开样例：14 日监测周报\n\n", 1
                )[1],
            },
            {
                "id": "coverage_metrics",
                "type": "metric-strip",
                "cardIds": ["normal_anomalies", "normal_coverage"],
            },
            {
                "id": "coverage_explanation",
                "type": "markdown",
                "sourceId": "normal_daily_metrics",
                "body": "## 交易号覆盖率决定了本周结论的边界\n\n覆盖率折线展示每个自然日购买事件中带有效交易号的比例。前 10 天为 0%，使规范订单、收入及其转化率失去可靠的业务解释基础。",
            },
            {"id": "coverage_chart", "type": "chart", "chartId": "normal_coverage_trend"},
            {
                "id": "daily_interpretation",
                "type": "markdown",
                "sourceId": "normal_daily_metrics",
                "body": "## 每日指标用于审计，不用于业务归因\n\n规范订单/收入的 0 或跳变在本样例中首先是导出或标识覆盖待核验信号，而非业务表现判断。",
            },
            {"id": "daily_table", "type": "table", "tableId": "normal_daily_table"},
            {
                "id": "next_steps",
                "type": "markdown",
                "body": "## Recommended Next Steps\n\n1. 补取稳定交易号、`event_params` 与 `items` 的完整事件载荷。\n2. 重跑质量门禁、日指标、95% 覆盖守护和 MAD 检测。\n3. 仅在守护通过后，才复核渠道与设备构成。",
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": "## Further Questions\n\n- 交易号缺失是否来自导出字段选择，而非购买埋点？\n- 完整载荷是否能恢复商品、优惠券和支付等漏斗诊断字段？",
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": "## Caveats and Assumptions\n\n- 数据为公开匿名化开发样例，不能代表真实生产业务。\n- 短观察窗不能形成稳定生产告警基线。\n- 维度贡献描述构成而不证明因果；本周期未生成贡献记录。",
            },
        ],
    )
    return markdown, artifact


def synthetic_report(
    connection: Any, manifest_path: Path, generated_at: str
) -> tuple[str, dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text())
    case = next(item for item in manifest["cases"] if item["case_name"] == "business_interpretable")
    batch_id = case["batch_id"]
    anomaly_run_id = case["anomaly_run_id"]
    daily_sql = """
        SELECT DATE_FORMAT(metric_date, '%%Y-%%m-%%d') AS metric_date, canonical_orders,
               canonical_revenue_usd, valid_transaction_id_coverage
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
        ORDER BY metric_date
    """
    contribution_sql = """
        SELECT anomaly.metric_id, contribution.dimension_name, contribution.dimension_value,
               contribution.current_value, contribution.baseline_median,
               contribution.contribution_delta, contribution.contribution_share,
               contribution.contribution_rank
        FROM insightops_ops.metric_anomaly_contribution AS contribution
        JOIN insightops_ops.metric_anomaly_result AS anomaly
          ON anomaly.anomaly_id = contribution.anomaly_id
        WHERE anomaly.run_id = %s
        ORDER BY anomaly.metric_id, contribution.dimension_name, contribution.contribution_rank
    """
    with connection.cursor() as cursor:
        cursor.execute(daily_sql, (batch_id,))
        daily = as_rows(cursor)
        cursor.execute(contribution_sql, (anomaly_run_id,))
        contributions = as_rows(cursor)
    if len(daily) != 8 or len(contributions) != 8:
        raise AssertionError("Synthetic business report inputs do not match the Golden Question")
    last_day = daily[-1]
    summary_row = {
        "statistical_anomalies": case["observed"]["statistical_anomalies"],
        "business_interpretable_anomalies": case["observed"]["business_interpretable_anomalies"],
        "contribution_count": case["observed"]["contributions"],
        "business_claims": case["observed"]["business_claims"],
        "current_orders": last_day["canonical_orders"],
        "baseline_orders": daily[0]["canonical_orders"],
    }
    sources = [
        source(
            "synthetic_daily_metrics",
            "合成业务可解释场景的日指标",
            daily_sql.replace("%s", f"'{batch_id}'"),
            ["insightops_mart.ga4_daily_metric"],
            ["synthetic_case = true", "case_name = business_interpretable"],
        ),
        source(
            "synthetic_contributions",
            "合成业务可解释场景的维度贡献",
            contribution_sql.replace("%s", f"'{anomaly_run_id}'"),
            [
                "insightops_ops.metric_anomaly_result",
                "insightops_ops.metric_anomaly_contribution",
            ],
            ["synthetic_case = true", "维度切片单独解释，不相加"],
        ),
    ]
    markdown = f"""# 合成异常报告：覆盖守护通过时的订单尖峰

## Executive Summary

- **在 100% 有效交易号覆盖下，系统正确识别出可人工复核的统计异常。** 第 8 天规范订单从此前中位数 10 升至 40，规范订单收入从 $1,000 升至 $4,000；共 {summary_row["business_interpretable_anomalies"]} 个可解释异常。
- **贡献链路已联通但不等于因果归因。** 系统写入 {summary_row["contribution_count"]} 条贡献记录，并生成 {summary_row["business_claims"]} 条带 `run_id`、`metric_id`、日期与 `query_id` 引用的业务发现。
- **人工复核仍是必需步骤。** 该案例是明确标记的合成数据，只证明检测与守护行为符合设计，不能推断真实渠道或设备策略。

## 第 8 天的规范订单尖峰清晰可见

折线展示合成日指标中的规范订单。前 7 天固定为 10，第 8 天升至 40；滚动中位数为 10、MAD 为 0 时，规则将偏离标为方向性高异常，而不伪造无限 Z 分数。

## 贡献说明“构成”，不说明“原因”

贡献表同时提供设备和首次获客渠道两套独立切片。每个切片内部可以与总差值对账；设备与渠道之间不能相加，也不证明营销、设备或产品因素造成了尖峰。

## Recommended Next Steps

1. 在真实完整数据上先核验交易号覆盖率和订单事实，再复跑同一检测。
2. 对通过守护的异常补充独立业务证据，例如发布记录、营销活动和支付状态。
3. 由人工审阅台记录“继续调查 / 确认数据质量 / 不采纳”，不触发自动业务动作。

## Further Questions

- 真实数据中，订单尖峰是否同时出现在可靠的购买事件、支付状态和会话漏斗中？
- 两个独立维度切片是否与可核验的外部业务变化一致？

## Caveats and Assumptions

- 本报告全部来自 `synthetic_case=true` 的派生日指标测试批次，不可当作生产表现。
- 统计异常不证明因果；贡献只描述当日相对历史中位数的构成。
- Agent 输出强制 `human_review_required=true`。
"""
    artifact = report_artifact(
        title="合成异常报告：覆盖守护通过时的订单尖峰",
        generated_at=generated_at,
        sources=sources,
        datasets={
            "synthetic_summary": [summary_row],
            "synthetic_daily_metrics": daily,
            "synthetic_contributions": contributions,
        },
        cards=[
            {
                "id": "synthetic_anomalies",
                "description": "覆盖守护通过后允许进入人工复核的统计异常。",
                "dataset": "synthetic_summary",
                "sourceId": "synthetic_daily_metrics",
                "metrics": [
                    {
                        "label": "可解释异常",
                        "field": "business_interpretable_anomalies",
                        "format": "number",
                    },
                    {"label": "统计异常", "field": "statistical_anomalies", "format": "number"},
                ],
            },
            {
                "id": "synthetic_contribution_count",
                "description": "两个独立维度切片的贡献记录数。",
                "dataset": "synthetic_summary",
                "sourceId": "synthetic_contributions",
                "metrics": [
                    {"label": "贡献记录", "field": "contribution_count", "format": "number"},
                    {"label": "业务发现", "field": "business_claims", "format": "number"},
                ],
            },
        ],
        charts=[
            {
                "id": "synthetic_orders_trend",
                "title": "合成场景中的每日规范订单",
                "subtitle": "2024 年 1 月 1–8 日；第 8 天为预设尖峰，单位为订单数",
                "type": "line",
                "dataset": "synthetic_daily_metrics",
                "sourceId": "synthetic_daily_metrics",
                "valueFormat": "number",
                "encodings": {
                    "x": {"field": "metric_date", "type": "temporal", "label": "日期"},
                    "y": {"field": "canonical_orders", "type": "quantitative", "label": "规范订单"},
                    "tooltip": [
                        {
                            "field": "canonical_revenue_usd",
                            "type": "quantitative",
                            "label": "规范订单收入",
                            "format": "currency",
                        },
                        {
                            "field": "valid_transaction_id_coverage",
                            "type": "quantitative",
                            "label": "有效交易号覆盖率",
                            "format": "percent",
                        },
                    ],
                },
            }
        ],
        tables=[
            {
                "id": "synthetic_contribution_table",
                "title": "维度贡献审计表",
                "subtitle": "设备与渠道是两套独立切片；每套内部按异常指标排序",
                "dataset": "synthetic_contributions",
                "sourceId": "synthetic_contributions",
                "defaultSort": {"field": "contribution_delta", "direction": "desc"},
                "columns": [
                    {"field": "metric_id", "label": "异常指标", "type": "text"},
                    {"field": "dimension_name", "label": "切片", "type": "text"},
                    {"field": "dimension_value", "label": "维度值", "type": "text"},
                    {"field": "current_value", "label": "当日值", "format": "number"},
                    {"field": "baseline_median", "label": "历史中位数", "format": "number"},
                    {"field": "contribution_delta", "label": "差值构成", "format": "number"},
                    {"field": "contribution_share", "label": "切片内份额", "format": "percent"},
                ],
            }
        ],
        blocks=[
            {"id": "title", "type": "markdown", "body": "# 合成异常报告：覆盖守护通过时的订单尖峰"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "body": markdown.split("## 第 8 天的规范订单尖峰清晰可见")[0].split(
                    "# 合成异常报告：覆盖守护通过时的订单尖峰\n\n", 1
                )[1],
            },
            {
                "id": "synthetic_metrics",
                "type": "metric-strip",
                "cardIds": ["synthetic_anomalies", "synthetic_contribution_count"],
            },
            {
                "id": "spike_explanation",
                "type": "markdown",
                "sourceId": "synthetic_daily_metrics",
                "body": "## 第 8 天的规范订单尖峰清晰可见\n\n前 7 天固定为 10，第 8 天升至 40；滚动中位数为 10、MAD 为 0 时，规则将偏离标为方向性高异常，而不伪造无限 Z 分数。",
            },
            {"id": "orders_chart", "type": "chart", "chartId": "synthetic_orders_trend"},
            {
                "id": "contribution_explanation",
                "type": "markdown",
                "sourceId": "synthetic_contributions",
                "body": "## 贡献说明“构成”，不说明“原因”\n\n设备与首次获客渠道是两套独立切片。每个切片内部可以与总差值对账；设备与渠道之间不能相加，也不证明营销、设备或产品因素造成了尖峰。",
            },
            {
                "id": "contribution_table",
                "type": "table",
                "tableId": "synthetic_contribution_table",
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": "## Recommended Next Steps\n\n1. 在真实完整数据上先核验交易号覆盖率和订单事实。\n2. 对通过守护的异常补充独立业务证据。\n3. 由人工审阅台记录决定，不触发自动业务动作。",
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": "## Further Questions\n\n- 真实数据中，订单尖峰是否同时出现在可靠的购买事件、支付状态和会话漏斗中？\n- 两个独立维度切片是否与可核验的外部业务变化一致？",
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": "## Caveats and Assumptions\n\n- 本报告全部来自 `synthetic_case=true` 的派生日指标测试批次。\n- 统计异常不证明因果；贡献只描述构成。\n- Agent 输出强制人工复核。",
            },
        ],
    )
    return markdown, artifact


def full_ga4_report(connection: Any, generated_at: str) -> tuple[str, dict[str, Any]]:
    """Build a separate report for the 92-day full-JSON GA4 public sample."""

    daily_sql = """
        SELECT DATE_FORMAT(metric_date, '%%Y-%%m-%%d') AS metric_date,
               purchase_events, valid_transaction_id_purchase_events,
               valid_transaction_id_coverage, canonical_orders, canonical_revenue_usd
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
        ORDER BY metric_date
    """
    summary_sql = """
        SELECT COUNT(*) AS day_count,
               SUM(purchase_events) AS purchase_events,
               SUM(valid_transaction_id_purchase_events) AS valid_transaction_id_purchase_events,
               SUM(canonical_orders) AS canonical_orders,
               SUM(canonical_revenue_usd) AS canonical_revenue_usd,
               AVG(valid_transaction_id_coverage) AS average_daily_coverage,
               MIN(valid_transaction_id_coverage) AS minimum_daily_coverage,
               MAX(valid_transaction_id_coverage) AS maximum_daily_coverage
        FROM insightops_mart.ga4_daily_metric
        WHERE source_batch_id = %s AND definition_version = 'ga4_daily_metrics_v2'
    """
    anomaly_sql = """
        SELECT COUNT(*) AS total_results,
               SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW')) AS statistical_anomalies,
               SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 1)
                 AS business_interpretable_anomalies,
               SUM(status IN ('ANOMALY_HIGH', 'ANOMALY_LOW') AND is_business_interpretable = 0)
                 AS suppressed_anomalies
        FROM insightops_ops.metric_anomaly_result
        WHERE run_id = %s AND source_batch_id = %s
    """
    contribution_sql = """
        SELECT COUNT(*) AS contribution_count
        FROM insightops_ops.metric_anomaly_contribution AS contribution
        JOIN insightops_ops.metric_anomaly_result AS anomaly
          ON anomaly.anomaly_id = contribution.anomaly_id
        WHERE anomaly.run_id = %s
    """
    quality_sql = """
        SELECT run_id, batch_id, dataset_name, rule_set_version, status, total_rows,
               failed_rules, blocker_failed_rules
        FROM insightops_ops.data_quality_run
        WHERE run_id = %s AND batch_id = %s
    """
    ingestion_sql = """
        SELECT batch_id, source_system, source_file, source_sha256, extract_start_date,
               extract_end_date, status, rows_loaded
        FROM insightops_ops.ingestion_batch
        WHERE batch_id = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(daily_sql, (FULL_GA4_BATCH_ID,))
        daily = as_rows(cursor)
        cursor.execute(summary_sql, (FULL_GA4_BATCH_ID,))
        summary = as_rows(cursor)[0]
        cursor.execute(anomaly_sql, (FULL_GA4_ANOMALY_RUN_ID, FULL_GA4_BATCH_ID))
        anomaly_summary = as_rows(cursor)[0]
        cursor.execute(contribution_sql, (FULL_GA4_ANOMALY_RUN_ID,))
        contribution_summary = as_rows(cursor)[0]
        cursor.execute(quality_sql, (FULL_GA4_QUALITY_RUN_ID, FULL_GA4_BATCH_ID))
        quality = as_rows(cursor)[0]
        cursor.execute(ingestion_sql, (FULL_GA4_BATCH_ID,))
        ingestion = as_rows(cursor)[0]
    if len(daily) != 92:
        raise AssertionError(f"Expected 92 full GA4 days, found {len(daily)}")
    if quality["status"] != "SUCCEEDED" or quality["blocker_failed_rules"] != 0:
        raise AssertionError("Full GA4 quality gate did not pass its blocker checks")
    if ingestion["status"] != "SUCCEEDED" or ingestion["rows_loaded"] != 4_295_584:
        raise AssertionError("Full GA4 ingestion receipt does not match the accepted source")
    overall_coverage = summary["valid_transaction_id_purchase_events"] / summary["purchase_events"]
    zero_coverage_days = sum(row["valid_transaction_id_coverage"] == 0 for row in daily)
    summary_row = {
        **summary,
        **anomaly_summary,
        **contribution_summary,
        "overall_valid_transaction_id_coverage": overall_coverage,
        "zero_coverage_days": zero_coverage_days,
        "rows_loaded": ingestion["rows_loaded"],
    }
    sources = [
        source(
            "full_ga4_ingestion",
            "完整 GA4 公开样例接入收据",
            ingestion_sql.replace("%s", f"'{FULL_GA4_BATCH_ID}'"),
            ["insightops_ops.ingestion_batch"],
            ["batch_id = 55c6501e-5403-43a4-b4d5-1a422d87b9d5"],
        ),
        source(
            "full_ga4_quality_gate",
            "完整 GA4 Raw 质量门禁",
            quality_sql.replace("%s", f"'{FULL_GA4_QUALITY_RUN_ID}'", 1).replace(
                "%s", f"'{FULL_GA4_BATCH_ID}'", 1
            ),
            ["insightops_ops.data_quality_run"],
            ["rule_set_version = ga4_raw_v2", "仅报告 BLOCKER 通过状态"],
        ),
        source(
            "full_ga4_daily_metrics",
            "完整 GA4 守护版日指标（92 日公开样例）",
            daily_sql.replace("%s", f"'{FULL_GA4_BATCH_ID}'"),
            ["insightops_mart.ga4_daily_metric"],
            ["definition_version = ga4_daily_metrics_v2", "2020-11-01 至 2021-01-31"],
        ),
        source(
            "full_ga4_anomaly_results",
            "完整 GA4 守护版异常检测结果",
            anomaly_sql.replace("%s", f"'{FULL_GA4_ANOMALY_RUN_ID}'", 1).replace(
                "%s", f"'{FULL_GA4_BATCH_ID}'", 1
            ),
            ["insightops_ops.metric_anomaly_result"],
            ["run_id = 5f4195cc-0b42-4fbb-bc2c-fc728b46b9b8"],
        ),
    ]
    markdown = f"""# GA4 公开样例：92 日完整载荷监测报告

## Executive Summary

- **完整载荷已成功接入，但样例仍只可用于技术验证。** 2020 年 11 月 1 日至 2021 年 1 月 31 日的 {ingestion["rows_loaded"]:,} 条公开匿名化事件已通过 Raw BLOCKER 质量门禁；`event_params_json` 与 `items_json` 已保存在 Raw 层。
- **订单键可用性显著改善但并不均匀。** {summary["purchase_events"]:,} 个购买事件中 {summary["valid_transaction_id_purchase_events"]:,} 个带有效交易号，整体覆盖率为 {overall_coverage:.1%}；日均覆盖率为 {summary["average_daily_coverage"]:.1%}，仍有 {zero_coverage_days} 天为 0%。
- **异常结果是人工复核队列，不是业务结论。** {anomaly_summary["statistical_anomalies"]} 条统计异常中有 {anomaly_summary["business_interpretable_anomalies"]} 条通过当前覆盖守护、{anomaly_summary["suppressed_anomalies"]} 条被抑制；{contribution_summary["contribution_count"]} 条贡献记录仅描述构成，不证明原因。

## 完整载荷扩大了观察窗口，但没有取消覆盖守护

覆盖率折线展示每日购买事件中带有效交易号的比例。92 个日观察点足以支持趋势审计；不过 0% 覆盖日仍意味着该日订单、收入和订单转化相关指标不能被当成可靠业务表现。

## 可解释异常只能进入人工复核

异常检测为每个指标日保留统计信号和覆盖守护结果。通过守护的 24 条结果仅表示其满足当前最低数据可用性规则；在没有营销、发布、支付或商品变更等独立证据前，不能将其解释为真实业务增长、下滑或因果影响。

## 每日指标保留为审计证据

下表保留 92 天的购买事件、有效交易号覆盖、规范订单和收入，用于定位异常日期与核验守护状态，而不是直接驱动渠道、设备或收入策略。

## Recommended Next Steps

1. 为 24 条通过守护的异常建立人工审阅队列，并为每条补充发布、营销、支付和埋点变更证据。
2. 以 `items_json` 和 `event_params_json` 建立最小的商品与参数派生模型，先做 JSON 解析率、键覆盖率和一对多展开防爆炸检查。
3. 在真实生产数据接入前继续保留交易号覆盖守护；不要将公开样例的统计阈值或异常日期直接迁移为生产告警策略。

## Further Questions

- 0% 覆盖日是否集中在特定导出分段、埋点版本或购买路径？
- 通过守护的异常在商品、优惠券、支付方式和会话结账漏斗中是否有一致的非因果证据？

## Caveats and Assumptions

- 数据为 Google Analytics 公开匿名化样例，不能代表真实生产业务或用作经营决策依据。
- 当前“可作业务解释”只表示交易号覆盖守护通过，不代表因果归因、异常已确认或建议自动业务动作。
- 维度贡献按独立切片计算；不同维度之间不能相加，且所有 Agent 输出仍要求人工复核。
"""
    artifact = report_artifact(
        title="GA4 公开样例：92 日完整载荷监测报告",
        generated_at=generated_at,
        sources=sources,
        datasets={
            "full_ga4_summary": [summary_row],
            "full_ga4_daily_metrics": daily,
            "full_ga4_quality": [quality],
            "full_ga4_ingestion": [ingestion],
        },
        cards=[
            {
                "id": "full_ga4_coverage",
                "description": "92 日完整公开样例中购买事件带有效交易号的整体覆盖率。",
                "dataset": "full_ga4_summary",
                "sourceId": "full_ga4_daily_metrics",
                "metrics": [
                    {
                        "label": "有效交易号覆盖率",
                        "field": "overall_valid_transaction_id_coverage",
                        "format": "percent",
                    },
                    {"label": "规范订单", "field": "canonical_orders", "format": "number"},
                ],
            },
            {
                "id": "full_ga4_anomalies",
                "description": "MAD 统计信号在交易号覆盖守护后的人工复核候选数。",
                "dataset": "full_ga4_summary",
                "sourceId": "full_ga4_anomaly_results",
                "metrics": [
                    {
                        "label": "可供人工复核",
                        "field": "business_interpretable_anomalies",
                        "format": "number",
                    },
                    {"label": "已抑制异常", "field": "suppressed_anomalies", "format": "number"},
                ],
            },
        ],
        charts=[
            {
                "id": "full_ga4_coverage_trend",
                "title": "每日有效交易号覆盖率",
                "subtitle": "2020 年 11 月 1 日至 2021 年 1 月 31 日；购买事件中带有效交易号的比例",
                "type": "line",
                "dataset": "full_ga4_daily_metrics",
                "sourceId": "full_ga4_daily_metrics",
                "valueFormat": "percent",
                "encodings": {
                    "x": {"field": "metric_date", "type": "temporal", "label": "日期"},
                    "y": {
                        "field": "valid_transaction_id_coverage",
                        "type": "quantitative",
                        "label": "有效交易号覆盖率",
                        "format": "percent",
                    },
                    "tooltip": [
                        {"field": "purchase_events", "type": "quantitative", "label": "购买事件"},
                        {
                            "field": "valid_transaction_id_purchase_events",
                            "type": "quantitative",
                            "label": "有效交易号购买事件",
                        },
                        {"field": "canonical_orders", "type": "quantitative", "label": "规范订单"},
                    ],
                },
            }
        ],
        tables=[
            {
                "id": "full_ga4_daily_table",
                "title": "92 日每日审计指标",
                "subtitle": "公开完整载荷的日粒度购买、交易号覆盖、规范订单和收入",
                "dataset": "full_ga4_daily_metrics",
                "sourceId": "full_ga4_daily_metrics",
                "defaultSort": {"field": "metric_date", "direction": "asc"},
                "columns": [
                    {"field": "metric_date", "label": "日期", "type": "date"},
                    {"field": "purchase_events", "label": "购买事件", "format": "number"},
                    {
                        "field": "valid_transaction_id_purchase_events",
                        "label": "有效交易号购买事件",
                        "format": "number",
                    },
                    {
                        "field": "valid_transaction_id_coverage",
                        "label": "交易号覆盖率",
                        "format": "percent",
                    },
                    {"field": "canonical_orders", "label": "规范订单", "format": "number"},
                    {
                        "field": "canonical_revenue_usd",
                        "label": "规范订单收入",
                        "format": "currency",
                    },
                ],
            }
        ],
        blocks=[
            {"id": "title", "type": "markdown", "body": "# GA4 公开样例：92 日完整载荷监测报告"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "body": "## Executive Summary",
            },
            {
                "id": "full_ga4_summary_ingestion",
                "type": "markdown",
                "sourceId": "full_ga4_ingestion",
                "body": f"- **完整载荷已成功接入，但样例仍只可用于技术验证。** 2020 年 11 月 1 日至 2021 年 1 月 31 日的 {ingestion['rows_loaded']:,} 条公开匿名化事件已成功接入。",
            },
            {
                "id": "full_ga4_summary_coverage",
                "type": "markdown",
                "sourceId": "full_ga4_daily_metrics",
                "body": f"- **订单键可用性显著改善但并不均匀。** 整体有效交易号覆盖率为 {overall_coverage:.1%}，日均为 {summary['average_daily_coverage']:.1%}，仍有 {zero_coverage_days} 天为 0%。",
            },
            {
                "id": "full_ga4_summary_anomaly",
                "type": "markdown",
                "sourceId": "full_ga4_anomaly_results",
                "body": f"- **异常结果是人工复核队列，不是业务结论。** {anomaly_summary['statistical_anomalies']} 条统计异常中有 {anomaly_summary['business_interpretable_anomalies']} 条通过当前覆盖守护，{anomaly_summary['suppressed_anomalies']} 条被抑制。",
            },
            {
                "id": "full_ga4_metrics",
                "type": "metric-strip",
                "cardIds": ["full_ga4_coverage", "full_ga4_anomalies"],
            },
            {
                "id": "full_ga4_quality_context",
                "type": "markdown",
                "sourceId": "full_ga4_quality_gate",
                "body": "## 完整载荷扩大了观察窗口，但没有取消覆盖守护\n\n完整载荷的 Raw BLOCKER 质量门禁已通过，但交易号覆盖仍按日守护；0% 覆盖日不支持订单、收入或转化相关的业务解释。",
            },
            {
                "id": "full_ga4_coverage_chart",
                "type": "chart",
                "chartId": "full_ga4_coverage_trend",
            },
            {
                "id": "full_ga4_anomaly_context",
                "type": "markdown",
                "sourceId": "full_ga4_anomaly_results",
                "body": "## 可解释异常只能进入人工复核\n\n通过交易号覆盖守护的异常只是人工复核候选；在没有独立业务证据前，不可被描述为增长、下滑或因果影响。",
            },
            {
                "id": "full_ga4_daily_context",
                "type": "markdown",
                "sourceId": "full_ga4_daily_metrics",
                "body": "## 每日指标保留为审计证据\n\n日粒度指标用于定位异常日期与核验覆盖守护状态，不直接驱动渠道、设备或收入策略。",
            },
            {
                "id": "full_ga4_daily_table_block",
                "type": "table",
                "tableId": "full_ga4_daily_table",
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": "## Recommended Next Steps\n\n1. 对通过守护的异常补充独立业务证据。\n2. 建立 JSON 商品与参数派生模型的质量检查。\n3. 不将公开样例的阈值直接迁移至生产。",
            },
            {
                "id": "questions",
                "type": "markdown",
                "body": "## Further Questions\n\n- 0% 覆盖日是否集中在特定导出分段或埋点版本？\n- 商品、优惠券和支付字段是否提供一致的非因果证据？",
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": "## Caveats and Assumptions\n\n- 公开匿名化样例不可用于生产经营决策。\n- 可解释状态只表示覆盖守护通过。\n- 贡献描述构成而不证明因果，人工复核始终必需。",
            },
        ],
    )
    return markdown, artifact


def write_report(output_directory: Path, markdown: str, artifact: dict[str, Any]) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "report.md").write_text(markdown, encoding="utf-8")
    (output_directory / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-directory", type=Path, default=Path("artifacts/reports"))
    parser.add_argument(
        "--synthetic-manifest",
        type=Path,
        default=Path("artifacts/evidence_packages/synthetic/synthetic_ga4_anomaly_manifest.json"),
    )
    parser.add_argument(
        "--include-full-ga4",
        action="store_true",
        help="Also build a separate 92-day full-payload GA4 public-sample report.",
    )
    arguments = parser.parse_args()
    generated_at = datetime.now(UTC).isoformat()
    output_directory = (ROOT / arguments.output_directory).resolve()
    manifest_path = (ROOT / arguments.synthetic_manifest).resolve()
    connection = connection_from_env(arguments.env_file)
    try:
        normal_markdown, normal_artifact = normal_report(connection, generated_at)
        synthetic_markdown, synthetic_artifact = synthetic_report(
            connection, manifest_path, generated_at
        )
    finally:
        connection.close()
    write_report(output_directory / "normal_week", normal_markdown, normal_artifact)
    write_report(output_directory / "synthetic_anomaly", synthetic_markdown, synthetic_artifact)
    destinations = ["normal_week", "synthetic_anomaly"]
    if arguments.include_full_ga4:
        connection = connection_from_env(arguments.env_file)
        try:
            full_markdown, full_artifact = full_ga4_report(connection, generated_at)
        finally:
            connection.close()
        write_report(output_directory / "full_ga4_92d", full_markdown, full_artifact)
        destinations.append("full_ga4_92d")
    print(
        "Report inputs written: "
        + ", ".join(str((output_directory / item).relative_to(ROOT)) for item in destinations)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
