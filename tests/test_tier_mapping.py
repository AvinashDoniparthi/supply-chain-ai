import unittest
from unittest.mock import MagicMock, patch
from models.state import AgentState
from agents.supplier_agent import supplier_agent

class TestTierMapping(unittest.TestCase):
    def setUp(self):
        self.state = AgentState(target_company="Apple")

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_tier_mapping(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        
        # Define mock discovery results
        # Tier 1 discovery for Apple
        apple_suppliers = [
            {"name": "TSMC", "location": "Taiwan", "products": ["Chips"], "tier": 1, "criticality": "High", "confidence": 0.9, "source_evidence": []},
            {"name": "Foxconn", "location": "China", "products": ["Assembly"], "tier": 1, "criticality": "High", "confidence": 0.8, "source_evidence": []}
        ]
        
        # Tier 2 discovery for TSMC and Foxconn
        tsmc_suppliers = [
            {"name": "ASML", "location": "Netherlands", "products": ["Lithography"], "tier": 1, "criticality": "High", "confidence": 0.95, "source_evidence": []}
        ]
        foxconn_suppliers = [
            {"name": "Pegatron", "location": "Taiwan", "products": ["Assembly"], "tier": 1, "criticality": "Medium", "confidence": 0.85, "source_evidence": []}
        ]
        
        # Configure mock to return different results based on input
        def side_effect(company_name):
            if "Apple" in company_name: return apple_suppliers
            if "Taiwan Semiconductor" in company_name: return tsmc_suppliers
            if "Hon Hai" in company_name: return foxconn_suppliers
            return []
            
        mock_scraper.find_suppliers.side_effect = side_effect
        
        # Run agent
        updated_state = supplier_agent(self.state)
        
        # Verify
        suppliers = updated_state.suppliers
        self.assertEqual(len(suppliers), 4) # 2 Tier 1 + 2 Tier 2
        
        # Find specific suppliers to check details
        tsmc = next(s for s in suppliers if s.name == "TSMC")
        asml = next(s for s in suppliers if s.name == "ASML")
        
        # Verify Tier 1
        self.assertEqual(tsmc.tier, 1)
        self.assertEqual(tsmc.propagated_confidence, 0.9)
        self.assertEqual(tsmc.parent_company, "Apple")
        self.assertEqual(tsmc.relationship_path, ["Apple", "Taiwan Semiconductor Manufacturing Company"])
        
        # Verify Tier 2
        self.assertEqual(asml.tier, 2)
        self.assertEqual(asml.parent_company, "Taiwan Semiconductor Manufacturing Company")
        self.assertEqual(asml.relationship_path, ["Apple", "Taiwan Semiconductor Manufacturing Company", "ASML"])
        self.assertEqual(asml.propagated_confidence, 0.85)

if __name__ == "__main__":
    unittest.main()
