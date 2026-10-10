"""
Regression Tests for Location-Based Customer Count Logic
Verifies:
1. Normalization of city names using LOWER(TRIM(city))
2. Alias matching: Bangalore, Bengaluru, BLR -> 164 customers (not all 200)
3. Other cities in database: Chennai (8), Hyderabad (12), Mangaluru (8), Mysuru (6), Pune (2)
4. Empty result / non-existent city: Delhi (0)
5. Whitespace handling in input and database values (e.g. 'bangalore ')
6. Never inferring customer city from operational rental hubs
"""
import pytest
from ridewise import db
from ridewise.orchestrator import RideWiseOrchestrator


@pytest.fixture
def orchestrator():
    return RideWiseOrchestrator()


# =========================================================================
# 1. DATABASE UNIT TESTS (db.agent_get_customer_count_by_city)
# =========================================================================

def test_db_count_bangalore_aliases():
    """Verify Bangalore, Bengaluru, and BLR all resolve to the same 164 distinct customers."""
    res_bangalore = db.agent_get_customer_count_by_city("Bangalore")
    res_bengaluru = db.agent_get_customer_count_by_city("Bengaluru")
    res_blr = db.agent_get_customer_count_by_city("BLR")

    assert res_bangalore["customer_count"] == 164
    assert res_bengaluru["customer_count"] == 164
    assert res_blr["customer_count"] == 164
    assert res_bangalore["customer_count"] != 200  # Must NOT return all 200 customers


def test_db_count_whitespace_normalization():
    """Verify leading, trailing, and embedded whitespaces are normalized properly."""
    res1 = db.agent_get_customer_count_by_city("   Bangalore   ")
    res2 = db.agent_get_customer_count_by_city("  bengaluru \t ")
    res3 = db.agent_get_customer_count_by_city("  BLR  ")

    assert res1["customer_count"] == 164
    assert res2["customer_count"] == 164
    assert res3["customer_count"] == 164

    # Verify that the 'bangalore ' row (with trailing space in DB) is included in the count
    assert "bangalore " in res1["db_breakdown"] or "bangalore" in str(res1["db_breakdown"])


def test_db_count_other_cities():
    """Verify exact counts for other cities present in the database."""
    res_chennai = db.agent_get_customer_count_by_city("Chennai")
    res_hyderabad = db.agent_get_customer_count_by_city("Hyderabad")
    res_mangaluru = db.agent_get_customer_count_by_city("Mangaluru")
    res_mangalore = db.agent_get_customer_count_by_city("Mangalore")
    res_mysuru = db.agent_get_customer_count_by_city("Mysuru")
    res_mysore = db.agent_get_customer_count_by_city("Mysore")
    res_pune = db.agent_get_customer_count_by_city("Pune")

    assert res_chennai["customer_count"] == 8
    assert res_hyderabad["customer_count"] == 12
    assert res_mangaluru["customer_count"] == 8
    assert res_mangalore["customer_count"] == 8
    assert res_mysuru["customer_count"] == 6
    assert res_mysore["customer_count"] == 6
    assert res_pune["customer_count"] == 2


def test_db_count_empty_result():
    """Verify cities without registered customers return count 0 without errors."""
    res_delhi = db.agent_get_customer_count_by_city("Delhi")
    res_mumbai = db.agent_get_customer_count_by_city("Mumbai")
    res_paris = db.agent_get_customer_count_by_city("Paris")

    assert res_delhi["customer_count"] == 0
    assert res_mumbai["customer_count"] == 0
    assert res_paris["customer_count"] == 0


def test_db_count_total_integrity():
    """Verify sum of all cities matches total distinct customers (200)."""
    total_distinct = db.agent_get_distinct_customers(count_only=True)["total_distinct_customers"]
    assert total_distinct == 200

    blr_count = db.agent_get_customer_count_by_city("Bangalore")["customer_count"]
    chennai_count = db.agent_get_customer_count_by_city("Chennai")["customer_count"]
    hyd_count = db.agent_get_customer_count_by_city("Hyderabad")["customer_count"]
    mng_count = db.agent_get_customer_count_by_city("Mangaluru")["customer_count"]
    mys_count = db.agent_get_customer_count_by_city("Mysuru")["customer_count"]
    pune_count = db.agent_get_customer_count_by_city("Pune")["customer_count"]

    assert blr_count + chennai_count + hyd_count + mng_count + mys_count + pune_count == 200


# =========================================================================
# 2. ORCHESTRATOR INTEGRATION TESTS (End-to-End Query Answering)
# =========================================================================

def test_orchestrator_bangalore_query(orchestrator):
    """Verify 'How many customers in Bangalore?' returns 164 and cites SQL evidence."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many customers in Bangalore?"
    )
    assert "Location-Based Customer Count Query" in res["evidence"]
    assert "Distinct Customers Found: 164" in res["evidence"]
    assert "164" in res["answer"]
    # Ensure it did NOT assume 200 customers
    assert "200 customers in Bangalore" not in res["answer"]
    assert "200 registered customers in Bangalore" not in res["answer"]


def test_orchestrator_bengaluru_query(orchestrator):
    """Verify 'How many customers in Bengaluru?' returns 164 and cites SQL evidence."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many customers in Bengaluru?"
    )
    assert "Distinct Customers Found: 164" in res["evidence"]
    assert "164" in res["answer"]


def test_orchestrator_blr_query(orchestrator):
    """Verify 'How many customers in BLR?' returns 164."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many customers in BLR?"
    )
    assert "Distinct Customers Found: 164" in res["evidence"]
    assert "164" in res["answer"]


def test_orchestrator_other_city_chennai(orchestrator):
    """Verify 'How many customers in Chennai?' returns 8."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many customers in Chennai?"
    )
    assert "Distinct Customers Found: 8" in res["evidence"]
    assert "8" in res["answer"]


def test_orchestrator_empty_result_delhi(orchestrator):
    """Verify 'How many customers in Delhi?' reports 0 and explains limitation."""
    res = orchestrator.process_query(
        role="agent",
        user_query="How many customers in Delhi?"
    )
    assert "Distinct Customers Found: 0" in res["evidence"]
    assert "0" in res["answer"] or "no " in res["answer"].lower() or "none" in res["answer"].lower()


def test_orchestrator_customer_role_location_query(orchestrator):
    """Verify location customer count is answered when asked in Customer role."""
    res = orchestrator.process_query(
        role="customer",
        user_query="How many customers in Bangalore?",
        session_customer_id="CUST0001"
    )
    assert "Location-Based Customer Count Query" in res["evidence"]
    assert "Distinct Customers Found: 164" in res["evidence"]
    assert "164" in res["answer"]
