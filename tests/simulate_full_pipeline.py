import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, CompanyInfo
from models.relationship import RelationshipResult
from models.verification import VerificationResult
from agents.confidence_agent import confidence_agent
from agents.criticality_agent import criticality_agent
from agents.health_agent import health_agent
from agents.executive_report_agent import executive_report_agent
from agents.history_agent import history_agent
from agents.graph_export_agent import graph_export_agent

def simulate_full_trace():
    state = AgentState(target_company="Apple Inc.")
    
    # Mocking data for Apple suppliers
    state.suppliers = [
        SupplierInfo(name="Foxconn", location="Taiwan", discovery_confidence=0.95, products=["Assembly", "Manufacturing"]),
        SupplierInfo(name="TSMC", location="Taiwan", discovery_confidence=0.98, products=["Semiconductors", "Chips"]),
        SupplierInfo(name="Supplier XYZ", location="Unknown", discovery_confidence=0.45, products=["Logistics"])
    ]
    
    state.relationship_results = [
        RelationshipResult(target_company="Apple Inc.", candidate_company="Foxconn", relationship_type="partner", confidence_score=0.99, reasoning="Main assembler.", evidence_text="..."),
        RelationshipResult(target_company="Apple Inc.", candidate_company="TSMC", relationship_type="supplier", confidence_score=0.98, reasoning="Chip manufacturer.", evidence_text="..."),
        RelationshipResult(target_company="Apple Inc.", candidate_company="Supplier XYZ", relationship_type="unknown", confidence_score=0.40, reasoning="Vague connection.", evidence_text="...")
    ]
    
    state.verification_results = [
        VerificationResult(supplier_name="Foxconn", relationship_type="partner", verified=True, confidence_score=0.90, reasoning="Verified via SEC filings."),
        VerificationResult(supplier_name="TSMC", relationship_type="supplier", verified=True, confidence_score=0.95, reasoning="Verified via official website."),
        # Supplier XYZ missing verification
    ]
    
    state.risk_assessments = [
        RiskAnalysis(supplier_name="Foxconn", risk_type="Operational", severity="Low", confidence=0.8, reasoning="Minor labor dispute."),
        RiskAnalysis(supplier_name="TSMC", risk_type="Geopolitical", severity="Critical", confidence=0.7, reasoning="Taiwan-China tensions."),
        RiskAnalysis(supplier_name="Supplier XYZ", risk_type="Strategic", severity="High", confidence=0.9, reasoning="Potential fraud.")
    ]
    
    # Run pipeline
    state = confidence_agent(state)
    state = criticality_agent(state)
    state = health_agent(state)
    state = executive_report_agent(state)
    state = history_agent(state)
    state = graph_export_agent(state)
    
if __name__ == "__main__":
    simulate_full_trace()
