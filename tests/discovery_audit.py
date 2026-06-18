import os
import logging
from main import run_analysis
from models.state import AgentState

# Configure logging to be minimal
logging.basicConfig(level=logging.ERROR)

COMPANIES = ["Tesla", "Microsoft", "Nvidia"]

def audit():
    for company in COMPANIES:
        print(f"\n{'#'*60}")
        print(f"AUDIT FOR: {company}")
        print(f"{'#'*60}\n")
        
        try:
            final_state = run_analysis(company)
            
            # Summary Table Generation
            print(f"\n{'='*100}")
            print(f"SUMMARY TABLE: {company}")
            print(f"{'='*100}")
            print(f"{'Entity':<40} | {'Relationship':<15} | {'Confidence':<10} | {'Decision':<8}")
            print(f"{'-'*100}")
            
            # Map relationship results by candidate company
            rel_map = {r.candidate_company: r for r in final_state.relationship_results}
            
            # Suppliers KEEP list
            keep_names = [s.name for s in final_state.suppliers]
            
            # We want to show everything that went through relationship classification
            for r in final_state.relationship_results:
                decision = "KEEP" if r.candidate_company in keep_names else "DROP"
                print(f"{r.candidate_company:<40} | {r.relationship_type:<15} | {r.confidence_score:<10.2f} | {decision:<8}")
            
            # If relationship_results is empty, something else might have failed
            if not final_state.relationship_results:
                print("No entities reached relationship classification.")
                
            print(f"{'='*100}\n")
            
            print(f"Suppliers passed to verification: {[v.supplier_name for v in final_state.verification_results]}")
            
        except Exception as e:
            print(f"AUDIT FAILED FOR {company}: {e}")

if __name__ == "__main__":
    audit()
