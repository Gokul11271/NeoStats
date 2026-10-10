"""
Database Access Module for RideWise Assist
Strict read-only SQLite connector with deterministic, role-based parameterized query functions.
"""
import sqlite3
from typing import Any, Dict, List, Optional
from ridewise.config import RIDEWISE_DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """
    Returns a read-only SQLite database connection using URI mode.
    Raises RuntimeError if the database file does not exist.
    """
    if not RIDEWISE_DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found at: {RIDEWISE_DB_PATH}")

    # SQLite read-only URI mode: file:path?mode=ro
    db_uri = f"file:{RIDEWISE_DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# CUSTOMER SCOPE FUNCTIONS (Enforced by code)
# ==========================================

def get_customer_profile(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the customer's own profile.
    Sensitive internal data is not leaked.
    """
    query = """
        SELECT customer_id, full_name, phone, email, city, date_of_birth,
               driving_license_no, kyc_status, customer_tier, created_at
        FROM customers
        WHERE customer_id = ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def lookup_vehicle_rates(model_query: str) -> Optional[Dict[str, Any]]:
    """
    Resolves model rates and specifications directly from the vehicles table.
    """
    if not model_query or len(model_query.strip()) < 2:
        return None

    clean = model_query.strip()
    query = """
        SELECT DISTINCT model, vehicle_type, hourly_rate, daily_rate, battery_capacity_kwh
        FROM vehicles
        WHERE model LIKE ? OR vehicle_type LIKE ?
        LIMIT 1
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (f"%{clean}%", f"%{clean}%"))
        row = cursor.fetchone()
        return dict(row) if row else None



def get_customer_bookings(customer_id: str, booking_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves bookings belonging ONLY to the specified customer_id.
    Includes vehicle specifications (rates, type, model).
    """
    query = """
        SELECT b.booking_id, b.customer_id, b.vehicle_id, b.booked_at,
               b.scheduled_start, b.scheduled_end, b.actual_return_at,
               b.cancelled_at, b.booking_status, b.return_battery_pct,
               v.registration_no, v.vehicle_type, v.model, v.hub_name,
               v.hourly_rate, v.daily_rate, v.battery_capacity_kwh
        FROM bookings b
        JOIN vehicles v ON b.vehicle_id = v.vehicle_id
        WHERE b.customer_id = ?
    """
    params = [customer_id]
    if booking_id:
        query += " AND b.booking_id = ?"
        params.append(booking_id)
    query += " ORDER BY b.booked_at DESC"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def get_booking_payments_for_customer(customer_id: str, booking_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves payments for a booking ONLY if that booking belongs to the customer.
    """
    query = """
        SELECT p.payment_id, p.booking_id, p.payment_type, p.amount,
               p.gst_amount, p.payment_method, p.payment_status,
               p.transaction_ref, p.paid_at, p.remarks
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        WHERE b.customer_id = ? AND p.booking_id = ?
        ORDER BY p.paid_at ASC
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id, booking_id))
        return [dict(row) for row in cursor.fetchall()]


def get_customer_all_payments(customer_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all payments for all bookings belonging to the customer.
    """
    query = """
        SELECT p.payment_id, p.booking_id, p.payment_type, p.amount,
               p.gst_amount, p.payment_method, p.payment_status,
               p.transaction_ref, p.paid_at, p.remarks
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        WHERE b.customer_id = ?
        ORDER BY p.paid_at DESC
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_booking_damages_for_customer(customer_id: str, booking_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves damage reports for a booking ONLY if that booking belongs to the customer.
    """
    query = """
        SELECT d.report_id, d.booking_id, d.vehicle_id, d.reported_by,
               d.damage_category, d.severity, d.description,
               d.assessed_cost, d.claim_status, d.reported_at
        FROM damage_reports d
        JOIN bookings b ON d.booking_id = b.booking_id
        WHERE b.customer_id = ? AND d.booking_id = ?
        ORDER BY d.reported_at ASC
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id, booking_id))
        return [dict(row) for row in cursor.fetchall()]


# ==========================================
# SUPPORT AGENT SCOPE FUNCTIONS
# ==========================================

