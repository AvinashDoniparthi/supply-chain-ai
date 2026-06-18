import os
import logging
from main import run_analysis
from models.state import AgentState

# Configure logging to be minimal
logging.basicConfig(level=logging.ERROR)

COMPANIES = ["Apple", "Samsung", "Nvidia"]

def validate():
    print(f"{'='*100}")
    print(f"{'Company':<15} | {'Suppliers':<10} | {'Geo':<5} | {'Ver':<5} | {'News':<5} | {'Fin':<5} | {'Total':<5}")
    print(f"{'-'*100}")
    
    for company in COMPANIES:
        try:
            # Run analysis
            final_state = run_analysis(company)
            
            # Count risks by type
            geo_count = sum(1 for r in final_state.risk_assessments if r.risk_type == "Geopolitical")
            ver_count = sum(1 for r in final_state.risk_assessments if r.risk_type in ["Operational", "Strategic"] and any(h.get("agent") == "verification_agent" for h in final_state.history))
            # Actually, verification risks in our provider are labeled "Operational" or "Strategic"
            # Let's just check the provider name in history or refine the check.
            # In risk_agent.py, VerificationRiskProvider generates "Operational" or "Strategic"
            # GeopoliticalRiskProvider generates "Geopolitical"
            # NewsRiskProvider generates "News"
            # FinancialRiskProvider generates "Financial"
            
            # Redoing counts based on risk_type exactly as defined in risk_agent.py
            geo_risks = [r for r in final_state.risk_assessments if r.risk_type == "Geopolitical"]
            news_risks = [r for r in final_state.risk_assessments if r.risk_type == "News"]
            fin_risks = [r for r in final_state.risk_assessments if r.risk_type == "Financial"]
            ver_risks = [r for r in final_state.risk_assessments if r.risk_type in ["Operational", "Strategic"]]
            
            supplier_count = len(final_state.suppliers)
            total_risks = len(final_state.risk_assessments)
            
            print(f"{company:<15} | {supplier_count:<10} | {len(geo_risks):<5} | {len(ver_risks):<5} | {len(news_risks):<5} | {len(fin_risks):<5} | {total_risks:<5}")
            
        except Exception as e:
            print(f"{company:<15} | FAILED: {e}")

    print(f"{'='*100}")

if __name__ == "__main__":
    validate()
