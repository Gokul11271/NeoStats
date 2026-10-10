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
