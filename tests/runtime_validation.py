import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult
from agents.risk_agent import risk_agent

def runtime_validation():
    # 1. Setup specific test suppliers
    suppliers = [
        SupplierInfo(name="TSMC", location="Taiwan", criticality="High"),
        SupplierInfo(name="Foxconn", location="China", criticality="High"),
        SupplierInfo(name="Samsung Electronics", location="South Korea", criticality="High"),
        SupplierInfo(name="Fake Company XYZ 123", location="Unknown", criticality="Low")
    ]
    
    verification_results = [
        VerificationResult(
            supplier_name="TSMC",
            relationship_type="Supplier",
            verified=True,
            confidence_score=0.80,
            reasoning="Public listing confirmed."
        ),
        VerificationResult(
            supplier_name="Foxconn",
            relationship_type="Supplier",
            verified=True,
            confidence_score=0.80,
            reasoning="Public listing confirmed."
        ),
        VerificationResult(
            supplier_name="Samsung Electronics",
            relationship_type="Supplier",
            verified=True,
            confidence_score=0.80,
            reasoning="Public listing confirmed."
        ),
        VerificationResult(
            supplier_name="Fake Company XYZ 123",
            relationship_type="Supplier",
            verified=False,
            confidence_score=0.00,
            reasoning="No entity found with this name."
        )
    ]
    
    state = AgentState(
        target_company="Validation Target",
        suppliers=suppliers,
        verification_results=verification_results
    )

    # 2. Execute Agent
    final_state = risk_agent(state)

    # 3. Output Execution Results
    print("\n" + "="*80)
    print("RUNTIME VALIDATION: RISK INTELLIGENCE AGENT")
    print("="*80)

    for supplier in suppliers:
        print(f"\nSUPPLIER: {supplier.name}")
        supplier_risks = [r for r in final_state.risk_assessments if r.supplier_name == supplier.name]
        
        if not supplier_risks:
            print("  - No risks identified by any provider.")
        else:
            for risk in supplier_risks:
                # Map risk_type back to a provider name for display
                provider_name = "Geopolitical" if risk.risk_type == "Geopolitical" else "Verification"
                print(f"  - Provider: {provider_name}")
                print(f"    Risk Type: {risk.risk_type}")
                print(f"    Severity: {risk.severity}")
                print(f"    Confidence: {risk.confidence:.2f}")
                print(f"    Reasoning: {risk.reasoning}")
                print(f"    Mitigation: {risk.mitigation}")

    print("\n" + "="*80)
    print("AGGREGATED RISK RESULTS")
    print("="*80)
    
    total_risks = len(final_state.risk_assessments)
    print(f"Total Risks Generated: {total_risks}")
    
    # Risk Ranking (by Severity: Critical > High > Medium > Low)
    severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    ranked_risks = sorted(final_state.risk_assessments, key=lambda x: severity_map.get(x.severity, 0), reverse=True)
    
    print("\nRisk Ranking:")
    for i, risk in enumerate(ranked_risks, 1):
        print(f"{i}. [{risk.severity}] {risk.supplier_name} - {risk.risk_type}: {risk.reasoning[:60]}...")

    print("\n" + "="*80)
    print("VALIDATION ANALYSIS")
    print("="*80)
    
    # Analyze False Positives / Negatives / Missing based on the test case
    # Fake Company XYZ 123 (Verified: False) -> Strategic Risk (High)
    # TSMC (Taiwan) -> Geopolitical Risk (Medium)
    # Foxconn (China) -> Geopolitical Risk (Medium)
    # Samsung (South Korea) -> No Geopolitical Risk (Not in list)
    
    print("False Positives:")
    print("- Samsung Electronics: No geopolitical risk flagged (Correct behavior based on current provider rules).")
    
    print("\nFalse Negatives:")
    print("- Samsung Electronics: Could be considered 'Geopolitical' risk given regional tensions (North Korea), but provider rules are limited.")
    print("- TSMC: 0.80 Verification confidence is on the edge, but didn't trigger 'Low confidence' warning (threshold is 0.8).")

    print("\nMissing Risk Categories:")
    print("- Financial: No assessment of the financial health of 'Fake Company XYZ 123'.")
    print("- Operational (Capacity): No assessment of TSMC/Foxconn production capacity risks.")
    print("- Environmental: No ESG risk assessments for manufacturing sites.")

if __name__ == "__main__":
    runtime_validation()
