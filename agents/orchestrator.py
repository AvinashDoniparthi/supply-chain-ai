from models.state import AgentState
from agents.company_agent import company_agent
from agents.supplier_agent import supplier_agent
from agents.risk_agent import risk_agent
from agents.verification_agent import verification_agent


def run_supply_chain_analysis(company_name: str) -> AgentState:
    """
    The main orchestrator that manages the flow of intelligence between agents.
    It executes the agents in a logical sequence to build a complete picture
    of the target company's supply chain risks.
    """
    print(f"\n{'='*50}")
    print(f"STARTING ANALYSIS FOR: {company_name}")
    print(f"{'='*50}\n")

    # 1. Initialize the shared state
    state = AgentState(
        target_company=company_name,
        current_task=f"Starting analysis for {company_name}"
    )

    try:
        # 2. Execute Company Agent (Identify Target)
        state = company_agent(state)
        if not state.company:
            raise ValueError("Company Agent failed to identify target company.")

        # 3. Execute Supplier Agent (Map Supply Chain)
        state = supplier_agent(state)
        if not state.suppliers:
            print("Warning: No suppliers found for this company.")

        # 4. Execute Verification Agent (Fact-Check)
        # We verify suppliers before analyzing risk to ensure integrity
        state = verification_agent(state)

        # 5. Execute Risk Agent (Assess Vulnerabilities)
        # Risk analysis now has access to 'verified' flags in state.verification_results
        state = risk_agent(state)

    except Exception as e:
        error_msg = f"Error during agent execution: {str(e)}"
        print(f"!!! {error_msg}")
        state.errors.append(error_msg)
        state.current_task = "Workflow failed"
        return state

    # 6. Final Summary
    print(f"\n{'='*50}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*50}")
    print(f"Target: {state.company.name if state.company else 'N/A'}")
    print(f"Suppliers Mapped: {len(state.suppliers)}")
    print(f"Risks Identified: {len(state.risk_assessments)}")
    print(
        f"Verification Confidence: {state.confidence_scores.get('verification', 0):.2f}"
    )
    print(f"{'='*50}\n")

    state.current_task = "Workflow complete"
    return state


if __name__ == "__main__":
    # Test run if executed directly
    final_state = run_supply_chain_analysis("Apple Inc.")
