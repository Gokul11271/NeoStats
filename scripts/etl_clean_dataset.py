import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple

# Reconfigure stdout for safe Windows UTF-8 execution
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DB_PATH = BASE_DIR / "Requirements" / "ridewise.db"
ANALYTICS_DB_PATH = BASE_DIR / "Requirements" / "ridewise_analytics.db"

# Canonical City Standardization Mapping
CANONICAL_CITY_MAP = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "blr": "Bengaluru",
    "chennai": "Chennai",
    "madras": "Chennai",
    "maa": "Chennai",
    "hyderabad": "Hyderabad",
    "hyd": "Hyderabad",
    "mangaluru": "Mangaluru",
    "mangalore": "Mangaluru",
    "ixe": "Mangaluru",
    "mysuru": "Mysuru",
    "mysore": "Mysuru",
    "myq": "Mysuru",
    "pune": "Pune",
    "pnq": "Pune"
}

# Status Code Human-Readable Descriptions
BOOKING_STATUS_MAP = {
    "CMP": "COMPLETED",
    "CNL_U": "CANCELLED_CUSTOMER",
    "CNL_S": "CANCELLED_RIDEWISE",
    "NSH": "NO_SHOW",
    "UPC": "UPCOMING",
    "ONG": "ONGOING"
}


def clean_string(val: Any) -> str:
    """Strips leading/trailing whitespaces and replaces multiple spaces."""
    if val is None:
        return ""
    return " ".join(str(val).strip().split())


def standardize_city(raw_city: Any) -> Tuple[str, str]:
    """
    Returns (canonical_city, raw_cleaned).
    Maps variations like 'bangalore ', 'BLR', 'Bengaluru' to 'Bengaluru'.
    """
    cleaned = clean_string(raw_city)
    lookup_key = cleaned.lower()
    canonical = CANONICAL_CITY_MAP.get(lookup_key, cleaned.title())
    return canonical, cleaned


