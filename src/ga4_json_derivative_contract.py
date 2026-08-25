"""Stable contracts shared by the GA4 nested-JSON derivative jobs."""

from __future__ import annotations

DERIVATIVE_VERSION = "ga4_json_v1"

# These keys support the first product, promotion, checkout, and engagement audits.
# Keep this list intentionally small: it prevents unbounded schema growth from arbitrary
# event parameters while preserving the original JSON payload in Raw for later expansion.
PARAMETER_ALLOWLIST = (
    "coupon",
    "creative_name",
    "creative_slot",
    "currency",
    "engagement_time_msec",
    "entrances",
    "item_list_id",
    "item_list_index",
    "item_list_name",
    "page_referrer",
    "page_title",
    "payment_type",
    "percent_scrolled",
    "promotion_id",
    "promotion_name",
    "search_term",
    "session_engaged",
    "shipping_tier",
    "value",
)


def allowlist_sql_literals() -> str:
    """Return trusted SQL literals for the versioned, code-owned allowlist."""

    return ", ".join(f"'{name}'" for name in PARAMETER_ALLOWLIST)
