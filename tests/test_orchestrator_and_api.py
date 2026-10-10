"""
Unit and Integration Tests for Orchestrator and API Resilience
"""
from ridewise.orchestrator import RideWiseOrchestrator
from ridewise.llm_client import RideWiseLLMClient


class MockFailingLLMClient(RideWiseLLMClient):
    """Simulates API failure (e.g. rate-limit, timeout, network error)."""
    def generate_response(self, messages, temperature=0.1):
        raise ConnectionError("Simulated 429 Rate Limit / Timeout on Azure LLM")


def test_orchestrator_customer_query():
    """Verify customer end-to-end query processing with live NeoStats LLM."""
    orch = RideWiseOrchestrator()
    res = orch.process_query(
        role="customer",
        user_query="What is my name, KYC status, and how many bookings do I have?",
        session_customer_id="CUST0001"
    )
    assert res is not None
    assert len(res["answer"]) > 0
    assert "CUST0001" in res["evidence"]


def test_orchestrator_agent_query():
    """Verify support agent end-to-end query processing."""
    orch = RideWiseOrchestrator()
    res = orch.process_query(
        role="agent",
        user_query="Give me a summary of vehicle fleet and hub distribution."
    )
    assert res is not None
    assert len(res["answer"]) > 0
    assert "Fleet Status Breakdown" in res["evidence"]


def test_orchestrator_graceful_fallback_on_api_error():
    """Verify that when LLM fails, orchestrator gracefully returns deterministic evidence instead of crashing."""
    failing_client = MockFailingLLMClient()
    orch = RideWiseOrchestrator(llm_client=failing_client)

    res = orch.process_query(
        role="customer",
        user_query="What is my booking status?",
        session_customer_id="CUST0001"
    )
    assert res["is_fallback"] is True
    assert "LLM synthesis temporarily unavailable" in res["answer"]
    assert "CUST0001" in res["answer"]
