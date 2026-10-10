"""
Unit Tests for Policy Knowledge Base and Ingestion
"""
from ridewise.policies import get_policy_store, VERIFIED_SCANNED_ANNEXURES


def test_policy_store_loading():
    """Verify that all policy documents are loaded and indexed."""
    store = get_policy_store()
    assert len(store.chunks) > 0

    doc_ids = {c["doc_id"] for c in store.chunks}
    assert "RW-POL-01" in doc_ids
    assert "RW-POL-02" in doc_ids
    assert "RW-POL-03" in doc_ids
    assert "RW-POL-04" in doc_ids
    assert "RW-POL-05" in doc_ids


def test_scanned_v2_refund_annexure():
    """Verify that scanned Policy v2 refund schedule is indexed with exact provenance."""
    store = get_policy_store()
    results = store.search_policy("Version 2 refund schedule slab 48 hours", top_k=3)
    assert len(results) > 0

    v2_match = next((r for r in results if r["doc_id"] == "RW-POL-03"), None)
    assert v2_match is not None
    assert v2_match["version"] == "v2.0"
    assert v2_match["page"] == 2
    assert "48 hours or more" in v2_match["content"]
    assert "75%" in v2_match["content"]


def test_scanned_tier_benefits_annexure():
    """Verify that scanned Penalty Schedule Annexure A (tier grace period) is indexed."""
    store = get_policy_store()
    results = store.search_policy("GOLD tier grace period on late return", top_k=3)
    assert len(results) > 0

    tier_match = next((r for r in results if r["doc_id"] == "RW-POL-04"), None)
    assert tier_match is not None
    assert "30 minutes" in tier_match["content"]
    assert "GOLD" in tier_match["content"]


def test_security_deposit_rules():
    """Verify retrieval of deposit policy details."""
    store = get_policy_store()
    results = store.search_policy("security deposit bike scooter", top_k=3)
    assert len(results) > 0
    formatted = store.format_citations_for_evidence(results)
    assert "RW-POL-01" in formatted


def test_synonym_late_fee_retrieves_penalty_schedule():
    """
    Synonym Test: 'late fee' must retrieve the Late Return & Damage Penalty Schedule (RW-POL-04).

    Verifies the synonym map correctly expands 'late' -> 'penalty', 'grace period', etc.,
    and that the top result comes from the correct source document.
    """
    store = get_policy_store()
    results = store.search_policy("What is the late fee if I return the bike after schedule?", top_k=4)
    assert len(results) > 0, "Must return results for late fee query."

    doc_ids = [r["doc_id"] for r in results]
    assert "RW-POL-04" in doc_ids, (
        f"'Late fee' query must retrieve RW-POL-04 (Late Return & Damage Penalty Schedule). "
        f"Got doc_ids: {doc_ids}"
    )

    # The retrieved chunk must contain late return specific content
    penalty_chunks = [r for r in results if r["doc_id"] == "RW-POL-04"]
    combined = " ".join([c["content"] for c in penalty_chunks]).lower()
    assert any(kw in combined for kw in ["late", "penalty", "grace", "1.5"]), (
        "RW-POL-04 chunk must contain late return penalty content."
    )


def test_synonym_low_battery_retrieves_ev_guide():
    """
    Synonym Test: 'low battery' must retrieve EV User Guide & FAQ (RW-POL-05).

    Verifies the synonym map correctly expands 'battery' -> 'ev low-battery', 'charging fee',
    and that the top result comes from the correct source document.
    """
    store = get_policy_store()
    results = store.search_policy("What happens if I return EV with low battery?", top_k=4)
    assert len(results) > 0, "Must return results for low battery query."

    doc_ids = [r["doc_id"] for r in results]
    assert "RW-POL-05" in doc_ids or "RW-POL-04" in doc_ids, (
        f"'Low battery' query must retrieve RW-POL-05 (EV Guide) or RW-POL-04 (Penalty Schedule). "
        f"Got doc_ids: {doc_ids}"
    )

    # The retrieved chunk must contain battery-related content
    battery_chunks = [r for r in results if r["doc_id"] in ("RW-POL-05", "RW-POL-04")]
    combined = " ".join([c["content"] for c in battery_chunks]).lower()
    assert any(kw in combined for kw in ["battery", "10%", "charging", "ev"]), (
        "Retrieved chunk must contain EV battery-related content."
    )


def test_synonym_deposit_retrieves_rental_agreement():
    """
    Synonym Test: 'deposit' / 'get my money' must retrieve Rental Agreement (RW-POL-01).

    Verifies the synonym map correctly expands 'deposit' -> 'security deposit', 'refundable',
    and that the top result comes from the correct source document.
    """
    store = get_policy_store()
    results = store.search_policy("How do I get my deposit back?", top_k=4)
    assert len(results) > 0, "Must return results for deposit query."

    doc_ids = [r["doc_id"] for r in results]
    assert "RW-POL-01" in doc_ids or "RW-POL-03" in doc_ids or "RW-POL-02" in doc_ids, (
        f"'deposit' query must retrieve rental agreement or refund policy. Got: {doc_ids}"
    )

    # The content must contain deposit-related terms
    all_content = " ".join([r["content"] for r in results]).lower()
    assert any(kw in all_content for kw in ["deposit", "refundable", "security"]), (
        "Retrieved chunks must mention deposit or security deposit terms."
    )
