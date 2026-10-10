"""
Unit Tests for Deterministic Calculations Engine
"""
from ridewise.calculations import (
    calculate_rental_charge,
    calculate_security_deposit,
    get_cancellation_policy_version,
    calculate_cancellation_refund,
    calculate_late_return_penalty,
    calculate_ev_battery_penalty,
    assess_damage_charge
)


def test_rental_charge_worked_examples():
    """Verify worked examples from RW-POL-01 Page 1-2."""
    # 4 hours @ 80/hr, 700/day
    r1 = calculate_rental_charge(4, 80.0, 700.0)
    assert r1["base_rental_charge"] == 320.0
    assert r1["gst_amount"] == 57.60
    assert r1["total_amount"] == 377.60

    # 10 hours @ 80/hr, 700/day -> 800 capped at 700
    r2 = calculate_rental_charge(10, 80.0, 700.0)
    assert r2["base_rental_charge"] == 700.0
    assert r2["gst_amount"] == 126.0
    assert r2["total_amount"] == 826.0

    # 24 hours @ 80/hr, 700/day
    r3 = calculate_rental_charge(24, 80.0, 700.0)
    assert r3["base_rental_charge"] == 700.0

    # 27 hours @ 80/hr, 700/day -> 1*700 + 3*80 = 940
    r4 = calculate_rental_charge(27, 80.0, 700.0)
    assert r4["base_rental_charge"] == 940.0
    assert r4["gst_amount"] == 169.20


def test_security_deposit():
    """Verify security deposit rules."""
    # Bike -> ₹1000 for any duration
    d1 = calculate_security_deposit("BIKE", 5)
    assert d1["deposit_amount"] == 1000.0
    assert d1["gst_amount"] == 0.0

    # EV Bike -> ₹1000
    d2 = calculate_security_deposit("EV_BIKE", 2)
    assert d2["deposit_amount"] == 1000.0

    # Scooter < 24h -> ₹0
    d3 = calculate_security_deposit("SCOOTER", 10)
    assert d3["deposit_amount"] == 0.0

    # Scooter >= 24h -> ₹500
    d4 = calculate_security_deposit("SCOOTER", 24)
    assert d4["deposit_amount"] == 500.0


def test_cancellation_policy_version_cutoff():
    """Verify v1 vs v2 cutoff on 2026-06-30 18:30:00 UTC (1 July 2026 00:00 IST)."""
    # Booked before cutoff -> v1
    v1 = get_cancellation_policy_version("2026-06-30 18:00:00")
    assert "v1.0" in v1

    # Booked at/after cutoff -> v2
    v2 = get_cancellation_policy_version("2026-06-30 18:30:00")
    assert "v2.0" in v2

    v2_later = get_cancellation_policy_version("2026-07-05 10:00:00")
    assert "v2.0" in v2_later


def test_cancellation_refund_v1():
    """Verify Version 1 refund slabs."""
    # Booked in May 2026, scheduled 20 May 09:00, cancelled 19 May 21:00 (12h before) -> 50%
    ref = calculate_cancellation_refund(
        booked_at_str="2026-05-10 18:00:00",
        scheduled_start_str="2026-05-20 09:00:00",
        cancelled_at_str="2026-05-19 21:00:00",
        paid_rental_amount=500.0,
        paid_gst_amount=90.0
    )
    assert ref["refund_percentage"] == 50.0
    assert ref["refund_rental_amount"] == 250.0
    assert ref["refund_gst_amount"] == 45.0
    assert ref["total_refund"] == 295.0

    # Cancelled 30h before -> 100%
    ref_full = calculate_cancellation_refund(
        booked_at_str="2026-05-10 18:00:00",
        scheduled_start_str="2026-05-20 09:00:00",
        cancelled_at_str="2026-05-18 09:00:00",
        paid_rental_amount=500.0
    )
    assert ref_full["refund_percentage"] == 100.0

    # Cancelled 3h before -> 0%
    ref_none = calculate_cancellation_refund(
        booked_at_str="2026-05-10 18:00:00",
        scheduled_start_str="2026-05-20 09:00:00",
        cancelled_at_str="2026-05-20 06:00:00",
        paid_rental_amount=500.0
    )
    assert ref_none["refund_percentage"] == 0.0


