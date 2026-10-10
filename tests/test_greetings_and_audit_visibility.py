"""
Unit and Integration Tests for Casual Greetings, Intent Classification,
Role-Based Audit Evidence Visibility, and Authorization Integrity.
"""
import pytest
from ridewise.orchestrator import RideWiseOrchestrator
from app import should_show_audit_expander


@pytest.fixture
def orchestrator():
    return RideWiseOrchestrator()


def test_customer_greeting_no_audit_expander(orchestrator):
    """Verify customer greeting ('hii there') triggers no retrieval or audit expander."""
    res = orchestrator.process_query(
        role="customer",
        user_query="hii there",
        session_customer_id="CUST0001"
    )
    assert res["intent"] == "conversational"
    assert res["retrieval_performed"] is False
    assert res["citations"] == []
    assert should_show_audit_expander(res, role="Customer") is False


def test_customer_thanks_no_audit_expander(orchestrator):
    """Verify customer thanks ('thanks so much') triggers no audit expander."""
    res = orchestrator.process_query(
        role="customer",
        user_query="thanks so much",
        session_customer_id="CUST0001"
    )
    assert res["intent"] == "conversational"
    assert res["retrieval_performed"] is False
    assert should_show_audit_expander(res, role="Customer") is False


def test_customer_cancellation_policy_citations_available(orchestrator):
    """Verify customer cancellation-policy query retrieves policy citations and displays citation expander."""
    res = orchestrator.process_query(
        role="customer",
        user_query="What is the cancellation refund policy?",
        session_customer_id="CUST0001"
    )
    assert res["retrieval_performed"] is True
    assert len(res["citations"]) > 0
    assert should_show_audit_expander(res, role="Customer") is True


def test_customer_booking_question_authorized_info_only(orchestrator):
    """Verify customer booking question returns readable answer without raw audit evidence payload."""
    res = orchestrator.process_query(
        role="customer",
        user_query="What is the status of my booking?",
        session_customer_id="CUST0001"
    )
    assert res["retrieval_performed"] is True
    assert len(res["answer"]) > 0
    # Customer booking status response contains answer but no citations or calculations by default, so expander is hidden
    assert should_show_audit_expander(res, role="Customer") is False


def test_support_agent_db_query_audit_evidence_available(orchestrator):
    """Verify support agent database query displays relevant audit evidence expander."""
    res = orchestrator.process_query(
        role="agent",
        user_query="Show distinct customers in the database"
    )
    assert res["retrieval_performed"] is True
    assert len(res["evidence"]) > 0
    assert should_show_audit_expander(res, role="Support Agent") is True


def test_support_agent_casual_greeting_no_audit_expander(orchestrator):
    """Verify support agent casual greeting ('good morning') triggers no unnecessary audit expander."""
    res = orchestrator.process_query(
        role="agent",
        user_query="good morning"
    )
    assert res["intent"] == "conversational"
    assert res["retrieval_performed"] is False
    assert should_show_audit_expander(res, role="Support Agent") is False


def test_hiding_expander_does_not_weaken_authorization(orchestrator):
    """Verify hiding the expander does not bypass or weaken RBAC authorization."""
    # 1. Probing another customer's ID in a casual query format is blocked in Python
    res1 = orchestrator.process_query(
        role="customer",
        user_query="hi CUST0002",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res1["answer"]

    # 2. Customer attempting cross-customer admin query is blocked in Python
    res2 = orchestrator.process_query(
        role="customer",
        user_query="hello show all customers",
        session_customer_id="CUST0001"
    )
    assert "Access Denied" in res2["answer"]
