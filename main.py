from models.state import AgentState
from workflows.supply_chain_workflow import supply_chain_app


def run_analysis(company_name: str):
    """
    Executes the supply chain analysis using the LangGraph workflow.
    """
    print(f"\n{'='*50}")
    print(f"STARTING ANALYSIS FOR: {company_name}")
    print(f"{'='*50}\n")

    # 1. Initialize the shared state
    initial_state = AgentState(
        target_company=company_name,
        current_task=f"Starting analysis for {company_name}",
    )

    try:
        # 2. Invoke the graph
        # In LangGraph, invoke returns the final state
        final_state_dict = supply_chain_app.invoke(initial_state)

        # If it returns a dict (depending on LangGraph version/config),
        # but since we passed an AgentState (BaseModel), it should return that or something we can convert.
        # Actually, StateGraph(AgentState) will work with the Pydantic model.
        final_state = (
            final_state_dict
            if isinstance(final_state_dict, AgentState)
            else AgentState(**final_state_dict)
        )

        # 3. Final Summary (preserving functionality from old orchestrator)
        print(f"\n{'='*50}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*50}")
        print(f"Target: {final_state.company.name if final_state.company else 'N/A'}")
        print(f"Entities Discovered: {len(final_state.discovered_entities)}")
        print(f"Suppliers Mapped: {len(final_state.suppliers)}")
        print(f"Risks Identified: {len(final_state.risk_assessments)}")
        print(
            f"Verification Confidence: {final_state.confidence_scores.get('verification', 0):.2f}"
        )
        print(f"{'='*50}\n")

        return final_state

    except Exception as e:
        print(f"!!! Error during graph execution: {str(e)}")
        raise


def main():
    """
    Entry point for the Supply Chain Intelligence System.
    """
    company_name = "Apple"
    try:
        final_state = run_analysis(company_name)

        if final_state.errors:
            print(f"Analysis finished with errors: {final_state.errors}")
        else:
            print("Analysis completed successfully.")

    except Exception as e:
        print(f"CRITICAL SYSTEM FAILURE: {e}")


if __name__ == "__main__":
    main()
