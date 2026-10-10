"""
Unit Tests for Database Question Answering, SQL Intent Routing, and RBAC Authorization
Tests all 7 required scenarios across Customer and Support Agent roles.
"""
import pytest
from ridewise.orchestrator import RideWiseOrchestrator
from ridewise import db


@pytest.fixture
def orchestrator():
    return RideWiseOrchestrator()


# ==========================================
# 1. Distinct Customers List & Privacy
# ==========================================
def test_qa_distinct_customers_agent(orchestrator):
    """Test Support Agent querying distinct customers list."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show me the distinct customers"
    )
    assert res is not None
    assert "CUST0001" in res["evidence"] or "Distinct Customers List" in res["evidence"]
    # Verify sensitive PII is excluded for privacy
    assert "Privacy Notice: Sensitive PII" in res["evidence"]
    assert "aarav.sharma@gmail.com" not in res["evidence"]


def test_qa_distinct_customers_customer_rbac(orchestrator):
    """Test Customer attempting to query distinct customers list (must be blocked)."""
    res = orchestrator.process_query(
        role="customer",
        user_query="Show me the distinct customers",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res["answer"]
    assert "restricted to Support Agents" in res["answer"]


# ==========================================
# 2. Distinct Customers Count
# ==========================================
def test_qa_distinct_customers_count_agent(orchestrator):
    """Test Support Agent asking for total distinct customer count."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many distinct customers are there?"
    )
    assert "Distinct Customer Count" in res["evidence"]
    assert "200" in res["evidence"] or "200" in res["answer"]


def test_qa_distinct_customers_count_customer_rbac(orchestrator):
    """Test Customer attempting to query distinct customer count (must be blocked)."""
    res = orchestrator.process_query(
        role="customer",
        user_query="How many distinct customers are there?",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res["answer"]


# ==========================================
# 3. Customers Who Have Never Booked
# ==========================================
def test_qa_customers_never_booked_agent(orchestrator):
    """Test Support Agent querying customers who have never placed a booking."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show customers who have never booked"
    )
    assert "Customers Who Have Never Booked" in res["evidence"]
    assert len(res["evidence"]) > 0


def test_qa_customers_never_booked_customer_rbac(orchestrator):
    """Test Customer attempting to query customers who have never booked (must be blocked)."""
    res = orchestrator.process_query(
        role="customer",
        user_query="Show customers who have never booked",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res["answer"]


# ==========================================
# 4. Booking Details Lookup
# ==========================================
def test_qa_booking_details_agent(orchestrator):
    """Test Support Agent retrieving details for a specific booking ID."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show the booking details for B-0001"
    )
    assert "Booking Details for B-0001" in res["evidence"]
    assert "Vehicle:" in res["evidence"] or "Customer:" in res["evidence"]


def test_qa_booking_details_customer_own(orchestrator):
    """Test Customer retrieving their own booking details."""
    # Find a valid booking for CUST0001
    cust_b = db.get_customer_bookings("CUST0001")
    if cust_b:
        b_id = cust_b[0]["booking_id"]
        res = orchestrator.process_query(
            role="customer",
            user_query=f"Show booking details for {b_id}",
            session_customer_id="CUST0001"
        )
        assert b_id in res["evidence"]


def test_qa_booking_details_customer_cross_access(orchestrator):
    """Test Customer attempting to view another customer's booking ID."""
    res = orchestrator.process_query(
        role="customer",
        user_query="Show booking details for CUST0002",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res["answer"]


# ==========================================
# 5. Failed Payments Query
# ==========================================
def test_qa_failed_payments_agent(orchestrator):
    """Test Support Agent querying system-wide failed payments."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show failed payments"
    )
    assert "System Failed Payments" in res["evidence"]


def test_qa_failed_payments_customer(orchestrator):
    """Test Customer querying failed payments (filtered to their account)."""
    res = orchestrator.process_query(
        role="customer",
        user_query="Show failed payments",
        session_customer_id="CUST0001"
    )
    assert "Customer Failed Payments" in res["evidence"]


# ==========================================
# 6. Damage Reports for Vehicle
# ==========================================
def test_qa_damage_reports_vehicle_agent(orchestrator):
    """Test Support Agent querying damage reports for a vehicle."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show damage reports for vehicle V-0001"
    )
    assert "Damage Reports for Vehicle 'V-0001'" in res["evidence"]


def test_qa_damage_reports_vehicle_customer(orchestrator):
    """Test Customer querying damage reports for a vehicle."""
    res = orchestrator.process_query(
        role="customer",
        user_query="Show damage reports for vehicle V-0001",
        session_customer_id="CUST0001"
    )
    assert "Customer Damage Reports for Vehicle 'V-0001'" in res["evidence"]


# ==========================================
# 7. Cancellation Refund Policy Query
# ==========================================
def test_qa_cancellation_policy(orchestrator):
    """Test retrieving cancellation refund policy rules & document citations."""
    res = orchestrator.process_query(
        role="customer",
        user_query="What is the cancellation refund policy?",
        session_customer_id="CUST0001"
    )
    assert res["citations"] is not None
    assert len(res["citations"]) > 0
    assert "Policy Evidence" in res["evidence"] or "Policy Rules" in res["evidence"]
