import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, CompanyInfo
from models.relationship import RelationshipResult
from models.verification import VerificationResult
from agents.confidence_agent import confidence_agent

def simulate_apple_trace():
    state = AgentState(target_company="Apple Inc.")
    
    # Mocking data for Apple suppliers
    state.suppliers = [
        SupplierInfo(name="Foxconn", location="Taiwan", discovery_confidence=0.95),
        SupplierInfo(name="TSMC", location="Taiwan", discovery_confidence=0.98),
        SupplierInfo(name="Supplier XYZ", location="Unknown", discovery_confidence=0.45)
    ]
    
    state.relationship_results = [
        RelationshipResult(target_company="Apple Inc.", candidate_company="Foxconn", relationship_type="supplier", confidence_score=0.99, reasoning="Main assembler.", evidence_text="..."),
        RelationshipResult(target_company="Apple Inc.", candidate_company="TSMC", relationship_type="supplier", confidence_score=0.98, reasoning="Chip manufacturer.", evidence_text="..."),
        RelationshipResult(target_company="Apple Inc.", candidate_company="Supplier XYZ", relationship_type="unknown", confidence_score=0.40, reasoning="Vague connection.", evidence_text="...")
    ]
    
    state.verification_results = [
        VerificationResult(supplier_name="Foxconn", relationship_type="supplier", verified=True, confidence_score=0.90, reasoning="Verified via SEC filings."),
        VerificationResult(supplier_name="TSMC", relationship_type="supplier", verified=True, confidence_score=0.95, reasoning="Verified via official website."),
        # Supplier XYZ missing verification
    ]
    
    state.risk_assessments = [
        RiskAnalysis(supplier_name="Foxconn", risk_type="Operational", severity="Low", confidence=0.8, reasoning="Minor labor dispute."),
        RiskAnalysis(supplier_name="TSMC", risk_type="Geopolitical", severity="Medium", confidence=0.7, reasoning="Regional tensions."),
        RiskAnalysis(supplier_name="Supplier XYZ", risk_type="Strategic", severity="High", confidence=0.9, reasoning="Potential fraud.")
    ]
    
    # Run confidence agent
    updated_state = confidence_agent(state)
    
if __name__ == "__main__":
    simulate_apple_trace()
