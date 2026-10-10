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
