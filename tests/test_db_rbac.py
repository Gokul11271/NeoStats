"""
Unit Tests for Database Access and RBAC Isolation
"""
import pytest
import sqlite3
from ridewise.db import (
    get_customer_profile,
    get_customer_bookings,
    get_booking_payments_for_customer,
    get_booking_damages_for_customer,
    agent_search_bookings,
    agent_get_fleet_status,
    agent_get_damage_reports,
    agent_get_operational_summary,
    get_db_connection
)


def test_db_read_only_enforcement():
    """Verify that the database connection is strictly read-only."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        with pytest.raises(sqlite3.OperationalError):
            cursor.execute("UPDATE customers SET full_name = 'Hacked' WHERE customer_id = 'CUST0001'")


def test_customer_profile_lookup():
    """Verify customer profile retrieval."""
    profile = get_customer_profile("CUST0001")
    assert profile is not None
    assert profile["customer_id"] == "CUST0001"
    assert "full_name" in profile
    assert "customer_tier" in profile


def test_customer_isolation_bookings():
    """Verify that a customer cannot retrieve another customer's bookings."""
    c1_bookings = get_customer_bookings("CUST0001")
    assert isinstance(c1_bookings, list)
    for b in c1_bookings:
        assert b["customer_id"] == "CUST0001"

    # Searching with a mismatched booking_id returns empty
    if c1_bookings:
        valid_b_id = c1_bookings[0]["booking_id"]
        # Another customer trying to fetch c1's booking
        cross_access = get_customer_bookings("CUST0002", booking_id=valid_b_id)
        assert len(cross_access) == 0


def test_customer_isolation_payments():
    """Verify customer cannot see payments for another customer's booking."""
    c1_bookings = get_customer_bookings("CUST0001")
    if c1_bookings:
        valid_b_id = c1_bookings[0]["booking_id"]
        # Proper owner gets payment records
        payments = get_booking_payments_for_customer("CUST0001", valid_b_id)
        assert isinstance(payments, list)

        # Mismatched customer gets 0 records
        unauthorized_payments = get_booking_payments_for_customer("CUST0002", valid_b_id)
        assert len(unauthorized_payments) == 0


def test_customer_isolation_damages():
    """Verify customer cannot see damage reports for another customer's booking."""
    c1_bookings = get_customer_bookings("CUST0001")
    if c1_bookings:
        valid_b_id = c1_bookings[0]["booking_id"]
        # Mismatched customer gets 0 records
        unauthorized_damages = get_booking_damages_for_customer("CUST0002", valid_b_id)
        assert len(unauthorized_damages) == 0


def test_agent_queries():
    """Verify support agent search functions."""
    bookings = agent_search_bookings(limit=5)
    assert len(bookings) <= 5
    assert len(bookings) > 0

    fleet = agent_get_fleet_status()
    assert len(fleet) > 0
    assert "hub_name" in fleet[0]

    damages = agent_get_damage_reports(limit=5)
    assert len(damages) <= 5

    summary = agent_get_operational_summary()
    assert "fleet_summary" in summary
    assert "hub_distribution" in summary
    assert "booking_summary" in summary
