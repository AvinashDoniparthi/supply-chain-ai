import unittest
import sys
import os
import json
import shutil

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RelationshipResult
from agents.graph_export_agent import GraphExportAgent, graph_export_agent

class TestGraphExportAgent(unittest.TestCase):
    def setUp(self):
        self.test_export_dir = "database/test_graphs"
        self.agent = GraphExportAgent(export_dir=self.test_export_dir)
        self.company_name = "TestCorp"
        self.state = AgentState(target_company=self.company_name)
        self.state.suppliers = [
            SupplierInfo(name="S1", location="L1"),
            SupplierInfo(name="S2", location="L2")
        ]
        self.state.relationship_results = [
            RelationshipResult(target_company=self.company_name, candidate_company="S1", relationship_type="supplier", confidence_score=1.0, reasoning="...", evidence_text="..."),
            RelationshipResult(target_company=self.company_name, candidate_company="S2", relationship_type="partner", confidence_score=1.0, reasoning="...", evidence_text="...")
        ]

    def tearDown(self):
        if os.path.exists(self.test_export_dir):
            shutil.rmtree(self.test_export_dir)

    def test_graph_creation(self):
        """Test basic node and edge creation."""
        updated_state = self.agent.export_graph(self.state)
        graph = updated_state.supply_chain_graph
        
        self.assertIsNotNone(graph)
        # Root + 2 suppliers = 3 nodes
        self.assertEqual(len(graph.nodes), 3)
        # 2 suppliers = 2 edges
        self.assertEqual(len(graph.edges), 2)
        
        node_ids = [n.id for n in graph.nodes]
        self.assertIn(self.company_name, node_ids)
        self.assertIn("S1", node_ids)
        self.assertIn("S2", node_ids)

    def test_file_export(self):
        """Test that the graph is exported to a JSON file correctly."""
        self.agent.export_graph(self.state)
        export_file = os.path.join(self.test_export_dir, f"{self.company_name.lower()}.json")
        
        self.assertTrue(os.path.exists(export_file))
        with open(export_file, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["nodes"]), 3)
            self.assertEqual(len(data["edges"]), 2)
            self.assertEqual(data["edges"][0]["source"], self.company_name)
            self.assertEqual(data["edges"][1]["relationship"], "partner")

    def test_graph_preserves_supplier_tiers_and_parent_edges(self):
        """Tier 3 suppliers should be exported under their immediate parent."""
        self.state.suppliers = [
            SupplierInfo(
                name="FoundryCo",
                canonical_name="FoundryCo",
                location="Taiwan",
                tier=1,
                parent_company=self.company_name,
            ),
            SupplierInfo(
                name="ToolCo",
                canonical_name="ToolCo",
                location="Netherlands",
                tier=2,
                parent_company="FoundryCo",
            ),
            SupplierInfo(
                name="OpticsCo",
                canonical_name="OpticsCo",
                location="Germany",
                tier=3,
                parent_company="ToolCo",
            ),
        ]
        self.state.relationship_results = [
            RelationshipResult(
                target_company=self.company_name,
                candidate_company="FoundryCo",
                relationship_type="supplier",
                confidence_score=1.0,
                reasoning="...",
                evidence_text="...",
            ),
            RelationshipResult(
                target_company="FoundryCo",
                candidate_company="ToolCo",
                relationship_type="upstream_supplier",
                confidence_score=1.0,
                reasoning="...",
                evidence_text="...",
            ),
            RelationshipResult(
                target_company="ToolCo",
                candidate_company="OpticsCo",
                relationship_type="upstream_supplier",
                confidence_score=1.0,
                reasoning="...",
                evidence_text="...",
            ),
        ]

        updated_state = self.agent.export_graph(self.state)
        nodes_by_id = {node.id: node for node in updated_state.supply_chain_graph.nodes}
        edge_pairs = {
            (edge.source, edge.target): edge.relationship
            for edge in updated_state.supply_chain_graph.edges
        }

        self.assertEqual(nodes_by_id["OpticsCo"].tier, 3)
        self.assertEqual(nodes_by_id["OpticsCo"].parent_company, "ToolCo")
        self.assertEqual(edge_pairs[("FoundryCo", "ToolCo")], "upstream_supplier")
        self.assertEqual(edge_pairs[("ToolCo", "OpticsCo")], "upstream_supplier")

    def test_empty_supplier_handling(self):
        """Test handling of empty supplier list."""
        self.state.suppliers = []
        self.state.relationship_results = []
        updated_state = self.agent.export_graph(self.state)
        graph = updated_state.supply_chain_graph
        
        self.assertEqual(len(graph.nodes), 1) # Only root
        self.assertEqual(len(graph.edges), 0)

if __name__ == '__main__':
    unittest.main()
