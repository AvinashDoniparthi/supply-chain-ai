from langgraph.graph import StateGraph, START, END
from models.state import AgentState
from agents.company_agent import company_agent
from agents.supplier_agent import supplier_agent
from agents.relationship_agent import relationship_agent
from agents.verification_agent import verification_agent
from agents.risk_agent import risk_agent


def create_supply_chain_workflow():
    """
    Creates and compiles the LangGraph workflow for supply chain analysis.
    The workflow follows a logical path:
    Company -> Supplier -> Relationship -> Verification -> Risk
    """

    # 1. Initialize the Graph with our AgentState schema
    workflow = StateGraph(AgentState)

    # 2. Add nodes for each agent
    # The node names are descriptive, mapping to the agent functions
    workflow.add_node("company_agent", company_agent)
    workflow.add_node("supplier_agent", supplier_agent)
    workflow.add_node("relationship_agent", relationship_agent)
    workflow.add_node("verification_agent", verification_agent)
    workflow.add_node("risk_agent", risk_agent)

    # 3. Define the edges (the flow of execution)
    workflow.add_edge(START, "company_agent")
    workflow.add_edge("company_agent", "supplier_agent")
    workflow.add_edge("supplier_agent", "relationship_agent")
    workflow.add_edge("relationship_agent", "verification_agent")
    workflow.add_edge("verification_agent", "risk_agent")
    workflow.add_edge("risk_agent", END)

    # 4. Compile the graph
    app = workflow.compile()

    return app


# Initialize the graph
supply_chain_app = create_supply_chain_workflow()
