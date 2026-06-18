import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, SupplierConfidence, SupplierCriticality, SupplyChainHealth, ExecutiveReport
from agents.executive_report_agent import executive_report_agent

class TestExecutiveReportAgent(unittest.TestCase):
    def setUp(self):
        self.state = AgentState(target_company="Apple Inc.")
        self.state.supply_chain_health = SupplyChainHealth(
            overall_score=84.2,
            status="Good",
            supplier_count=1,
            critical_suppliers=1,
            high_risk_suppliers=0,
            summary="Healthy overall."
        )

    def test_report_generation_succeeds(self):
        """Test basic report generation."""
        self.state.suppliers = [SupplierInfo(name="Foxconn", location="Taiwan")]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(supplier_name="Foxconn", criticality_score=0.85, criticality_level="Critical", reasoning="...")
        ]
        self.state.supplier_confidence_scores = [
            SupplierConfidence(supplier_name="Foxconn", final_confidence=0.92, discovery_confidence=0.9, relationship_confidence=0.9, verification_confidence=0.9, risk_confidence=0.9, reasoning="...")
        ]
        
        updated_state = executive_report_agent(self.state)
        report = updated_state.executive_report
        
        self.assertIsNotNone(report)
        self.assertEqual(report.company_name, "Apple Inc.")
        self.assertEqual(report.overall_health_score, 84.2)
        self.assertIn("Apple Inc.'s supply chain health is Good", report.executive_summary)

    def test_key_suppliers_selection(self):
        """Test that top suppliers are selected correctly by criticality then confidence."""
        self.state.suppliers = [
            SupplierInfo(name="S1", location="L1"),
            SupplierInfo(name="S2", location="L2"),
            SupplierInfo(name="S3", location="L3")
        ]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(supplier_name="S1", criticality_score=0.9, criticality_level="Critical", reasoning="..."),
            SupplierCriticality(supplier_name="S2", criticality_score=0.8, criticality_level="High", reasoning="..."),
            SupplierCriticality(supplier_name="S3", criticality_score=0.9, criticality_level="Critical", reasoning="...")
        ]
        self.state.supplier_confidence_scores = [
            SupplierConfidence(supplier_name="S1", final_confidence=0.8, discovery_confidence=0.8, relationship_confidence=0.8, verification_confidence=0.8, risk_confidence=0.8, reasoning="..."),
            SupplierConfidence(supplier_name="S2", final_confidence=0.95, discovery_confidence=0.9, relationship_confidence=0.9, verification_confidence=0.9, risk_confidence=0.9, reasoning="..."),
            SupplierConfidence(supplier_name="S3", final_confidence=0.9, discovery_confidence=0.9, relationship_confidence=0.9, verification_confidence=0.9, risk_confidence=0.9, reasoning="...")
        ]
        
        updated_state = executive_report_agent(self.state)
        report = updated_state.executive_report
        
        # S3 (0.9 crit, 0.9 conf) > S1 (0.9 crit, 0.8 conf) > S2 (0.8 crit, 0.95 conf)
        self.assertEqual(report.key_suppliers[0], "S3")
        self.assertEqual(report.key_suppliers[1], "S1")
        self.assertEqual(report.key_suppliers[2], "S2")

    def test_major_risks_prioritization(self):
        """Test that risks are prioritized by severity."""
        self.state.risk_assessments = [
            RiskAnalysis(supplier_name="S1", risk_type="Operational", severity="Low", confidence=1.0, reasoning="Minor issue."),
            RiskAnalysis(supplier_name="S2", risk_type="Geopolitical", severity="Critical", confidence=1.0, reasoning="War zone."),
            RiskAnalysis(supplier_name="S3", risk_type="Strategic", severity="High", confidence=1.0, reasoning="Sanctions.")
        ]
        
        updated_state = executive_report_agent(self.state)
        report = updated_state.executive_report
        
        self.assertIn("Geopolitical", report.major_risks[0])
        self.assertIn("Strategic", report.major_risks[1])
        self.assertIn("Operational", report.major_risks[2])

    def test_dynamic_recommendations(self):
        """Test recommendations change based on risk profile."""
        # Case 1: Geopolitical risk + Critical concentration
        self.state.risk_assessments = [
            RiskAnalysis(supplier_name="S1", risk_type="Geopolitical", severity="High", confidence=1.0, reasoning="...")
        ]
        self.state.supplier_criticality_scores = [
            SupplierCriticality(supplier_name="S1", criticality_score=0.9, criticality_level="Critical", reasoning="...")
        ]
        
        report1 = executive_report_agent(self.state).executive_report
        self.assertTrue(any("geopolitical" in r.lower() for r in report1.recommendations))
        self.assertTrue(any("dependence" in r.lower() for r in report1.recommendations))

        # Case 2: Low confidence + Weak health
        self.state.risk_assessments = []
        self.state.supplier_criticality_scores = []
        self.state.supplier_confidence_scores = [
            SupplierConfidence(supplier_name="S1", final_confidence=0.4, discovery_confidence=0.4, relationship_confidence=0.4, verification_confidence=0.4, risk_confidence=0.4, reasoning="...")
        ]
        self.state.supply_chain_health.overall_score = 45.0
        
        report2 = executive_report_agent(self.state).executive_report
        self.assertTrue(any("verification" in r.lower() for r in report2.recommendations))
        self.assertTrue(any("resilience review" in r.lower() for r in report2.recommendations))

if __name__ == '__main__':
    unittest.main()
