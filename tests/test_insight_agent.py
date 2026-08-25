from datetime import date, datetime

from insight_agent import EvidenceFinding, EvidencePackage, EvidenceReference, answer_from_evidence


def make_finding(*, interpretable: bool) -> EvidenceFinding:
    return EvidenceFinding(
        metric_id="ga4_canonical_orders",
        metric_date=date(2020, 11, 11),
        status="ANOMALY_HIGH",
        metric_value=28,
        baseline_median=0,
        baseline_mad=0,
        is_business_interpretable=interpretable,
        interpretation_note="coverage guardrail" if not interpretable else None,
        evidence=EvidenceReference(
            query_id="test_query",
            run_id="test_run",
            metric_id="ga4_canonical_orders",
            metric_date=date(2020, 11, 11),
            source_table="insightops_ops.metric_anomaly_result",
        ),
    )


def make_package(findings: list[EvidenceFinding]) -> EvidencePackage:
    interpretable_count = sum(finding.is_business_interpretable for finding in findings)
    return EvidencePackage(
        package_version="insight_evidence_v1",
        generated_at=datetime(2026, 8, 23),
        source_batch_id="test_batch",
        daily_metric_run_id="test_daily_run",
        anomaly_run_id="test_anomaly_run",
        metric_definition_version="ga4_daily_metrics_v2",
        anomaly_definition_version="ga4_mad_anomaly_v2",
        statistical_anomaly_count=len(findings),
        business_interpretable_anomaly_count=interpretable_count,
        suppressed_anomaly_count=len(findings) - interpretable_count,
        contribution_count=0,
        findings=findings,
        limitations=["test limitation"],
    )


def test_suppressed_evidence_never_becomes_a_business_finding() -> None:
    response = answer_from_evidence(
        "发生了什么？", make_package([make_finding(interpretable=False)])
    )

    assert not [claim for claim in response.claims if claim.claim_type == "business_finding"]
    diagnostic = next(
        claim for claim in response.claims if claim.claim_type == "data_quality_diagnostic"
    )
    assert "不能写作订单、收入、渠道或设备表现变化" in diagnostic.text
    assert diagnostic.evidence[0].query_id == "test_query"


def test_interpretable_evidence_keeps_a_traceable_business_finding() -> None:
    response = answer_from_evidence(
        "发生了什么？", make_package([make_finding(interpretable=True)])
    )

    finding = next(claim for claim in response.claims if claim.claim_type == "business_finding")
    assert "不证明因果" in finding.text
    assert finding.evidence[0].run_id == "test_run"