def test_cancellation_refund_v2():
    """Verify Version 2 refund slabs from scanned Annexure 1."""
    # Booked on 5 July 2026, pickup 10 July 12:00, cancelled 9 July 00:00 (36h before) -> 75%
    ref_75 = calculate_cancellation_refund(
        booked_at_str="2026-07-05 10:00:00",
        scheduled_start_str="2026-07-10 12:00:00",
        cancelled_at_str="2026-07-09 00:00:00",
        paid_rental_amount=1000.0,
        paid_gst_amount=180.0
    )
    assert ref_75["refund_percentage"] == 75.0
    assert ref_75["refund_rental_amount"] == 750.0
    assert ref_75["refund_gst_amount"] == 135.0
    assert ref_75["total_refund"] == 885.0

    # Cancelled 6h before pickup -> 25% (2h to < 12h slab in v2)
    ref_25 = calculate_cancellation_refund(
        booked_at_str="2026-07-05 10:00:00",
        scheduled_start_str="2026-07-10 12:00:00",
        cancelled_at_str="2026-07-10 06:00:00",
        paid_rental_amount=1000.0
    )
    assert ref_25["refund_percentage"] == 25.0

    # RideWise cancelled -> 100%
    ref_rw = calculate_cancellation_refund(
        booked_at_str="2026-07-05 10:00:00",
        scheduled_start_str="2026-07-10 12:00:00",
        paid_rental_amount=1000.0,
        is_ridewise_cancelled=True
    )
    assert ref_rw["refund_percentage"] == 100.0

    # No-show -> 0%
    ref_nsh = calculate_cancellation_refund(
        booked_at_str="2026-07-05 10:00:00",
        scheduled_start_str="2026-07-10 12:00:00",
        paid_rental_amount=1000.0,
        is_no_show=True
    )
    assert ref_nsh["refund_percentage"] == 0.0


def test_late_return_penalty():
    """Verify late penalty and GOLD tier grace period."""
    # STANDARD tier, 20 min late, hourly rate ₹100 -> 1 hour charged @ 1.5*100 = 150 + 27 GST = 177
    p1 = calculate_late_return_penalty(
        customer_tier="STANDARD",
        hourly_rate=100.0,
        scheduled_end_str="2026-05-10 18:00:00",
        actual_return_str="2026-05-10 18:20:00"
    )
    assert p1["is_late"] is True
    assert p1["hours_charged"] == 1
    assert p1["base_penalty"] == 150.0
    assert p1["gst_amount"] == 27.0
    assert p1["total_penalty"] == 177.0

    # GOLD tier, 25 min late -> Within 30 min grace period -> ₹0 penalty
    p_gold_grace = calculate_late_return_penalty(
        customer_tier="GOLD",
        hourly_rate=100.0,
        scheduled_end_str="2026-05-10 18:00:00",
        actual_return_str="2026-05-10 18:25:00"
    )
    assert p_gold_grace["base_penalty"] == 0.0
    assert p_gold_grace["total_penalty"] == 0.0

    # GOLD tier, 45 min late -> Exceeds grace period -> Full lateness charged from minute 1 (1 hr charged)
    p_gold_exceeded = calculate_late_return_penalty(
        customer_tier="GOLD",
        hourly_rate=100.0,
        scheduled_end_str="2026-05-10 18:00:00",
        actual_return_str="2026-05-10 18:45:00"
    )
    assert p_gold_exceeded["hours_charged"] == 1
    assert p_gold_exceeded["base_penalty"] == 150.0

    # STANDARD tier, 1 hr 10 min late (70 min) -> 2 hours charged @ 150 = ₹300
    p2 = calculate_late_return_penalty(
        customer_tier="STANDARD",
        hourly_rate=100.0,
        scheduled_end_str="2026-05-10 18:00:00",
        actual_return_str="2026-05-10 19:10:00"
    )
    assert p2["hours_charged"] == 2
    assert p2["base_penalty"] == 300.0


def test_ev_low_battery_penalty():
    """Verify EV low battery penalty."""
    # EV scooter returned at 8% (< 10%) -> ₹150 + 18% GST = ₹177
    ev1 = calculate_ev_battery_penalty("EV_SCOOTER", 8)
    assert ev1["fee_applied"] is True
    assert ev1["base_fee"] == 150.0
    assert ev1["gst_amount"] == 27.0
    assert ev1["total_fee"] == 177.0

    # EV scooter returned at 15% -> ₹0
    ev2 = calculate_ev_battery_penalty("EV_SCOOTER", 15)
    assert ev2["fee_applied"] is False
    assert ev2["total_fee"] == 0.0

    # Non-EV bike -> ₹0
    non_ev = calculate_ev_battery_penalty("BIKE", 5)
    assert non_ev["fee_applied"] is False


def test_damage_charge_assessment():
    """Verify damage claim liability."""
    # CHARGED -> Customer liable
    d_charged = assess_damage_charge("CHARGED", 1200.0)
    assert d_charged["customer_liable"] is True
    assert d_charged["base_cost"] == 1200.0
    assert d_charged["gst_amount"] == 216.0
    assert d_charged["total_charge"] == 1416.0

    # OPEN -> Not yet charged
    d_open = assess_damage_charge("OPEN", 1200.0)
    assert d_open["customer_liable"] is False
    assert d_open["total_charge"] == 0.0

    # DISPUTED -> Under review
    d_disp = assess_damage_charge("DISPUTED", 1200.0)
    assert d_disp["customer_liable"] is False

    # WAIVED -> Waived
    d_waived = assess_damage_charge("WAIVED", 1200.0)
    assert d_waived["customer_liable"] is False
