from unittest.mock import patch

from agents.verification_agent import verification_agent
from models.relationship import RelationshipResult
from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult


def _supplier(name: str) -> SupplierInfo:
    return SupplierInfo(name=name, canonical_name=name, location="Unknown")


def _relationship(name: str) -> RelationshipResult:
    return RelationshipResult(
        target_company="Apple",
        candidate_company=name,
        relationship_type="supplier",
        confidence_score=0.9,
        reasoning="Supplier evidence",
        evidence_text="Supplier evidence",
    )


def test_verification_removes_failed_suppliers_and_preserves_discard_metrics():
    state = AgentState(
        target_company="Apple",
        suppliers=[_supplier("Good Supplier"), _supplier("No Company"), _supplier("Low Confidence")],
        relationship_results=[
            _relationship("Good Supplier"),
            _relationship("No Company"),
            _relationship("Low Confidence"),
        ],
    )
    results = {
        "Good Supplier": VerificationResult(
            supplier_name="Good Supplier",
            relationship_type="supplier",
            verified=True,
            company_exists=True,
            relationship_verified=True,
            confidence_score=0.9,
            verification_status="VERIFIED",
            reasoning="Verified",
        ),
        "No Company": VerificationResult(
            supplier_name="No Company",
            relationship_type="supplier",
            verified=False,
            company_exists=False,
            confidence_score=0.2,
            verification_status="FAILED",
            reasoning="Entity does not exist",
        ),
        "Low Confidence": VerificationResult(
            supplier_name="Low Confidence",
            relationship_type="supplier",
            verified=True,
            company_exists=True,
            relationship_verified=True,
            confidence_score=0.4,
            verification_status="VERIFIED",
            reasoning="Below threshold",
        ),
    }

    class FakeAggregator:
        def __init__(self, providers, runtime_state=None):
            pass

        def aggregate(self, name, rel_type, evidence, relationship_confidence):
            return results[name]

    with patch("agents.verification_agent.VerificationAggregator", FakeAggregator), \
         patch("agents.verification_agent.enrich_supplier_evidence_with_rag", lambda state, stage: state):
        updated = verification_agent(state)

    assert [supplier.name for supplier in updated.suppliers] == ["Good Supplier"]
    assert [supplier.name for supplier in updated.discovered_suppliers] == [
        "Good Supplier",
        "No Company",
        "Low Confidence",
    ]
    assert [result.supplier_name for result in updated.verification_results] == ["Good Supplier"]
    assert {item["supplier_name"] for item in updated.discarded_suppliers} == {
        "No Company",
        "Low Confidence",
    }
    assert any(item["reason"] == "company_exists=False" for item in updated.discarded_suppliers)


def test_verification_status_failed_is_never_retained():
    result = VerificationResult(
        supplier_name="Failed Status",
        relationship_type="supplier",
        verified=True,
        company_exists=True,
        relationship_verified=True,
        confidence_score=0.9,
        verification_status="FAILED",
        reasoning="Failed status must win",
    )
    state = AgentState(
        target_company="Apple",
        suppliers=[_supplier("Failed Status")],
        relationship_results=[_relationship("Failed Status")],
    )

    class FakeAggregator:
        def __init__(self, providers, runtime_state=None):
            pass

        def aggregate(self, name, rel_type, evidence, relationship_confidence):
            return result

    with patch("agents.verification_agent.VerificationAggregator", FakeAggregator), \
         patch("agents.verification_agent.enrich_supplier_evidence_with_rag", lambda state, stage: state):
        updated = verification_agent(state)

    assert updated.suppliers == []
    assert updated.discarded_suppliers[0]["reason"] == "verification_status=FAILED"
