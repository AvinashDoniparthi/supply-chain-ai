from agents.orchestrator import run_supply_chain_analysis

def main():
    """
    Entry point for the Supply Chain Intelligence System.
    """
    company_name = "TechNova Solutions"
    try:
        final_state = run_supply_chain_analysis(company_name)
        
        if final_state.errors:
            print(f"Analysis finished with errors: {final_state.errors}")
        else:
            print("Analysis completed successfully.")
            
    except Exception as e:
        print(f"CRITICAL SYSTEM FAILURE: {e}")

if __name__ == "__main__":
    main()
