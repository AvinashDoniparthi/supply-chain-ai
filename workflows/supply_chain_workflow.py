import logging

from langgraph.graph import StateGraph, START, END
from models.state import AgentState
from agents.company_agent import company_agent
from agents.supplier_agent import supplier_agent
from agents.relationship_agent import relationship_agent
from agents.deduplication_agent import deduplication_agent
from agents.verification_agent import verification_agent
from agents.risk_agent import risk_agent
from agents.confidence_agent import confidence_agent
from agents.criticality_agent import criticality_agent
from agents.health_agent import health_agent
from agents.executive_report_agent import executive_report_agent
from agents.history_agent import history_agent
from agents.graph_export_agent import graph_export_agent

logger = logging.getLogger(__name__)


def tier_router(state: AgentState) -> str:
    """Route the workflow based on current supplier discovery progress."""
    queue_size = len(state.mapping_queue)
    decision = "continue_discovery" if queue_size > 0 else "discovery_complete"

    log_msg = (
        "[TIER ROUTER]\n"
        f"Queue Size: {queue_size}\n"
        f"Current Depth: {state.current_depth}\n"
        f"Decision: {decision}"
    )
    print(log_msg)
    logger.info(log_msg)

    return decision


def tier_router_node(state: AgentState) -> AgentState:
    """No-op node that enables conditional routing after supplier discovery."""
    state.current_task = "Tier router evaluation"
    return state


def create_supply_chain_workflow():
    """
    Creates and compiles the LangGraph workflow for supply chain analysis.
    The workflow follows a logical path:
    Company -> Supplier -> Relationship -> Deduplication -> Verification -> Risk -> Confidence -> Criticality -> Health -> ExecutiveReport -> History -> GraphExport
    """

    # 1. Initialize the Graph with our AgentState schema
    workflow = StateGraph(AgentState)

    # 2. Add nodes for each agent
    # The node names are descriptive, mapping to the agent functions
    workflow.add_node("company_agent", company_agent)
    workflow.add_node("supplier_agent", supplier_agent)
    workflow.add_node("relationship_agent", relationship_agent)
    workflow.add_node("deduplication_agent", deduplication_agent)
    workflow.add_node("verification_agent", verification_agent)
    workflow.add_node("risk_agent", risk_agent)
    workflow.add_node("confidence_agent", confidence_agent)
    workflow.add_node("criticality_agent", criticality_agent)
    workflow.add_node("health_agent", health_agent)
    workflow.add_node("executive_report_agent", executive_report_agent)
    workflow.add_node("history_agent", history_agent)
    workflow.add_node("graph_export_agent", graph_export_agent)
    workflow.add_node("tier_router", tier_router_node)

    # 3. Define the edges (the flow of execution)
    workflow.add_edge(START, "company_agent")
    workflow.add_edge("company_agent", "supplier_agent")
    workflow.add_edge("supplier_agent", "tier_router")
    workflow.add_conditional_edges(
        "tier_router",
        tier_router,
        path_map={
            "continue_discovery": "supplier_agent",
            "discovery_complete": "relationship_agent",
        },
    )
    workflow.add_edge("relationship_agent", "deduplication_agent")
    workflow.add_edge("deduplication_agent", "verification_agent")
    workflow.add_edge("verification_agent", "risk_agent")
    workflow.add_edge("risk_agent", "confidence_agent")
    workflow.add_edge("confidence_agent", "criticality_agent")
    workflow.add_edge("criticality_agent", "health_agent")
    workflow.add_edge("health_agent", "executive_report_agent")
    workflow.add_edge("executive_report_agent", "history_agent")
    workflow.add_edge("history_agent", "graph_export_agent")
    workflow.add_edge("graph_export_agent", END)

    # 4. Compile the graph
    app = workflow.compile()

    return app


# Initialize the graph
supply_chain_app = create_supply_chain_workflow()
