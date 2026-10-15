"""
Deterministic Financial & Policy Calculation Engine for RideWise Assist
Pure Python calculations for rental charges, cancellation refunds, late return penalties,
EV low-battery fees, damage claims, and 18% GST. Zero LLM math hallucinations.
"""
import math
from datetime import datetime
from typing import Any, Dict, Optional
from ridewise.config import POLICY_V2_CUTOFF_UTC

GST_RATE = 0.18


def parse_utc_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parses ISO timestamp string (YYYY-MM-DD HH:MM:SS) into a naive UTC datetime.
    Returns None for empty, missing, or malformed timestamps."""
    if not ts:
        return None
    # Support both space and T separator
    clean_ts = ts.replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(clean_ts, fmt)
        except ValueError:
            continue
    return None


def calculate_rental_charge(
    duration_hours: int,
    hourly_rate: float,
    daily_rate: float
) -> Dict[str, Any]:
    """
    Calculates rental charge according to RW-POL-01 Clause 4.1:
    - Full 24-hour blocks are charged at daily_rate.
    - Remaining hours are charged at hourly_rate, but capped at one daily_rate.
    - Adds 18% GST.
    """
    if duration_hours < 2:
        # Minimum rental is 2 hours per policy
        effective_hours = 2
    else:
        effective_hours = duration_hours

    days = effective_hours // 24
    rem_hours = effective_hours % 24

    day_cost = days * daily_rate
    rem_cost = min(rem_hours * hourly_rate, daily_rate)
    base_charge = round(day_cost + rem_cost, 2)
    gst = round(base_charge * GST_RATE, 2)
    total = round(base_charge + gst, 2)

    return {
        "duration_hours": duration_hours,
        "effective_hours": effective_hours,
        "hourly_rate": hourly_rate,
        "daily_rate": daily_rate,
        "days_charged": days,
        "rem_hours_charged": rem_hours,
        "base_rental_charge": base_charge,
        "gst_amount": gst,
        "total_amount": total,
        "formula": f"({days} × ₹{daily_rate}) + min({rem_hours} × ₹{hourly_rate}, ₹{daily_rate}) = ₹{base_charge} + ₹{gst} GST = ₹{total}"
    }


def calculate_security_deposit(vehicle_type: str, duration_hours: int) -> Dict[str, Any]:
    """
    Calculates refundable security deposit per RW-POL-01 Clause 5.1:
    - Bike / EV bike: ₹1,000 (any rental)
    - Scooter / EV scooter: ₹500 (rentals >= 24 hours), ₹0 (< 24 hours)
    - Deposits carry NO GST.
    """
    vtype = vehicle_type.upper().strip()
    if "BIKE" in vtype:
        deposit = 1000.0
        reason = "Bike/EV Bike rental deposit (₹1,000 applicable to any duration)"
    elif "SCOOTER" in vtype:
        if duration_hours >= 24:
            deposit = 500.0
            reason = "Scooter/EV Scooter rental of 24h or more (₹500 deposit)"
        else:
            deposit = 0.0
            reason = "Scooter rental under 24 hours (₹0 deposit)"
    else:
        deposit = 0.0
        reason = "Standard vehicle deposit"

    return {
        "vehicle_type": vehicle_type,
        "duration_hours": duration_hours,
        "deposit_amount": deposit,
        "gst_amount": 0.0,
        "reason": reason
    }


def get_cancellation_policy_version(booked_at_str: str) -> str:
    """
    Determines if RW-POL-02 (v1) or RW-POL-03 (v2) applies based strictly on booked_at timestamp.
    Cutoff: 1 July 2026, 00:00 IST == 2026-06-30 18:30:00 UTC.
    """
    dt_booked = parse_utc_timestamp(booked_at_str)
    dt_cutoff = parse_utc_timestamp(POLICY_V2_CUTOFF_UTC)

    if dt_booked and dt_cutoff and dt_booked >= dt_cutoff:
        return "v2.0 (RW-POL-03)"
    return "v1.0 (RW-POL-02)"


def calculate_cancellation_refund(
    booked_at_str: str,
    scheduled_start_str: str,
    cancelled_at_str: Optional[str] = None,
    paid_rental_amount: float = 0.0,
    paid_gst_amount: float = 0.0,
    is_ridewise_cancelled: bool = False,
    is_no_show: bool = False
) -> Dict[str, Any]:
    # NOTE: paid_rental_amount must be the base amount EXCLUSIVE of GST.
    # If paid_gst_amount is 0 or negative, GST is auto-calculated as 18% of paid_rental_amount.
    # Callers must never pass a GST-inclusive amount as paid_rental_amount.
    """
    Calculates cancellation refund adhering to versioning and policy schedules:
    - RideWise Cancelled: 100% refund.
    - No-show: 0% refund.
    - Version 1 (< 1 July 2026 IST):
        >= 24h: 100%
        6h to < 24h: 50%
        < 6h: 0%
    - Version 2 (>= 1 July 2026 IST):
        >= 48h: 100%
        12h to < 48h: 75%
        2h to < 12h: 25%
        < 2h: 0%
    """
    policy_version = get_cancellation_policy_version(booked_at_str)
    is_v2 = "v2.0" in policy_version

    # If GST was not supplied separately, calculate 18% of paid base amount
    if paid_gst_amount <= 0.0 and paid_rental_amount > 0.0:
        paid_gst_amount = round(paid_rental_amount * GST_RATE, 2)

    # 1. No-Show
    if is_no_show:
        return {
            "policy_version": policy_version,
            "refund_percentage": 0.0,
            "refund_rental_amount": 0.0,
            "refund_gst_amount": 0.0,
            "total_refund": 0.0,
            "reason": "No-show: Rental charge is not refunded per policy clause 7.2 / 3.1."
        }

    # 2. RideWise Cancellation
    if is_ridewise_cancelled:
        return {
            "policy_version": policy_version,
            "refund_percentage": 100.0,
            "refund_rental_amount": round(paid_rental_amount, 2),
            "refund_gst_amount": round(paid_gst_amount, 2),
            "total_refund": round(paid_rental_amount + paid_gst_amount, 2),
            "reason": "RideWise cancelled booking: 100% refund in all cases."
        }

    # 3. Customer Cancellation
    dt_start = parse_utc_timestamp(scheduled_start_str)
    dt_cancelled = parse_utc_timestamp(cancelled_at_str)

    if not dt_start or not dt_cancelled:
        return {
            "policy_version": policy_version,
            "refund_percentage": 0.0,
            "refund_rental_amount": 0.0,
            "refund_gst_amount": 0.0,
            "total_refund": 0.0,
            "reason": "Insufficient timing evidence to determine cancellation window."
        }

    hours_before = (dt_start - dt_cancelled).total_seconds() / 3600.0

    if is_v2:
        # Version 2 schedule
        if hours_before >= 48.0:
            pct = 100.0
            slab_desc = "48 hours or more before pickup (100% refund)"
        elif hours_before >= 12.0:
            pct = 75.0
            slab_desc = "12 hours or more, but less than 48 hours before pickup (75% refund)"
        elif hours_before >= 2.0:
            pct = 25.0
            slab_desc = "2 hours or more, but less than 12 hours before pickup (25% refund)"
        else:
            pct = 0.0
            slab_desc = "Less than 2 hours before pickup (0% refund)"
    else:
        # Version 1 schedule
        if hours_before >= 24.0:
            pct = 100.0
            slab_desc = "24 hours or more before pickup (100% refund)"
        elif hours_before >= 6.0:
            pct = 50.0
            slab_desc = "6 hours or more, but less than 24 hours before pickup (50% refund)"
        else:
            pct = 0.0
            slab_desc = "Less than 6 hours before pickup (0% refund)"

    refund_base = round(paid_rental_amount * (pct / 100.0), 2)
    refund_gst = round(paid_gst_amount * (pct / 100.0), 2)
    total_refund = round(refund_base + refund_gst, 2)

    return {
        "policy_version": policy_version,
        "hours_before_pickup": round(hours_before, 2),
        "applied_slab": slab_desc,
        "refund_percentage": pct,
        "refund_rental_amount": refund_base,
        "refund_gst_amount": refund_gst,
        "total_refund": total_refund,
        "reason": f"Cancelled {hours_before:.1f}h before pickup under {policy_version}: {pct}% of ₹{paid_rental_amount} = ₹{refund_base} (+ ₹{refund_gst} GST)"
    }


def calculate_late_return_penalty(
    customer_tier: str,
    hourly_rate: float,
    scheduled_end_str: str,
    actual_return_str: Optional[str]
) -> Dict[str, Any]:
    """
    Calculates late return penalty per RW-POL-04 Clause 1 and Annexure A:
    - GOLD tier gets 30 min grace period (up to and including 30m = ₹0).
    - If return is > 30 min late for GOLD, full lateness is charged from minute 1.
    - STANDARD & SILVER have 0 grace period.
    - Each late hour or part-hour is charged at 1.5 × hourly_rate.
    - Adds 18% GST.
    """
    dt_end = parse_utc_timestamp(scheduled_end_str)
    dt_actual = parse_utc_timestamp(actual_return_str)

    if not dt_end or not dt_actual:
        return {
            "is_late": False,
            "late_minutes": 0,
            "hours_charged": 0,
            "base_penalty": 0.0,
            "gst_amount": 0.0,
            "total_penalty": 0.0,
            "reason": "No actual return timestamp recorded."
        }

    late_seconds = (dt_actual - dt_end).total_seconds()
    if late_seconds <= 0:
        return {
            "is_late": False,
            "late_minutes": 0,
            "hours_charged": 0,
            "base_penalty": 0.0,
            "gst_amount": 0.0,
            "total_penalty": 0.0,
            "reason": "Returned on time or early."
        }

    late_minutes = late_seconds / 60.0
    tier = customer_tier.upper().strip()

    # Grace period evaluation
    if tier == "GOLD" and late_minutes <= 30.0:
        return {
            "is_late": True,
            "late_minutes": round(late_minutes, 1),
            "grace_period_applied": "30 minutes (GOLD Tier Benefit)",
            "hours_charged": 0,
            "base_penalty": 0.0,
            "gst_amount": 0.0,
            "total_penalty": 0.0,
            "reason": f"Returned {late_minutes:.1f}m late within GOLD tier 30-minute grace period. No late fee."
        }

    # Per Annexure A: when GOLD exceeds 30-min grace, the FULL lateness
    # is charged from minute 1 (grace does NOT reduce billable minutes).
    # Billed hours: each hour or part of hour counts as 1 full hour.
    hours_charged = math.ceil(late_minutes / 60.0)
    rate_per_late_hour = round(1.5 * hourly_rate, 2)
    base_penalty = round(hours_charged * rate_per_late_hour, 2)
    gst = round(base_penalty * GST_RATE, 2)
    total = round(base_penalty + gst, 2)

    return {
        "is_late": True,
        "late_minutes": round(late_minutes, 1),
        "tier": tier,
        "hours_charged": hours_charged,
        "late_rate_per_hour": rate_per_late_hour,
        "base_penalty": base_penalty,
        "gst_amount": gst,
        "total_penalty": total,
        "reason": f"Returned {late_minutes:.1f}m late ({hours_charged} hr(s) billed at 1.5× ₹{hourly_rate} = ₹{rate_per_late_hour}/hr). Base ₹{base_penalty} + ₹{gst} GST = ₹{total}"
    }


def calculate_ev_battery_penalty(
    vehicle_type: str,
    return_battery_pct: Optional[int]
) -> Dict[str, Any]:
    """
    Calculates EV low-battery penalty per RW-POL-04 Clause 2:
    - EV Scooters & EV Bikes with return battery < 10%: flat ₹150 + 18% GST (₹27) = ₹177.
    - Return battery >= 10% or non-EV: ₹0.
    """
    vtype = vehicle_type.upper().strip()
    is_ev = "EV" in vtype

    if not is_ev or return_battery_pct is None:
        return {
            "is_ev": is_ev,
            "battery_pct": return_battery_pct,
            "fee_applied": False,
            "base_fee": 0.0,
            "gst_amount": 0.0,
            "total_fee": 0.0,
            "reason": "Non-EV vehicle or no battery reading."
        }

    if return_battery_pct < 10:
        base_fee = 150.0
        gst = round(base_fee * GST_RATE, 2)
        total = round(base_fee + gst, 2)
        return {
            "is_ev": True,
            "battery_pct": return_battery_pct,
            "fee_applied": True,
            "base_fee": base_fee,
            "gst_amount": gst,
            "total_fee": total,
            "reason": f"EV returned with {return_battery_pct}% battery (< 10% threshold): flat fee ₹150 + ₹{gst} GST = ₹{total}"
        }

    return {
        "is_ev": True,
        "battery_pct": return_battery_pct,
        "fee_applied": False,
        "base_fee": 0.0,
        "gst_amount": 0.0,
        "total_fee": 0.0,
        "reason": f"EV returned with {return_battery_pct}% battery (>= 10%). No low-battery fee."
    }


def assess_damage_charge(
    claim_status: str,
    assessed_cost: float
) -> Dict[str, Any]:
    """
    Evaluates damage claim liability per RW-POL-04 Clause 3:
    - CHARGED: Assessed cost + 18% GST charged to customer.
    - OPEN / DISPUTED / WAIVED: ₹0 charged to customer currently.
    """
    status = claim_status.upper().strip()
    if status == "CHARGED":
        base = round(assessed_cost, 2)
        gst = round(base * GST_RATE, 2)
        total = round(base + gst, 2)
        return {
            "claim_status": status,
            "customer_liable": True,
            "base_cost": base,
            "gst_amount": gst,
            "total_charge": total,
            "reason": f"Damage claim CHARGED: ₹{base} assessed cost + ₹{gst} GST = ₹{total} charged to customer."
        }
    elif status == "OPEN":
        return {
            "claim_status": status,
            "customer_liable": False,
            "base_cost": 0.0,
            "gst_amount": 0.0,
            "total_charge": 0.0,
            "reason": "Damage claim OPEN: Assessment or review in progress. Not charged yet."
        }
    elif status == "DISPUTED":
        return {
            "claim_status": status,
            "customer_liable": False,
            "base_cost": 0.0,
            "gst_amount": 0.0,
            "total_charge": 0.0,
            "reason": "Damage claim DISPUTED: Under review. Not charged until dispute is resolved."
        }
    elif status == "WAIVED":
        return {
            "claim_status": status,
            "customer_liable": False,
            "base_cost": 0.0,
            "gst_amount": 0.0,
            "total_charge": 0.0,
            "reason": "Damage claim WAIVED: RideWise decided not to charge."
        }

    return {
        "claim_status": status,
        "customer_liable": False,
        "base_cost": 0.0,
        "gst_amount": 0.0,
        "total_charge": 0.0,
        "reason": f"Status '{status}': No charge applied."
    }
