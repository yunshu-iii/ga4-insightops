import pandas as pd

from run_ga4_anomaly_detection import anomaly_status, business_interpretability
from synthetic_ga4_cases import SYNTHETIC_CASES, case_rows, dimension_rows


def test_business_interpretable_case_has_a_traceable_order_spike() -> None:
    rows = case_rows("business_interpretable")
    dimensions = dimension_rows("business_interpretable")

    assert len(rows) == 8
    assert rows[-1]["canonical_orders"] == 40
    assert rows[-1]["valid_transaction_id_coverage"] == 1.0
    assert (
        sum(
            row["canonical_orders"]
            for row in dimensions
            if row["metric_date"] == rows[-1]["metric_date"]
            and row["dimension_name"] == "device_category"
        )
        == rows[-1]["canonical_orders"]
    )
    assert SYNTHETIC_CASES["business_interpretable"].expected_contributions == 8


def test_coverage_suppressed_case_blocks_canonical_order_interpretation() -> None:
    coverage = pd.Series([0.5] * 8)

    interpretable, note = business_interpretability("ga4_canonical_orders", coverage)

    assert not interpretable
    assert note is not None
    assert anomaly_status(40, 10, 0) == ("ANOMALY_HIGH", None)
    assert SYNTHETIC_CASES["coverage_suppressed"].expected_business_claims == 0


def test_insufficient_history_case_never_has_a_detection_baseline() -> None:
    rows = case_rows("insufficient_history")

    assert len(rows) < 5
    assert SYNTHETIC_CASES["insufficient_history"].expected_statistical_anomalies == 0
