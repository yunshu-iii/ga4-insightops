import pandas as pd

from run_ga4_anomaly_detection import anomaly_status, business_interpretability


def test_zero_mad_rule_detects_only_a_directional_change() -> None:
    assert anomaly_status(10, 10, 0) == ("NORMAL", None)
    assert anomaly_status(11, 10, 0) == ("ANOMALY_HIGH", None)
    assert anomaly_status(9, 10, 0) == ("ANOMALY_LOW", None)


def test_coverage_guardrail_only_suppresses_order_key_metrics() -> None:
    low_coverage = pd.Series([1.0, 0.5, 1.0])

    order_interpretable, order_note = business_interpretability(
        "ga4_canonical_orders", low_coverage
    )
    purchase_interpretable, purchase_note = business_interpretability(
        "ga4_purchase_event_count", low_coverage
    )
    coverage_interpretable, coverage_note = business_interpretability(
        "ga4_valid_transaction_id_coverage", low_coverage
    )

    assert not order_interpretable
    assert order_note is not None
    assert purchase_interpretable
    assert purchase_note is None
    assert not coverage_interpretable
    assert coverage_note is not None
