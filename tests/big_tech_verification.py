import os
import json
import logging
import time
from main import run_analysis
from models.state import AgentState

# Configure logging to be less verbose for the test script
logging.basicConfig(level=logging.ERROR)

COMPANIES = [
    "Apple",
    "Tesla",
    "Nvidia",
    "Microsoft",
    "Amazon",
    "Google",
    "Samsung",
    "Intel"
]

def verify_company(company_name: str):
    print(f"\nVerifying {company_name}...")
    try:
        final_state = run_analysis(company_name)
        
        # 1. Suppliers discovered
        suppliers_discovered = len(final_state.suppliers) > 0
        
        # 2. Deduplication works (check history)
        dedup_success = any(h.get("agent") == "deduplication_agent" and h.get("status") == "success" for h in final_state.history)
        
        # 3. Verification works
        verification_success = any(h.get("agent") == "verification_agent" and h.get("status") == "success" for h in final_state.history)
        
        # 4. Risks generated
        risks_generated = len(final_state.risk_assessments) > 0
        
        # 5. Executive report generated
        report_generated = final_state.executive_report is not None
        
        # 6. History file created
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        history_file = os.path.join("database/history", f"{safe_name}.json")
        history_exists = os.path.exists(history_file)
        
        verified_count = sum(1 for v in final_state.verification_results if v.verified)
        
        results = {
            "Company": company_name,
            "Entities Discovered": len(final_state.discovered_entities),
            "Suppliers Mapped": len(final_state.suppliers),
            "Verified Suppliers": verified_count,
            "Risks": len(final_state.risk_assessments),
            "Health Score": final_state.supply_chain_health.overall_score if final_state.supply_chain_health else 0,
            "Status": final_state.supply_chain_health.status if final_state.supply_chain_health else "N/A",
            "Verification": {
                "Suppliers discovered": "✅" if suppliers_discovered else "❌",
                "Deduplication works": "✅" if dedup_success else "❌",
                "Verification works": "✅" if verification_success else "❌",
                "Risks generated": "✅" if risks_generated else "❌",
                "Executive report generated": "✅" if report_generated else "❌",
                "History file created": "✅" if history_exists else "❌"
            }
        }
        
        return results
    except Exception as e:
        print(f"Error verifying {company_name}: {e}")
        return {
            "Company": company_name,
            "Status": "FAILED",
            "Error": str(e)
        }

def main():
    all_results = []
    
    print(f"{'='*100}")
    print(f"{'Company':<15} | {'Entities':<10} | {'Suppliers':<10} | {'Verified':<10} | {'Risks':<8} | {'Health':<8} | {'Status':<10}")
    print(f"{'-'*100}")
    
    for i, company in enumerate(COMPANIES):
        if i > 0:
            print(f"Waiting 20 seconds before next company...")
            time.sleep(20)
        res = verify_company(company)
        all_results.append(res)
        
        if res.get("Status") == "FAILED":
            print(f"{res['Company']:<15} | {'FAILED':<10} | {res['Error'][:50]:<10}")
        else:
            print(f"{res['Company']:<15} | {res['Entities Discovered']:<10} | {res['Suppliers Mapped']:<10} | {res['Verified Suppliers']:<10} | {res['Risks']:<8} | {res['Health Score']:<8} | {res['Status']:<10}")

    print(f"{'='*100}")
    
    # Detailed verification check
    print("\nDetailed Verification:")
    for res in all_results:
        if res.get("Status") == "FAILED":
            continue
        print(f"\n{res['Company']}:")
        for k, v in res['Verification'].items():
            print(f"  {v} {k}")

if __name__ == "__main__":
    main()