def agent_get_customer_profile(customer_id: str) -> Optional[Dict[str, Any]]:
    """Support agent lookup of any customer profile."""
    return get_customer_profile(customer_id)


def agent_search_bookings(
    booking_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    hub_name: Optional[str] = None,
    booking_status: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Allows support agents to search bookings across hubs, customers, and statuses.
    """
    query = """
        SELECT b.booking_id, b.customer_id, b.vehicle_id, b.booked_at,
               b.scheduled_start, b.scheduled_end, b.actual_return_at,
               b.cancelled_at, b.booking_status, b.return_battery_pct,
               c.full_name as customer_name, c.phone as customer_phone, c.customer_tier,
               v.registration_no, v.vehicle_type, v.model, v.hub_name,
               v.hourly_rate, v.daily_rate, v.status as vehicle_status
        FROM bookings b
        JOIN customers c ON b.customer_id = c.customer_id
        JOIN vehicles v ON b.vehicle_id = v.vehicle_id
        WHERE 1=1
    """
    params: List[Any] = []
    if booking_id:
        query += " AND b.booking_id = ?"
        params.append(booking_id)
    if customer_id:
        query += " AND b.customer_id = ?"
        params.append(customer_id)
    if hub_name:
        query += " AND v.hub_name LIKE ?"
        params.append(f"%{hub_name}%")
    if booking_status:
        query += " AND b.booking_status = ?"
        params.append(booking_status)

    query += " ORDER BY b.booked_at DESC LIMIT ?"
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_booking_details(booking_id: str) -> Optional[Dict[str, Any]]:
    """
    Support agent retrieves complete details for any booking including customer,
    vehicle, all payments, and all damage reports.
    """
    bookings = agent_search_bookings(booking_id=booking_id, limit=1)
    if not bookings:
        return None

    booking = bookings[0]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Payments
        cursor.execute(
            "SELECT * FROM payments WHERE booking_id = ? ORDER BY paid_at ASC",
            (booking_id,)
        )
        booking["payments"] = [dict(r) for r in cursor.fetchall()]

        # Damages
        cursor.execute(
            "SELECT * FROM damage_reports WHERE booking_id = ? ORDER BY reported_at ASC",
            (booking_id,)
        )
        booking["damage_reports"] = [dict(r) for r in cursor.fetchall()]

    return booking


def agent_get_fleet_status(
    hub_name: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fleet inventory and operational availability lookup."""
    query = """
        SELECT vehicle_id, registration_no, vehicle_type, model, hub_name,
               hourly_rate, daily_rate, battery_capacity_kwh, status, commissioned_on
        FROM vehicles
        WHERE 1=1
    """
    params: List[Any] = []
    if hub_name:
        query += " AND hub_name LIKE ?"
        params.append(f"%{hub_name}%")
    if vehicle_type:
        query += " AND vehicle_type = ?"
        params.append(vehicle_type)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY hub_name, vehicle_type, model"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_damage_reports(
    claim_status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Support agent lookup of damage reports and claim resolution status."""
    query = """
        SELECT d.report_id, d.booking_id, d.vehicle_id, d.reported_by,
               d.damage_category, d.severity, d.description,
               d.assessed_cost, d.claim_status, d.reported_at,
               b.customer_id, c.full_name as customer_name,
               v.model as vehicle_model, v.registration_no, v.hub_name
        FROM damage_reports d
        JOIN bookings b ON d.booking_id = b.booking_id
        JOIN customers c ON b.customer_id = c.customer_id
        JOIN vehicles v ON d.vehicle_id = v.vehicle_id
        WHERE 1=1
    """
    params: List[Any] = []
    if claim_status:
        query += " AND d.claim_status = ?"
        params.append(claim_status)
    if severity:
        query += " AND d.severity = ?"
        params.append(severity)

    query += " ORDER BY d.reported_at DESC LIMIT ?"
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_operational_summary() -> Dict[str, Any]:
    """Provides high-level operational statistics for Support Agents."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Vehicles by status
        cursor.execute("SELECT status, count(*) FROM vehicles GROUP BY status")
        fleet_counts = dict(cursor.fetchall())

        # Vehicles by hub
        cursor.execute("SELECT hub_name, count(*) FROM vehicles GROUP BY hub_name")
        hub_counts = dict(cursor.fetchall())

        # Bookings by status
        cursor.execute("SELECT booking_status, count(*) FROM bookings GROUP BY booking_status")
        booking_counts = dict(cursor.fetchall())

        # KYC status summary
        cursor.execute("SELECT kyc_status, count(*) FROM customers GROUP BY kyc_status")
        kyc_counts = dict(cursor.fetchall())

        # Damage claims summary
        cursor.execute("SELECT claim_status, count(*), sum(assessed_cost) FROM damage_reports GROUP BY claim_status")
        damage_counts = {
            row[0]: {"count": row[1], "total_assessed": row[2] or 0.0}
            for row in cursor.fetchall()
        }

        return {
            "fleet_summary": fleet_counts,
            "hub_distribution": hub_counts,
            "booking_summary": booking_counts,
            "kyc_summary": kyc_counts,
            "damage_summary": damage_counts,
        }


def agent_get_distinct_customers(count_only: bool = False, limit: int = 100) -> Any:
    """
    Support agent lookup of distinct customers or distinct customer count.
    Excludes sensitive PII (phone, email, license) for privacy.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if count_only:
            cursor.execute("SELECT COUNT(DISTINCT customer_id) as total_distinct_customers FROM customers")
            row = cursor.fetchone()
            return dict(row) if row else {"total_distinct_customers": 0}
        else:
            cursor.execute(
                """
                SELECT DISTINCT customer_id, full_name, city, kyc_status, customer_tier, created_at
                FROM customers
                ORDER BY customer_id
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]


