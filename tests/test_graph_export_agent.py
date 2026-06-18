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
