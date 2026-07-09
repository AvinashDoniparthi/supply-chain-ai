from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import main
from models.state import (
    AgentState,
    CompanyInfo,
    ExecutiveReport,
    RiskAnalysis,
    SupplierConfidence,
    SupplierCriticality,
    SupplierInfo,
    SupplyChainHealth,
)
from models.verification import VerificationResult
from retrieval import knowledge_report_generator as report_generator


def _sample_state() -> AgentState:
    state = AgentState(target_company="Apple", execution_mode="llm", max_depth=3)
    state.company = CompanyInfo(name="Apple")
    state.suppliers = [
        SupplierInfo(
            name="TSMC",
            canonical_name="Taiwan Semiconductor Manufacturing Company",
            location="Taiwan",
            products=["Semiconductor foundry"],
            tier=1,
            parent_company="Apple",
            relationship_path=["Apple", "Taiwan Semiconductor Manufacturing Company"],
            discovery_confidence=0.96,
            propagated_confidence=0.96,
        ),
        SupplierInfo(
            name="ASML",
            canonical_name="ASML",
            location="Netherlands",
            products=["Lithography systems"],
            tier=2,
            parent_company="Taiwan Semiconductor Manufacturing Company",
            relationship_path=[
                "Apple",
                "Taiwan Semiconductor Manufacturing Company",
                "ASML",
            ],
            discovery_confidence=0.88,
            propagated_confidence=0.82,
        ),
    ]
    state.supply_chain_health = SupplyChainHealth(
        overall_score=81.0,
        status="Good",
        supplier_count=2,
        critical_suppliers=1,
        high_risk_suppliers=1,
        summary="Healthy with concentration risk.",
    )
    state.verification_results = [
        VerificationResult(
            supplier_name="TSMC",
            relationship_type="supplier",
            verified=True,
            confidence_score=0.94,
            reasoning="Verified via public sources.",
        ),
        VerificationResult(
            supplier_name="ASML",
            relationship_type="upstream_supplier",
            verified=False,
            confidence_score=0.41,
            reasoning="Incomplete verification.",
        ),
    ]
    state.supplier_confidence_scores = [
        SupplierConfidence(
            supplier_name="TSMC",
            discovery_confidence=0.96,
            relationship_confidence=0.95,
            verification_confidence=0.94,
            risk_confidence=0.76,
            final_confidence=0.91,
            reasoning="Strong direct foundry evidence.",
        ),
        SupplierConfidence(
            supplier_name="ASML",
            discovery_confidence=0.88,
            relationship_confidence=0.82,
            verification_confidence=0.41,
            risk_confidence=0.64,
            final_confidence=0.68,
            reasoning="Upstream supplier with partial verification.",
        ),
    ]
    state.supplier_criticality_scores = [
        SupplierCriticality(
            supplier_name="TSMC",
            criticality_score=0.9,
            criticality_level="Critical",
            reasoning="Core foundry.",
        ),
        SupplierCriticality(
            supplier_name="ASML",
            criticality_score=0.72,
            criticality_level="High",
            reasoning="Upstream lithography dependency.",
        ),
    ]
    state.risk_assessments = [
        RiskAnalysis(
            supplier_name="TSMC",
            risk_type="Geopolitical",
            severity="Medium",
            confidence=0.7,
            reasoning="Taiwan geopolitical exposure.",
            mitigation="Monitor regional developments and diversify capacity.",
        )
    ]
    state.executive_report = ExecutiveReport(
        company_name="Apple",
        overall_health_score=81.0,
        health_status="Good",
        executive_summary="Apple has a concentrated but well-verified semiconductor supply base.",
        key_suppliers=["TSMC", "ASML"],
        major_risks=["Geopolitical risk for TSMC: Taiwan exposure"],
        recommendations=["Diversify foundry exposure."],
    )
    return state


def test_generate_knowledge_report_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator, "KNOWLEDGE_BASE_DIR", tmp_path / "knowledge_base")

    path = report_generator.generate_knowledge_report(_sample_state())

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "# Apple" in content
    assert "## Executive Summary" in content
    assert "## Tier 1 Suppliers" in content
    assert "TSMC" in content
    assert "## Report Metadata" in content
    assert "Generated Timestamp:" in content
    assert "Mode: llm" in content


def test_run_analysis_generates_knowledge_report(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator, "KNOWLEDGE_BASE_DIR", tmp_path / "knowledge_base")
    monkeypatch.setattr(main, "index_knowledge_base", MagicMock())
    monkeypatch.setattr(main, "render_final_report", lambda state: None)
    monkeypatch.setattr(main.supply_chain_app, "invoke", lambda state: _sample_state())

    final_state = main.run_analysis("Apple")

    report_path = tmp_path / "knowledge_base" / "Apple" / "apple_supply_chain_report.md"
    assert report_path.exists()
    assert final_state.company.name == "Apple"
    assert main.index_knowledge_base.called
