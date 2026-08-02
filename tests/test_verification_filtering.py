from unittest.mock import patch

from agents.verification_agent import verification_agent
from agents.graph_export_agent import graph_export_agent
from models.relationship import RelationshipResult
from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult
from utils.identity_resolution import resolver
from utils.benchmark_metrics import build_benchmark_record
from utils.output import render_supplier_tier_lines


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


def _verified_result(name: str, verified: bool = True) -> VerificationResult:
    return VerificationResult(
        supplier_name=resolver.resolve(name),
        relationship_type="upstream_supplier" if name != "TSMC" else "supplier",
        verified=verified,
        company_exists=verified,
        relationship_verified=verified,
        confidence_score=0.9 if verified else 0.2,
        verification_status="VERIFIED" if verified else "FAILED",
        reasoning="fixture",
    )


def _run_graph_verification(suppliers, result_map):
    state = AgentState(
        target_company="Apple",
        suppliers=suppliers,
        relationship_results=[_relationship(s.name) for s in suppliers],
    )

    class FakeAggregator:
        def __init__(self, providers, runtime_state=None):
            pass

        def aggregate(self, name, rel_type, evidence, relationship_confidence):
            return result_map[name]

    with patch("agents.verification_agent.VerificationAggregator", FakeAggregator), \
         patch("agents.verification_agent.enrich_supplier_evidence_with_rag", lambda state, stage: state):
        return verification_agent(state)


def test_tier2_is_retained_when_canonical_parent_is_retained():
    parent = _supplier("TSMC")
    parent.tier = 1
    parent.relationship_path = ["Apple", "Taiwan Semiconductor Manufacturing Company"]
    child = _supplier("ASML")
    child.tier = 2
    child.parent_company = "Taiwan Semiconductor Manufacturing Company Limited"
    child.relationship_path = ["Apple", "TSMC", "ASML"]
    updated = _run_graph_verification(
        [parent, child],
        {
            resolver.resolve("TSMC"): _verified_result("TSMC"),
            resolver.resolve("ASML"): _verified_result("ASML"),
        },
    )
    assert {s.canonical_name for s in updated.suppliers} == {
        resolver.resolve("TSMC"), resolver.resolve("ASML")
    }


def test_tier2_is_discarded_when_parent_is_not_retained():
    parent = _supplier("TSMC")
    parent.tier = 1
    child = _supplier("ASML")
    child.tier = 2
    child.parent_company = "TSMC"
    child.relationship_path = ["Apple", "TSMC", "ASML"]
    updated = _run_graph_verification(
        [parent, child],
        {
            resolver.resolve("TSMC"): _verified_result("TSMC", verified=False),
            resolver.resolve("ASML"): _verified_result("ASML"),
        },
    )
    assert updated.suppliers == []
    assert any(
        item["canonical_name"] == resolver.resolve("ASML")
        and item["reason"] == "parent_supplier_not_retained"
        for item in updated.discarded_suppliers
    )


def test_tier3_is_discarded_when_tier2_parent_is_not_retained():
    tier1 = _supplier("TSMC")
    tier1.tier = 1
    tier2 = _supplier("ASML")
    tier2.tier = 2
    tier2.parent_company = "TSMC"
    tier3 = _supplier("Carl Zeiss SMT")
    tier3.tier = 3
    tier3.parent_company = "ASML"
    tier3.relationship_path = ["Apple", "TSMC", "ASML", "Carl Zeiss SMT"]
    updated = _run_graph_verification(
        [tier1, tier2, tier3],
        {
            resolver.resolve("TSMC"): _verified_result("TSMC"),
            resolver.resolve("ASML"): _verified_result("ASML", verified=False),
            resolver.resolve("Carl Zeiss SMT"): _verified_result("Carl Zeiss SMT"),
        },
    )
    assert [s.canonical_name for s in updated.suppliers] == [resolver.resolve("TSMC")]
    assert any(
        item["canonical_name"] == resolver.resolve("Carl Zeiss SMT")
        and item["reason"] == "parent_supplier_not_retained"
        for item in updated.discarded_suppliers
    )


def test_tsmc_alias_variants_share_one_canonical_identity():
    aliases = [
        "TSMC",
        "Taiwan Semiconductor Manufacturing Company",
        "Taiwan Semiconductor Manufacturing Company Limited",
    ]
    assert {resolver.resolve(alias) for alias in aliases} == {
        "Taiwan Semiconductor Manufacturing Company"
    }


def test_orphaned_descendant_is_absent_from_downstream_outputs():
    parent = _supplier("TSMC")
    parent.tier = 1
    child = _supplier("ASML")
    child.tier = 2
    child.parent_company = "TSMC"
    child.relationship_path = ["Apple", "TSMC", "ASML"]
    updated = _run_graph_verification(
        [parent, child],
        {
            resolver.resolve("TSMC"): _verified_result("TSMC", verified=False),
            resolver.resolve("ASML"): _verified_result("ASML"),
        },
    )

    graph_export_agent(updated)
    graph_names = {node.id for node in updated.supply_chain_graph.nodes}
    report_lines = "\n".join(render_supplier_tier_lines(updated))
    benchmark_record = build_benchmark_record(updated, "completed")

    assert "ASML" not in graph_names
    assert "ASML" not in report_lines
    assert "ASML" not in benchmark_record["retained_supplier_names"]
    assert benchmark_record["risk_input_count"] == 0