def parse_ts(val: Any) -> Tuple[str, Any]:
    """Normalizes ISO timestamp strings to standard YYYY-MM-DD HH:MM:SS."""
    if not val:
        return "", None
    clean = clean_string(val).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(clean, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S"), dt
        except ValueError:
            pass
    return clean, None


def run_etl():
    """Main ETL execution pipeline."""
    print("=" * 70)
    print("🚀 Starting RideWise Assist ETL Pipeline")
    print(f"• Source DB (Read-Only): {RAW_DB_PATH}")
    print(f"• Target DB (Analytics): {ANALYTICS_DB_PATH}")
    print("=" * 70)

    if not RAW_DB_PATH.exists():
        raise FileNotFoundError(f"Source database not found at {RAW_DB_PATH}")

    # Remove previous analytics db if present to ensure fresh build
    if ANALYTICS_DB_PATH.exists():
        ANALYTICS_DB_PATH.unlink()

    raw_conn = sqlite3.connect(f"file:{RAW_DB_PATH.as_posix()}?mode=ro", uri=True)
    raw_conn.row_factory = sqlite3.Row
    analytics_conn = sqlite3.connect(ANALYTICS_DB_PATH.as_posix())
    analytics_cursor = analytics_conn.cursor()

    stats: Dict[str, Any] = {}

    # -------------------------------------------------------------
    # 1. TRANSFORM & LOAD CUSTOMERS (dim_customers)
    # -------------------------------------------------------------
    print("\n[1/5] Extracting & Transforming Customers...")
    raw_customers = raw_conn.execute("SELECT * FROM customers").fetchall()

    analytics_cursor.execute("""
        CREATE TABLE dim_customers (
            customer_id        TEXT PRIMARY KEY,
            full_name          TEXT NOT NULL,
            phone              TEXT,
            email              TEXT,
            city_canonical     TEXT NOT NULL,
            city_raw           TEXT,
            date_of_birth      TEXT,
            driving_license_no TEXT,
            kyc_status         TEXT,
            customer_tier      TEXT,
            created_at         TEXT
        )
    """)

    city_transform_counts: Dict[str, int] = {}
    cleaned_customers = []
    for c in raw_customers:
        can_city, raw_city = standardize_city(c["city"])
        city_transform_counts[can_city] = city_transform_counts.get(can_city, 0) + 1
        cleaned_customers.append((
            clean_string(c["customer_id"]).upper(),
            clean_string(c["full_name"]),
            clean_string(c["phone"]),
            clean_string(c["email"]).lower(),
            can_city,
            clean_string(c["city"]),
            clean_string(c["date_of_birth"]),
            clean_string(c["driving_license_no"]).upper(),
            clean_string(c["kyc_status"]).upper(),
            clean_string(c["customer_tier"]).upper(),
            parse_ts(c["created_at"])[0]
        ))

    analytics_cursor.executemany(
        "INSERT INTO dim_customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cleaned_customers
    )
    # Provide alias table 'customers' for drop-in query compatibility
    analytics_cursor.execute("CREATE VIEW customers AS SELECT * FROM dim_customers")

    stats["customers"] = len(cleaned_customers)
    print(f"  ✓ Processed {len(cleaned_customers)} customer records.")
    print(f"  ✓ Standardized City Counts: {city_transform_counts}")

    # -------------------------------------------------------------
    # 2. TRANSFORM & LOAD VEHICLES (dim_vehicles)
    # -------------------------------------------------------------
    print("\n[2/5] Extracting & Transforming Vehicles...")
    raw_vehicles = raw_conn.execute("SELECT * FROM vehicles").fetchall()

    analytics_cursor.execute("""
        CREATE TABLE dim_vehicles (
            vehicle_id           TEXT PRIMARY KEY,
            registration_no      TEXT NOT NULL,
            vehicle_type         TEXT,
            model                TEXT,
            hub_name             TEXT,
            hourly_rate          REAL,
            daily_rate           REAL,
            battery_capacity_kwh REAL,
            status               TEXT,
            commissioned_on      TEXT
        )
    """)

    cleaned_vehicles = []
    for v in raw_vehicles:
        cleaned_vehicles.append((
            clean_string(v["vehicle_id"]).upper(),
            clean_string(v["registration_no"]).upper(),
            clean_string(v["vehicle_type"]).upper(),
            clean_string(v["model"]),
            clean_string(v["hub_name"]),
            float(v["hourly_rate"]) if v["hourly_rate"] is not None else 0.0,
            float(v["daily_rate"]) if v["daily_rate"] is not None else 0.0,
            float(v["battery_capacity_kwh"]) if v["battery_capacity_kwh"] is not None else None,
            clean_string(v["status"]).upper(),
            clean_string(v["commissioned_on"])
        ))

    analytics_cursor.executemany(
        "INSERT INTO dim_vehicles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cleaned_vehicles
    )
    analytics_cursor.execute("CREATE VIEW vehicles AS SELECT * FROM dim_vehicles")
    stats["vehicles"] = len(cleaned_vehicles)
    print(f"  ✓ Processed {len(cleaned_vehicles)} fleet vehicle records.")

    # -------------------------------------------------------------
    # 3. TRANSFORM & LOAD BOOKINGS (fact_bookings)
    # -------------------------------------------------------------
    print("\n[3/5] Extracting & Transforming Bookings...")
    raw_bookings = raw_conn.execute("SELECT * FROM bookings").fetchall()

    analytics_cursor.execute("""
        CREATE TABLE fact_bookings (
            booking_id               TEXT PRIMARY KEY,
            customer_id              TEXT NOT NULL,
            vehicle_id               TEXT NOT NULL,
            booked_at                TEXT,
            scheduled_start          TEXT,
            scheduled_end            TEXT,
            actual_return_at         TEXT,
            cancelled_at             TEXT,
            booking_status_code      TEXT,
            booking_status_desc      TEXT,
            return_battery_pct       INTEGER,
            scheduled_duration_hours REAL,
            actual_duration_hours    REAL,
            is_late                  INTEGER,
            late_minutes             REAL
        )
    """)

    cleaned_bookings = []
    for b in raw_bookings:
        b_code = clean_string(b["booking_status"]).upper()
        b_desc = BOOKING_STATUS_MAP.get(b_code, b_code)

        b_start_str, dt_start = parse_ts(b["scheduled_start"])
        b_end_str, dt_end = parse_ts(b["scheduled_end"])
        b_ret_str, dt_ret = parse_ts(b["actual_return_at"])
        b_cnl_str, _ = parse_ts(b["cancelled_at"])
        b_book_str, _ = parse_ts(b["booked_at"])

        sched_hrs = (dt_end - dt_start).total_seconds() / 3600.0 if (dt_start and dt_end) else 0.0
        act_hrs = (dt_ret - dt_start).total_seconds() / 3600.0 if (dt_start and dt_ret) else None

        is_late = 0
        late_min = 0.0
        if dt_end and dt_ret:
            diff_sec = (dt_ret - dt_end).total_seconds()
            if diff_sec > 0:
                is_late = 1
                late_min = round(diff_sec / 60.0, 1)

        cleaned_bookings.append((
            clean_string(b["booking_id"]).upper(),
            clean_string(b["customer_id"]).upper(),
            clean_string(b["vehicle_id"]).upper(),
            b_book_str,
            b_start_str,
            b_end_str,
            b_ret_str,
            b_cnl_str,
            b_code,
            b_desc,
            b["return_battery_pct"],
            round(sched_hrs, 2),
            round(act_hrs, 2) if act_hrs is not None else None,
            is_late,
            late_min
        ))

    analytics_cursor.executemany(
        "INSERT INTO fact_bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cleaned_bookings
    )
    analytics_cursor.execute("CREATE VIEW bookings AS SELECT * FROM fact_bookings")
    stats["bookings"] = len(cleaned_bookings)
    print(f"  ✓ Processed {len(cleaned_bookings)} bookings with pre-computed duration & lateness.")

    # -------------------------------------------------------------
    # 4. TRANSFORM & LOAD PAYMENTS (fact_payments)
    # -------------------------------------------------------------
    print("\n[4/5] Extracting & Transforming Payments...")
    raw_payments = raw_conn.execute("SELECT * FROM payments").fetchall()

    analytics_cursor.execute("""
        CREATE TABLE fact_payments (
            payment_id       TEXT PRIMARY KEY,
            booking_id       TEXT NOT NULL,
            payment_type     TEXT,
            amount           REAL,
            gst_amount       REAL,
            net_total_amount REAL,
            payment_method   TEXT,
            payment_status   TEXT,
            transaction_ref  TEXT,
            paid_at          TEXT,
            remarks          TEXT
        )
    """)

    cleaned_payments = []
    for p in raw_payments:
        amt = float(p["amount"]) if p["amount"] is not None else 0.0
        gst = float(p["gst_amount"]) if p["gst_amount"] is not None else 0.0
        cleaned_payments.append((
            clean_string(p["payment_id"]).upper(),
            clean_string(p["booking_id"]).upper(),
            clean_string(p["payment_type"]).upper(),
            round(amt, 2),
            round(gst, 2),
            round(amt + gst, 2),
            clean_string(p["payment_method"]).upper(),
            clean_string(p["payment_status"]).upper(),
            clean_string(p["transaction_ref"]),
            parse_ts(p["paid_at"])[0],
            clean_string(p["remarks"])
        ))

    analytics_cursor.executemany(
        "INSERT INTO fact_payments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cleaned_payments
    )
    analytics_cursor.execute("CREATE VIEW payments AS SELECT * FROM fact_payments")
    stats["payments"] = len(cleaned_payments)
    print(f"  ✓ Processed {len(cleaned_payments)} financial payment transactions.")

    # -------------------------------------------------------------
    # 5. TRANSFORM & LOAD DAMAGE REPORTS (fact_damage_reports)
    # -------------------------------------------------------------
    print("\n[5/5] Extracting & Transforming Damage Reports...")
    raw_damages = raw_conn.execute("SELECT * FROM damage_reports").fetchall()

    analytics_cursor.execute("""
        CREATE TABLE fact_damage_reports (
            report_id       TEXT PRIMARY KEY,
            booking_id      TEXT NOT NULL,
            vehicle_id      TEXT NOT NULL,
            reported_by     TEXT,
            damage_category TEXT,
            severity        TEXT,
            description     TEXT,
            assessed_cost   REAL,
            claim_status    TEXT,
            reported_at     TEXT
        )
    """)

    cleaned_damages = []
    for d in raw_damages:
        cost = float(d["assessed_cost"]) if d["assessed_cost"] is not None else 0.0
        cleaned_damages.append((
            clean_string(d["report_id"]).upper(),
            clean_string(d["booking_id"]).upper(),
            clean_string(d["vehicle_id"]).upper(),
            clean_string(d["reported_by"]),
            clean_string(d["damage_category"]).upper(),
            clean_string(d["severity"]).upper(),
            clean_string(d["description"]),
            round(cost, 2),
            clean_string(d["claim_status"]).upper(),
            parse_ts(d["reported_at"])[0]
        ))

    analytics_cursor.executemany(
        "INSERT INTO fact_damage_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cleaned_damages
    )
    analytics_cursor.execute("CREATE VIEW damage_reports AS SELECT * FROM fact_damage_reports")
    stats["damage_reports"] = len(cleaned_damages)
    print(f"  ✓ Processed {len(cleaned_damages)} vehicle damage reports.")

    # -------------------------------------------------------------
    # 6. CREATE AGGREGATED ANALYTICS VIEWS
    # -------------------------------------------------------------
    print("\nCreating Analytical Business Views...")

    # View 1: City summary
    analytics_cursor.execute("""
        CREATE VIEW view_city_customer_summary AS
        SELECT
            city_canonical as city,
            COUNT(customer_id) as total_customers,
            SUM(CASE WHEN kyc_status = 'VERIFIED' THEN 1 ELSE 0 END) as verified_customers,
            SUM(CASE WHEN customer_tier = 'GOLD' THEN 1 ELSE 0 END) as gold_tier_customers,
            SUM(CASE WHEN customer_tier = 'SILVER' THEN 1 ELSE 0 END) as silver_tier_customers,
            SUM(CASE WHEN customer_tier = 'STANDARD' THEN 1 ELSE 0 END) as standard_tier_customers
        FROM dim_customers
        GROUP BY city_canonical
        ORDER BY total_customers DESC;
    """)

    # View 2: Financial summary by type
    analytics_cursor.execute("""
        CREATE VIEW view_financial_summary AS
        SELECT
            payment_type,
            COUNT(*) as transaction_count,
            SUM(amount) as base_revenue,
            SUM(gst_amount) as total_gst,
            SUM(net_total_amount) as gross_revenue
        FROM fact_payments
        WHERE payment_status = 'SUCCESS'
        GROUP BY payment_type;
    """)

    # View 3: Fleet utilization summary
    analytics_cursor.execute("""
        CREATE VIEW view_fleet_utilization AS
        SELECT
            v.vehicle_id,
            v.model,
            v.vehicle_type,
            v.hub_name,
            COUNT(b.booking_id) as total_trips,
            COALESCE(SUM(b.actual_duration_hours), 0) as total_billable_hours,
            COALESCE(SUM(b.is_late), 0) as late_return_trips
        FROM dim_vehicles v
        LEFT JOIN fact_bookings b ON v.vehicle_id = b.vehicle_id AND b.booking_status_code = 'CMP'
        GROUP BY v.vehicle_id
        ORDER BY total_trips DESC;
    """)

    # Commit all changes
    analytics_conn.commit()

    # Query view for verification
    city_summary = analytics_cursor.execute("SELECT * FROM view_city_customer_summary").fetchall()

    print("\n" + "=" * 70)
    print("✨ ETL PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("📊 Standardized City Distribution in Clean Analytics DB:")
    for row in city_summary:
        print(f"  • {row[0]:<12}: {row[1]} customers (Verified: {row[2]}, Gold: {row[3]})")
    print("\n📦 Cleaned Analytics Database saved to:")
    print(f"   {ANALYTICS_DB_PATH}")
    print("=" * 70)

    raw_conn.close()
    analytics_conn.close()
    return stats


if __name__ == "__main__":
    run_etl()
