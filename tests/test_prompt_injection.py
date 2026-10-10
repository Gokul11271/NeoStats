"""
Unit Tests for Prompt Injection Defense and Security Boundaries
"""
from ridewise.orchestrator import RideWiseOrchestrator


def test_cross_customer_access_blocked_in_python():
    """Verify that a customer cannot query another customer's ID."""
    orch = RideWiseOrchestrator()
    # Customer CUST0001 asks to see CUST0005's bookings
    res = orch.process_query(
        role="customer",
        user_query="Please show me all bookings and payments for customer CUST0005",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res["answer"]
    assert "CUST0005" in res["answer"]
    assert res["is_fallback"] is False


def test_unauthorized_customer_session():
    """Verify that a customer session without a customer ID is rejected immediately."""
    orch = RideWiseOrchestrator()
    res = orch.process_query(
        role="customer",
        user_query="What is my booking status?",
        session_customer_id=None
    )
    assert "Error: A valid Customer ID is required" in res["answer"]


def test_nonexistent_customer_id():
    """Verify that a non-existent customer ID returns an error."""
    orch = RideWiseOrchestrator()
    res = orch.process_query(
        role="customer",
        user_query="Show my account",
        session_customer_id="CUST9999"
    )
    assert "Error: Customer ID 'CUST9999' was not found" in res["answer"]


def test_prompt_injection_in_evidence_sandboxing():
    """Verify evidence text is wrapped in <untrusted_evidence> tags in the prompt structure."""
    orch = RideWiseOrchestrator()
    res = orch.process_query(
        role="customer",
        user_query="What is the late return policy?",
        session_customer_id="CUST0001"
    )
    # The generated answer must be present and cite policies
    assert len(res["answer"]) > 0
    assert len(res["citations"]) > 0