def agent_get_customers_without_bookings(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Support agent lookup of customers who have never placed a booking.
    Excludes sensitive PII (phone, email, license).
    """
    query = """
        SELECT c.customer_id, c.full_name, c.city, c.kyc_status, c.customer_tier, c.created_at
        FROM customers c
        LEFT JOIN bookings b ON c.customer_id = b.customer_id
        WHERE b.booking_id IS NULL
        ORDER BY c.customer_id
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_failed_payments(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Support agent lookup of all failed payment transactions across the system.
    """
    query = """
        SELECT p.payment_id, p.booking_id, b.customer_id, p.payment_type, p.amount,
               p.gst_amount, p.payment_method, p.payment_status, p.paid_at, p.remarks
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        WHERE p.payment_status = 'FAILED'
        ORDER BY p.paid_at DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_customer_failed_payments(customer_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Customer lookup of failed payments belonging ONLY to the session customer.
    """
    query = """
        SELECT p.payment_id, p.booking_id, p.payment_type, p.amount,
               p.gst_amount, p.payment_method, p.payment_status, p.paid_at, p.remarks
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        WHERE b.customer_id = ? AND p.payment_status = 'FAILED'
        ORDER BY p.paid_at DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_damage_reports_for_vehicle(vehicle_query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Support agent lookup of damage reports for a specific vehicle (by vehicle_id, registration, or model).
    """
    clean = vehicle_query.strip()
    query = """
        SELECT d.report_id, d.booking_id, d.vehicle_id, d.reported_by,
               d.damage_category, d.severity, d.description,
               d.assessed_cost, d.claim_status, d.reported_at,
               b.customer_id, c.full_name as customer_name,
               v.model as vehicle_model, v.registration_no, v.hub_name
        FROM damage_reports d
        JOIN bookings b ON d.booking_id = b.booking_id
        JOIN customers c ON b.customer_id = c.customer_id
        JOIN vehicles v ON d.vehicle_id = v.vehicle_id
        WHERE d.vehicle_id LIKE ? OR v.registration_no LIKE ? OR v.model LIKE ?
        ORDER BY d.reported_at DESC
        LIMIT ?
    """
    param = f"%{clean}%"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (param, param, param, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_customer_damages_for_vehicle(customer_id: str, vehicle_query: str) -> List[Dict[str, Any]]:
    """
    Customer lookup of damage reports for a vehicle ONLY if belonging to customer's own bookings.
    """
    clean = vehicle_query.strip()
    query = """
        SELECT d.report_id, d.booking_id, d.vehicle_id, d.reported_by,
               d.damage_category, d.severity, d.description,
               d.assessed_cost, d.claim_status, d.reported_at,
               v.model as vehicle_model, v.registration_no
        FROM damage_reports d
        JOIN bookings b ON d.booking_id = b.booking_id
        JOIN vehicles v ON d.vehicle_id = v.vehicle_id
        WHERE b.customer_id = ? AND (d.vehicle_id LIKE ? OR v.registration_no LIKE ? OR v.model LIKE ?)
        ORDER BY d.reported_at DESC
    """
    param = f"%{clean}%"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id, param, param, param))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_failed_and_pending_payments(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Support agent lookup of failed and pending payment transactions across the system.
    """
    query = """
        SELECT p.payment_id, p.booking_id, b.customer_id, p.payment_type, p.amount,
               p.gst_amount, p.payment_method, p.payment_status, p.paid_at, p.remarks
        FROM payments p
        JOIN bookings b ON p.booking_id = b.booking_id
        WHERE p.payment_status IN ('FAILED', 'PENDING')
        ORDER BY p.paid_at DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_payment_financial_summary() -> Dict[str, Any]:
    """
    Summarize successful payments, refunds, and penalties without double-counting.
    Groups strictly by payment_type where payment_status = 'SUCCESS'.
    """
    query = """
        SELECT payment_type, COUNT(*) as count, SUM(amount) as total_amount, SUM(gst_amount) as total_gst
        FROM payments
        WHERE payment_status = 'SUCCESS'
        GROUP BY payment_type
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        summary = {}
        for r in rows:
            ptype = r["payment_type"]
            summary[ptype] = {
                "count": r["count"],
                "total_amount": round(r["total_amount"] or 0.0, 2),
                "total_gst": round(r["total_gst"] or 0.0, 2),
                "net_total": round((r["total_amount"] or 0.0) + (r["total_gst"] or 0.0), 2)
            }
        return summary


def agent_get_top_damaged_vehicles(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Returns the vehicles with the most damage reports and total assessed damage cost.
    """
    query = """
        SELECT v.vehicle_id, v.model, v.registration_no, v.hub_name,
               COUNT(d.report_id) as damage_count,
               SUM(d.assessed_cost) as total_assessed_cost
        FROM damage_reports d
        JOIN vehicles v ON d.vehicle_id = v.vehicle_id
        GROUP BY v.vehicle_id, v.model, v.registration_no, v.hub_name
        ORDER BY damage_count DESC, total_assessed_cost DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_open_and_disputed_damages(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns damage reports with claim_status in ('OPEN', 'DISPUTED').
    """
    query = """
        SELECT d.report_id, d.booking_id, d.vehicle_id, d.reported_by,
               d.damage_category, d.severity, d.description,
               d.assessed_cost, d.claim_status, d.reported_at,
               v.model as vehicle_model, v.registration_no, v.hub_name
        FROM damage_reports d
        JOIN vehicles v ON d.vehicle_id = v.vehicle_id
        WHERE d.claim_status IN ('OPEN', 'DISPUTED')
        ORDER BY d.reported_at DESC
        LIMIT ?
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def agent_get_completed_bookings_missing_return() -> List[Dict[str, Any]]:
    """
    Identifies completed bookings ('CMP') that are missing an actual return timestamp.
    """
    query = """
        SELECT b.booking_id, b.customer_id, b.vehicle_id, b.scheduled_start,
               b.scheduled_end, b.actual_return_at, b.booking_status
        FROM bookings b
        WHERE b.booking_status = 'CMP' AND (b.actual_return_at IS NULL OR b.actual_return_at = '')
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def get_customer_upcoming_bookings(customer_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves upcoming bookings ('UPC') belonging to the customer.
    """
    query = """
        SELECT b.booking_id, b.customer_id, b.vehicle_id, b.booked_at,
               b.scheduled_start, b.scheduled_end, b.booking_status,
               v.registration_no, v.vehicle_type, v.model, v.hub_name,
               v.hourly_rate, v.daily_rate
        FROM bookings b
        JOIN vehicles v ON b.vehicle_id = v.vehicle_id
        WHERE b.customer_id = ? AND b.booking_status = 'UPC'
        ORDER BY b.scheduled_start ASC
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (customer_id,))
        return [dict(row) for row in cursor.fetchall()]


