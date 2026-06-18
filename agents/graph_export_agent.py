import json
import os
import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, GraphNode, GraphEdge, SupplyChainGraph

logger = logging.getLogger(__name__)

class GraphExportAgent:
    """
    Generates visualization-ready supply chain network data.
    """

    def __init__(self, export_dir: str = "database/graphs"):
        self.export_dir = export_dir
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir)

    def export_graph(self, state: AgentState) -> AgentState:
        print("\n--- GRAPH EXPORT AGENT ---")

        company_name = state.target_company or "Unknown"
        
        nodes = []
        edges = []

        # 1. Create root company node
        root_node = GraphNode(
            id=company_name,
            label=company_name,
            node_type="company"
        )
        nodes.append(root_node)

        # Map relationships for quick lookup
        relationship_map = {r.candidate_company: r.relationship_type for r in state.relationship_results}

        # 2. Create supplier nodes and edges
        for supplier in state.suppliers:
            # Create node
            supplier_node = GraphNode(
                id=supplier.name,
                label=supplier.name,
                node_type="supplier"
            )
            nodes.append(supplier_node)

            # Create edge
            rel_type = relationship_map.get(supplier.name, "supplier")
            edge = GraphEdge(
                source=company_name,
                target=supplier.name,
                relationship=rel_type
            )
            edges.append(edge)

        graph = SupplyChainGraph(nodes=nodes, edges=edges)
        state.supply_chain_graph = graph

        # 3. Export to JSON
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        export_file = os.path.join(self.export_dir, f"{safe_name}.json")
        
        try:
            with open(export_file, "w") as f:
                # Use model_dump for Pydantic v2
                json.dump(graph.model_dump(), f, indent=2)
            print(f"\nNodes Created: {len(nodes)}")
            print(f"Edges Created: {len(edges)}")
            print(f"\nGraph Saved: {export_file}")
        except Exception as e:
            logger.error(f"Failed to export graph to {export_file}: {e}")

        state.current_task = "Graph export completed"
        state.history.append({
            "agent": "graph_export_agent",
            "action": "exported_graph",
            "file": export_file,
            "status": "success"
        })

        return state

def graph_export_agent(state: AgentState) -> AgentState:
    agent = GraphExportAgent()
    return agent.export_graph(state)
