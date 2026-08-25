"""Deterministic derived-metric fixtures for synthetic GA4 anomaly tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class SyntheticCase:
    """A bounded scenario and its expected observable controls."""

    name: str
    day_count: int
    coverage: float
    expected_statistical_anomalies: int
    expected_interpretable_anomalies: int
    expected_contributions: int
    expected_business_claims: int
    expected_data_quality_claims: int


SYNTHETIC_CASES = {
    "business_interpretable": SyntheticCase(
        name="business_interpretable",
        day_count=8,
        coverage=1.0,
        expected_statistical_anomalies=2,
        expected_interpretable_anomalies=2,
        expected_contributions=8,
        expected_business_claims=2,
        expected_data_quality_claims=0,
    ),
    "coverage_suppressed": SyntheticCase(
        name="coverage_suppressed",
        day_count=8,
        coverage=0.5,
        expected_statistical_anomalies=2,
        expected_interpretable_anomalies=0,
        expected_contributions=0,
        expected_business_claims=0,
        expected_data_quality_claims=1,
    ),
    "insufficient_history": SyntheticCase(
        name="insufficient_history",
        day_count=4,
        coverage=1.0,
        expected_statistical_anomalies=0,
        expected_interpretable_anomalies=0,
        expected_contributions=0,
        expected_business_claims=0,
        expected_data_quality_claims=0,
    ),
}

SYNTHETIC_START_DATE = date(2024, 1, 1)


def synthetic_batch_id(case_name: str) -> str:
    """Return a stable, non-production batch identifier for one test case."""

    return str(uuid5(NAMESPACE_URL, f"insightops.synthetic.ga4.{case_name}"))


def case_rows(case_name: str) -> list[dict[str, object]]:
    """Build direct daily metric rows with a final-day order/revenue spike when needed."""

    case = SYNTHETIC_CASES[case_name]
    rows: list[dict[str, object]] = []
    for index in range(case.day_count):
        is_final_spike = case.day_count >= 8 and index == case.day_count - 1
        canonical_orders = 40 if is_final_spike else 10
        rows.append(
            {
                "metric_date": SYNTHETIC_START_DATE + timedelta(days=index),
                "observed_sessions": 200,
                "checkout_start_sessions": 20,
                "canonical_order_sessions": 10,
                "canonical_orders": canonical_orders,
                "canonical_revenue_usd": canonical_orders * 100,
                "checkout_to_canonical_order_rate": 0.5,
                "purchase_events": 100,
                "valid_transaction_id_purchase_events": int(100 * case.coverage),
                "valid_transaction_id_coverage": case.coverage,
            }
        )
    return rows


def dimension_rows(case_name: str) -> list[dict[str, object]]:
    """Build mutually reconcilable device and acquisition cuts for contribution tests."""

    case = SYNTHETIC_CASES[case_name]
    rows: list[dict[str, object]] = []
    definitions = (
        ("device_category", (("mobile", 6, 30), ("desktop", 4, 10))),
        (
            "acquisition_channel",
            (("direct / none", 7, 28), ("email / newsletter", 3, 12)),
        ),
    )
    for index in range(case.day_count):
        is_final_spike = case.day_count >= 8 and index == case.day_count - 1
        metric_date = SYNTHETIC_START_DATE + timedelta(days=index)
        for dimension_name, values in definitions:
            for dimension_value, baseline_orders, spike_orders in values:
                canonical_orders = spike_orders if is_final_spike else baseline_orders
                rows.append(
                    {
                        "metric_date": metric_date,
                        "dimension_name": dimension_name,
                        "dimension_value": dimension_value,
                        "observed_sessions": 0,
                        "checkout_start_sessions": 0,
                        "canonical_order_sessions": 0,
                        "canonical_orders": canonical_orders,
                        "canonical_revenue_usd": canonical_orders * 100,
                    }
                )
    return rows
