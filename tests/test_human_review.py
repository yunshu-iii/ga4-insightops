from datetime import datetime

import pytest
from pydantic import ValidationError

from insight_agent import HumanReviewRecord


def test_human_review_record_is_non_operational_and_traceable() -> None:
    record = HumanReviewRecord(
        reviewed_at=datetime(2026, 8, 23),
        evidence_package_sha256="a" * 64,
        response_sha256="b" * 64,
        source_batch_id="batch_123",
        anomaly_run_id="run_456",
        decision="confirmed_data_quality",
        reviewer_role="数据分析协作者",
        rationale="交易号覆盖不足，不能将订单变化解释为业务增长。",
    )

    assert record.automated_action_taken is False
    assert record.anomaly_run_id == "run_456"


def test_human_review_rejects_short_rationale() -> None:
    with pytest.raises(ValidationError):
        HumanReviewRecord(
            reviewed_at=datetime(2026, 8, 23),
            evidence_package_sha256="a" * 64,
            response_sha256="b" * 64,
            source_batch_id="batch_123",
            anomaly_run_id="run_456",
            decision="needs_investigation",
            reviewer_role="数据分析协作者",
            rationale="太短",
        )
