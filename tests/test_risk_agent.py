import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, CompanyInfo
from models.verification import VerificationResult
from agents.risk_agent import risk_agent
from utils.output import data_quality_warning_lines

def test_risk_agent():
    # 1. Setup mock state
    state = AgentState(
        target_company="Apple Inc.",
        skip_news=True,
        suppliers=[
            SupplierInfo(name="Foxconn", location="Hsinchu, Taiwan", criticality="High"),
            SupplierInfo(name="Unverified Corp", location="Unknown", criticality="Low"),
            SupplierInfo(name="Russian Metals", location="Moscow, Russia", criticality="Medium")
        ],
        verification_results=[
            VerificationResult(
                supplier_name="Foxconn",
                relationship_type="Supplier",
                verified=True,
                confidence_score=0.95,
                reasoning="Confirmed via multiple public filings."
            ),
            # Unverified Corp is missing from verification_results
            VerificationResult(
                supplier_name="Russian Metals",
                relationship_type="Supplier",
                verified=False,
                confidence_score=0.6,
                reasoning="Sanctions check failed."
            )
        ]
    )

    # 2. Run the agent
    updated_state = risk_agent(state)

    # 3. Assertions
    print(f"\nTotal risks found: {len(updated_state.risk_assessments)}")
    for risk in updated_state.risk_assessments:
        print(f"Supplier: {risk.supplier_name} | Type: {risk.risk_type} | Severity: {risk.severity} | Conf: {risk.confidence:.2f}")
        print(f"  Reasoning: {risk.reasoning}")
        print(f"  Mitigation: {risk.mitigation}")

    # Check for expected risks
    found_foxconn_geo = any(r.supplier_name == "Foxconn" and r.risk_type == "Geopolitical" for r in updated_state.risk_assessments)
    found_russian_metals_geo = any(r.supplier_name == "Russian Metals" and r.risk_type == "Geopolitical" for r in updated_state.risk_assessments)
    found_verification_risk = any("verification" in r.reasoning.lower() for r in updated_state.risk_assessments)

    assert found_foxconn_geo, "Foxconn geopolitical risk not found"
    assert found_russian_metals_geo, "Russian Metals geopolitical risk not found"
    assert not found_verification_risk, "Verification failure should not be represented as a business risk"

    warnings = "\n".join(data_quality_warning_lines(updated_state))
    assert "Missing Verification Result" in warnings
    assert "1. Unverified Corp" in warnings
    assert "Failed Verification" in warnings
    assert "1. Russian Metals" in warnings

    print("\n--- TEST PASSED SUCCESSFULLY ---")

if __name__ == "__main__":
    test_risk_agent()
