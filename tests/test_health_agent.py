import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, SupplierConfidence, SupplierCriticality, SupplyChainHealth
from agents.health_agent import health_agent

class TestHealthAgent(unittest.TestCase):
    def setUp(self):
        self.state = AgentState(target_company="Apple Inc.")

    def test_excellent_health(self):
        """Test a supply chain in excellent health."""
        self.state.suppliers = [SupplierInfo(name="PerfectCorp", location="USA")]
        self.state.supplier_confidence_scores = [
            SupplierConfidence(
                supplier_name="PerfectCorp",
                discovery_confidence=1.0,
                relationship_confidence=1.0,
                verification_confidence=1.0,
                risk_confidence=0.9,
                final_confidence=0.95,
                reasoning="..."
            )
        ]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(
                supplier_name="PerfectCorp",
                criticality_score=0.9,
                criticality_level="Critical",
                reasoning="..."
            )
        ]
        # No risks for PerfectCorp
        
        updated_state = health_agent(self.state)
        health = updated_state.supply_chain_health
        
        # Calculation:
        # Confidence: 0.95 * 0.3 = 0.285
        # Criticality: 0.9 * 0.3 = 0.27
        # Risk: 1.0 (No Risk) * 0.4 = 0.4
        # Total: (0.285 + 0.27 + 0.4) * 100 = 95.5
        
        self.assertEqual(health.overall_score, 95.5)
        self.assertEqual(health.status, "Excellent")
        self.assertEqual(health.critical_suppliers, 1)
        self.assertEqual(health.high_risk_suppliers, 0)

    def test_critical_health(self):
        """Test a supply chain in critical condition."""
        self.state.suppliers = [SupplierInfo(name="RiskyBiz", location="Unknown")]
        self.state.supplier_confidence_scores = [
            SupplierConfidence(
                supplier_name="RiskyBiz",
                discovery_confidence=0.3,
                relationship_confidence=0.3,
                verification_confidence=0.3,
                risk_confidence=0.2,
                final_confidence=0.25,
                reasoning="..."
            )
        ]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(
                supplier_name="RiskyBiz",
                criticality_score=0.3,
                criticality_level="Low",
                reasoning="..."
            )
        ]
        self.state.risk_assessments = [
            RiskAnalysis(
                supplier_name="RiskyBiz",
                risk_type="Operational",
                severity="Critical",
                confidence=1.0,
                reasoning="Active shutdown."
            )
        ]
        
        updated_state = health_agent(self.state)
        health = updated_state.supply_chain_health
        
        # Calculation:
        # Confidence: 0.25 * 0.3 = 0.075
        # Criticality: 0.3 * 0.3 = 0.09
        # Risk: 0.1 (Critical) * 0.4 = 0.04
        # Total: (0.075 + 0.09 + 0.04) * 100 = 20.5
        
        self.assertEqual(health.overall_score, 20.5)
        self.assertEqual(health.status, "Critical")
        self.assertEqual(health.high_risk_suppliers, 1)

    def test_moderate_health_mixed_suppliers(self):
        """Test a mixed supply chain resulting in moderate health."""
        self.state.suppliers = [
            SupplierInfo(name="GoodOne", location="USA"),
            SupplierInfo(name="BadOne", location="Unknown")
        ]
        self.state.supplier_confidence_scores = [
            SupplierConfidence(supplier_name="GoodOne", final_confidence=0.9, discovery_confidence=0.9, relationship_confidence=0.9, verification_confidence=0.9, risk_confidence=0.9, reasoning="..."),
            SupplierConfidence(supplier_name="BadOne", final_confidence=0.4, discovery_confidence=0.4, relationship_confidence=0.4, verification_confidence=0.4, risk_confidence=0.4, reasoning="...")
        ]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(supplier_name="GoodOne", criticality_score=0.8, criticality_level="High", reasoning="..."),
            SupplierCriticality(supplier_name="BadOne", criticality_score=0.2, criticality_level="Low", reasoning="...")
        ]
        self.state.risk_assessments = [
            RiskAnalysis(supplier_name="BadOne", risk_type="Strategic", severity="High", confidence=1.0, reasoning="Potential fraud.")
        ]
        
        updated_state = health_agent(self.state)
        health = updated_state.supply_chain_health
        
        # GoodOne: (0.9*0.3 + 0.8*0.3 + 1.0*0.4) = 0.27 + 0.24 + 0.4 = 0.91
        # BadOne: (0.4*0.3 + 0.2*0.3 + 0.3*0.4) = 0.12 + 0.06 + 0.12 = 0.3
        # Average: (0.91 + 0.3) / 2 = 0.605 * 100 = 60.5
        
        self.assertEqual(health.overall_score, 60.5)
        self.assertEqual(health.status, "Moderate")

if __name__ == '__main__':
    unittest.main()
