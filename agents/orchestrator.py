from models.state import AgentState
from agents.company_agent import company_agent
from agents.supplier_agent import supplier_agent
from agents.relationship_agent import relationship_agent
from agents.deduplication_agent import deduplication_agent
from agents.risk_agent import risk_agent
from agents.verification_agent import verification_agent
from agents.confidence_agent import confidence_agent
from agents.criticality_agent import criticality_agent
from agents.health_agent import health_agent
from agents.executive_report_agent import executive_report_agent
from agents.history_agent import history_agent
from agents.graph_export_agent import graph_export_agent
from utils.output import OutputMode, emit, render_final_report


def run_supply_chain_analysis(company_name: str) -> AgentState:
    """
    The main orchestrator that manages the flow of intelligence between agents.
    It executes the agents in a logical sequence to build a complete picture
    of the target company's supply chain risks.
    """
    emit(f"Starting supply-chain analysis for {company_name}", OutputMode.DEBUG)

    # 1. Initialize the shared state
    state = AgentState(target_company=company_name)
    state.current_task = f"Starting analysis for {company_name}"

    try:
        # 2. Execute Company Agent (Identify Target)
        state = company_agent(state)
        if not state.company:
            raise ValueError("Company Agent failed to identify target company.")

        # 3. Execute Supplier Agent (Map Supply Chain)
        state = supplier_agent(state)
        if not state.suppliers:
            emit("Warning: No suppliers found for this company.", OutputMode.NORMAL)

        # 4. Execute Relationship Agent (Classify Relationships)
        state = relationship_agent(state)

        # 5. Execute Deduplication Agent (Merge Entities)
        state = deduplication_agent(state)

        # 6. Execute Verification Agent (Fact-Check)
        # We verify suppliers before analyzing risk to ensure integrity
        state = verification_agent(state)

        # 7. Execute Risk Agent (Assess Vulnerabilities)
        # Risk analysis now has access to 'verified' flags in state.verification_results
        state = risk_agent(state)

        # 8. Score confidence, criticality, health, and report quality
        state = confidence_agent(state)
        state = criticality_agent(state)
        state = health_agent(state)
        state = executive_report_agent(state)
        state = history_agent(state)
        state = graph_export_agent(state)

    except Exception as e:
        error_msg = f"Error during agent execution: {str(e)}"
        emit(f"!!! {error_msg}")
        state.errors.append(error_msg)
        state.current_task = "Workflow failed"
        return state

    render_final_report(state)

    state.current_task = "Workflow complete"
    return state


if __name__ == "__main__":
    # Test run if executed directly
    final_state = run_supply_chain_analysis("TechNova Solutions")
