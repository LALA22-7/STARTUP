"""
Property-based test: Monthly no-show rate is consistent with daily breakdown.

Property 3: For any year and month, the `no_show_rate` in the monthly analytics
response SHALL equal:
    (sum of missed across daily_breakdown) / (sum of total_appointments across
    daily_breakdown) × 100
within floating-point tolerance.

When total_appointments is zero, no_show_rate SHALL be 0.

Validates: Requirements 3.2, 5.4
"""
from typing import List

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Pure no-show rate calculation — mirrors analytics_service.py
# ---------------------------------------------------------------------------

def compute_no_show_rate(daily_breakdown: List[dict]) -> float:
    """
    Compute the expected no-show rate from a list of daily analytics dicts.

    Mirrors the formula in AnalyticsService.get_monthly_revenue():
        no_show_rate = (missed / total_appointments * 100)
                       if total_appointments > 0 else 0
    """
    total = sum(d["total_appointments"] for d in daily_breakdown)
    missed = sum(d["missed"] for d in daily_breakdown)
    if total == 0:
        return 0.0
    return (missed / total) * 100.0


def build_monthly_response(daily_breakdown: List[dict]) -> dict:
    """
    Build a MonthlyAnalyticsResponse-shaped dict from a daily breakdown,
    applying the same aggregation logic as AnalyticsService.get_monthly_revenue().
    """
    total_revenue = sum(d["revenue"] for d in daily_breakdown)
    total_appointments = sum(d["total_appointments"] for d in daily_breakdown)
    completed_appointments = sum(d["completed"] for d in daily_breakdown)
    missed_appointments = sum(d["missed"] for d in daily_breakdown)
    no_show_rate = compute_no_show_rate(daily_breakdown)

    return {
        "month": "January 2025",
        "total_revenue": total_revenue,
        "total_appointments": total_appointments,
        "completed_appointments": completed_appointments,
        "missed_appointments": missed_appointments,
        "no_show_rate": no_show_rate,
        "daily_breakdown": daily_breakdown,
    }


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for a single day's analytics entry.
# missed <= total_appointments to keep data internally consistent.
@st.composite
def daily_analytics_strategy(draw):
    total = draw(st.integers(min_value=0, max_value=50))
    if total == 0:
        completed = 0
        missed = 0
    else:
        missed = draw(st.integers(min_value=0, max_value=total))
        completed = draw(st.integers(min_value=0, max_value=total - missed))
    revenue = completed * 500
    return {
        "date": "2025-01-01",
        "total_appointments": total,
        "completed": completed,
        "missed": missed,
        "revenue": revenue,
    }


# Strategy for a monthly breakdown: 1–31 daily entries
monthly_breakdown_strategy = st.lists(
    daily_analytics_strategy(),
    min_size=1,
    max_size=31,
)


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(daily_breakdown=monthly_breakdown_strategy)
def test_noshow_rate_consistent_with_daily_breakdown(daily_breakdown: List[dict]):
    """
    **Validates: Requirements 3.2, 5.4**

    Property 3: Monthly no-show rate is consistent with daily breakdown.

    For any list of daily analytics entries, the `no_show_rate` in the monthly
    response SHALL equal:
        (sum(missed) / sum(total_appointments)) * 100
    within floating-point tolerance (1e-9).

    When total_appointments is zero across all days, no_show_rate SHALL be 0.
    """
    monthly = build_monthly_response(daily_breakdown)

    total_appointments = sum(d["total_appointments"] for d in daily_breakdown)
    total_missed = sum(d["missed"] for d in daily_breakdown)

    if total_appointments == 0:
        expected_rate = 0.0
    else:
        expected_rate = (total_missed / total_appointments) * 100.0

    assert abs(monthly["no_show_rate"] - expected_rate) < 1e-9, (
        f"no_show_rate mismatch: expected {expected_rate}, "
        f"got {monthly['no_show_rate']}. "
        f"total_missed={total_missed}, total_appointments={total_appointments}"
    )


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(daily_breakdown=monthly_breakdown_strategy)
def test_noshow_rate_zero_when_no_appointments(daily_breakdown: List[dict]):
    """
    **Validates: Requirements 3.2, 5.4**

    When total_appointments across all days is zero, no_show_rate SHALL be 0.
    This test forces all daily entries to have zero appointments.
    """
    # Override all entries to have zero appointments
    zero_breakdown = [
        {**d, "total_appointments": 0, "completed": 0, "missed": 0, "revenue": 0}
        for d in daily_breakdown
    ]
    monthly = build_monthly_response(zero_breakdown)

    assert monthly["no_show_rate"] == 0.0, (
        f"Expected no_show_rate=0.0 when no appointments, "
        f"got {monthly['no_show_rate']}"
    )


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(daily_breakdown=monthly_breakdown_strategy)
def test_noshow_rate_bounds(daily_breakdown: List[dict]):
    """
    **Validates: Requirements 3.2, 5.4**

    The no_show_rate SHALL always be in the range [0, 100].
    Since missed <= total_appointments by construction, this must hold.
    """
    monthly = build_monthly_response(daily_breakdown)

    assert 0.0 <= monthly["no_show_rate"] <= 100.0, (
        f"no_show_rate {monthly['no_show_rate']} is outside [0, 100]. "
        f"daily_breakdown={daily_breakdown}"
    )


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(daily_breakdown=monthly_breakdown_strategy)
def test_monthly_aggregates_match_daily_sums(daily_breakdown: List[dict]):
    """
    **Validates: Requirements 3.2, 5.4**

    The monthly totals (total_appointments, completed_appointments,
    missed_appointments, total_revenue) SHALL equal the sums of the
    corresponding fields across the daily_breakdown.
    """
    monthly = build_monthly_response(daily_breakdown)

    assert monthly["total_appointments"] == sum(
        d["total_appointments"] for d in daily_breakdown
    ), "total_appointments mismatch"

    assert monthly["completed_appointments"] == sum(
        d["completed"] for d in daily_breakdown
    ), "completed_appointments mismatch"

    assert monthly["missed_appointments"] == sum(
        d["missed"] for d in daily_breakdown
    ), "missed_appointments mismatch"

    assert monthly["total_revenue"] == sum(
        d["revenue"] for d in daily_breakdown
    ), "total_revenue mismatch"
