"""Restricted, evidence-only Insight Agent contracts and deterministic response policy."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceReference(BaseModel):
    """A stable pointer to one reviewed query result inside an evidence package."""

    query_id: str
    run_id: str
    metric_id: str
    metric_date: date
    source_table: str


class EvidenceFinding(BaseModel):
    """A statistical result that the agent may describe, subject to its interpretation flag."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str
    metric_date: date
    status: Literal["ANOMALY_HIGH", "ANOMALY_LOW"]
    metric_value: float
    baseline_median: float | None
    baseline_mad: float | None
    is_business_interpretable: bool
    interpretation_note: str | None
    evidence: EvidenceReference


class EvidencePackage(BaseModel):
    """Bounded, versioned facts the restricted agent is permitted to read."""

    model_config = ConfigDict(extra="forbid")

    package_version: Literal["insight_evidence_v1"]
    generated_at: datetime
    source_batch_id: str
    daily_metric_run_id: str
    anomaly_run_id: str
    metric_definition_version: str
    anomaly_definition_version: str
    statistical_anomaly_count: int = Field(ge=0)
    business_interpretable_anomaly_count: int = Field(ge=0)
    suppressed_anomaly_count: int = Field(ge=0)
    contribution_count: int = Field(ge=0)
    findings: list[EvidenceFinding]
    limitations: list[str]


class InsightClaim(BaseModel):
    """A user-facing statement with a reference to the only evidence that supports it."""

    model_config = ConfigDict(extra="forbid")

    claim_type: Literal["business_finding", "data_quality_diagnostic", "limitation"]
    text: str
    evidence: list[EvidenceReference]


class InsightResponse(BaseModel):
    """Structured output contract for a non-generative, reviewable MVP agent."""

    model_config = ConfigDict(extra="forbid")

    response_version: Literal["insight_response_v1"] = "insight_response_v1"
    question: str
    claims: list[InsightClaim]
    recommended_next_steps: list[str]
    human_review_required: bool = True


class HumanReviewRecord(BaseModel):
    """A local, non-operational record of a human decision about one agent response."""

    model_config = ConfigDict(extra="forbid")

    review_version: Literal["human_review_v1"] = "human_review_v1"
    reviewed_at: datetime
    evidence_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_batch_id: str
    anomaly_run_id: str
    decision: Literal["needs_investigation", "confirmed_data_quality", "not_adopted"]
    reviewer_role: str = Field(min_length=2, max_length=80)
    rationale: str = Field(min_length=10, max_length=2_000)
    automated_action_taken: Literal[False] = False


def answer_from_evidence(question: str, package: EvidencePackage) -> InsightResponse:
    """Produce a bounded response without model calls, SQL, or access to raw records."""

    claims: list[InsightClaim] = []
    business_findings = [
        finding for finding in package.findings if finding.is_business_interpretable
    ]
    suppressed_findings = [
        finding for finding in package.findings if not finding.is_business_interpretable
    ]

    for finding in business_findings:
        direction = "升高" if finding.status == "ANOMALY_HIGH" else "降低"
        claims.append(
            InsightClaim(
                claim_type="business_finding",
                text=(
                    f"{finding.metric_date.isoformat()} 的 {finding.metric_id} "
                    f"出现统计性{direction}，"
                    "可进入人工业务复核；该结果不证明因果。"
                ),
                evidence=[finding.evidence],
            )
        )

    if suppressed_findings:
        claims.append(
            InsightClaim(
                claim_type="data_quality_diagnostic",
                text=(
                    f"检测到 {len(suppressed_findings)} 条统计异常，但均未满足业务解释守护条件。"
                    "它们只能用于定位数据覆盖、导出或埋点问题，不能写作订单、收入、渠道或设备表现变化。"
                ),
                evidence=[finding.evidence for finding in suppressed_findings],
            )
        )

    for limitation in package.limitations:
        claims.append(InsightClaim(claim_type="limitation", text=limitation, evidence=[]))

    next_steps = [
        "人工核验交易号缺失或占位是否来自导出限制、埋点变更或上游数据缺口。",
        "接入具有稳定交易号的完整数据后，重跑同一覆盖守护与异常检测流程。",
    ]
    if business_findings:
        next_steps.insert(0, "对允许业务解释的统计结果进行人工复核，并寻找独立业务证据。")
    return InsightResponse(question=question, claims=claims, recommended_next_steps=next_steps)
