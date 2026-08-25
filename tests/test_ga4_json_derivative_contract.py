from ga4_json_derivative_contract import (
    DERIVATIVE_VERSION,
    PARAMETER_ALLOWLIST,
    allowlist_sql_literals,
)


def test_json_derivative_contract_is_small_and_versioned() -> None:
    assert DERIVATIVE_VERSION == "ga4_json_v1"
    assert len(PARAMETER_ALLOWLIST) == len(set(PARAMETER_ALLOWLIST))
    assert "ga_session_id" not in PARAMETER_ALLOWLIST
    assert {"coupon", "currency", "payment_type", "page_title"} <= set(PARAMETER_ALLOWLIST)


def test_allowlist_sql_literals_are_explicit_and_quoted() -> None:
    literals = allowlist_sql_literals().split(", ")
    assert literals == [f"'{name}'" for name in PARAMETER_ALLOWLIST]
