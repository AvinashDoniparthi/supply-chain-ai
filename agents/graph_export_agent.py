import json
import os
import logging
from models.state import AgentState, GraphNode, GraphEdge, SupplyChainGraph
from utils.identity_resolution import resolver
from utils.output import agent_event, debug_log
from utils.runtime_controls import timed_stage

logger = logging.getLogger(__name__)
DEFAULT_GRAPH_EXPORT_DIR = "database/graphs"

class GraphExportAgent:
    """
    Generates visualization-ready supply chain network data.
    """

    def __init__(self, export_dir: str = DEFAULT_GRAPH_EXPORT_DIR):
        self.export_dir = export_dir
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir)

    def export_graph(self, state: AgentState) -> AgentState:
        agent_event("Graph export agent started")

        company_name = state.target_company or "Unknown"
        
        nodes = []
        edges = []

        # 1. Create root company node
        root_node = GraphNode(
            id=company_name,
            label=company_name,
            node_type="company",
            tier=0,
        )
        nodes.append(root_node)

        # Map relationships for quick lookup
        relationship_map = {}
        for result in state.relationship_results:
            relationship_map[result.candidate_company] = result.relationship_type
            relationship_map[resolver.resolve(result.candidate_company)] = (
                result.relationship_type
            )

        node_id_by_company = {
            company_name: company_name,
            resolver.resolve(company_name): company_name,
        }
        for supplier in state.suppliers:
            node_id_by_company[supplier.name] = supplier.name
            node_id_by_company[resolver.resolve(supplier.name)] = supplier.name
            if supplier.canonical_name:
                node_id_by_company[supplier.canonical_name] = supplier.name
                node_id_by_company[resolver.resolve(supplier.canonical_name)] = supplier.name

        # 2. Create supplier nodes and edges
        for supplier in state.suppliers:
            # Create node
            supplier_node = GraphNode(
                id=supplier.name,
                label=supplier.name,
                node_type="supplier",
                tier=supplier.tier,
                parent_company=supplier.parent_company,
            )
            nodes.append(supplier_node)

            parent_name = supplier.parent_company if supplier.tier > 1 else company_name
            source_id = (
                node_id_by_company.get(parent_name or "")
                or node_id_by_company.get(resolver.resolve(parent_name or ""))
                or company_name
            )
            rel_type = (
                relationship_map.get(supplier.name)
                or relationship_map.get(supplier.canonical_name or "")
                or relationship_map.get(
                    resolver.resolve(supplier.canonical_name or supplier.name)
                )
                or ("upstream_supplier" if supplier.tier > 1 else "supplier")
            )
            edge = GraphEdge(
                source=source_id,
                target=supplier.name,
                relationship=rel_type
            )
            edges.append(edge)

        graph = SupplyChainGraph(nodes=nodes, edges=edges)
        state.supply_chain_graph = graph

        # 3. Export to JSON
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        export_file = os.path.join(self.export_dir, f"{safe_name}.json")
        
        write_succeeded = False
        try:
            with open(export_file, "w") as f:
                # Use model_dump for Pydantic v2
                json.dump(graph.model_dump(exclude_none=True), f, indent=2)
            debug_log(logger, "Nodes Created: %s", len(nodes))
            debug_log(logger, "Edges Created: %s", len(edges))
            debug_log(logger, "Graph Saved: %s", export_file)
            write_succeeded = True
        except Exception as e:
            error = f"Graph export failed for {export_file}: {e}"
            logger.error(error)
            state.errors.append(error)
            state.stage_statuses["graph_export"] = "failed"

        state.current_task = "Graph export completed"
        state.history.append(
            {
                "agent": "graph_export_agent",
                "action": "exported_graph" if write_succeeded else "graph_export_failed",
                **({"file": export_file} if write_succeeded else {}),
                "status": "success" if write_succeeded else "failed",
            }
        )

        agent_event("Graph export agent completed")

        return state

def graph_export_agent(state: AgentState) -> AgentState:
    agent = GraphExportAgent(export_dir=DEFAULT_GRAPH_EXPORT_DIR)
    with timed_stage(state, "graph_export"):
        return agent.export_graph(state)
