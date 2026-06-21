import unittest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, SupplierConfidence, SupplierCriticality, SupplyChainHealth, ExecutiveReport
from agents.executive_report_agent import executive_report_agent
from providers.llm_provider import LLMConfig
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

class TestExecutiveReportAgent(unittest.TestCase):
    def setUp(self):
        self.resolve_patcher = patch(
            "chains.executive_summary_chain.resolve_provider",
            return_value=LLMConfig(
                provider="google",
                model="gemini-2.5-flash",
                key_source="GOOGLE_API_KEY",
                api_key="google-test-key",
            ),
        )
        self.get_llm_patcher = patch(
            "chains.executive_summary_chain.get_llm",
            return_value=RunnableLambda(
                lambda _: AIMessage(
                    content="Apple's supply chain is healthy with strong ties to Foxconn."
                )
            ),
        )
        self.resolve_patcher.start()
        self.get_llm_patcher.start()
        self.addCleanup(self.resolve_patcher.stop)
        self.addCleanup(self.get_llm_patcher.stop)

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
        self.assertIn("DISCOVERY QUALITY", report.executive_summary)
        self.assertIn("SUPPLY CHAIN HEALTH", report.executive_summary)
        self.assertIn("TIER 1 SUPPLIERS", report.executive_summary)
        self.assertIn("TOP RISKS", report.executive_summary)
        self.assertIn("DATA QUALITY WARNINGS", report.executive_summary)
        self.assertIn("CRITICAL SUPPLIERS", report.executive_summary)
        self.assertIn("EXECUTIVE SUMMARY", report.executive_summary)
        self.assertIn(
            "Coverage: High - 1 discovered Tier-1 suppliers identified.",
            report.executive_summary,
        )

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
            RiskAnalysis(supplier_name="S1", risk_type="News", severity="Low", confidence=1.0, reasoning="Minor strike warning."),
            RiskAnalysis(supplier_name="S2", risk_type="Geopolitical", severity="Critical", confidence=1.0, reasoning="War zone."),
            RiskAnalysis(supplier_name="S3", risk_type="Strategic", severity="High", confidence=1.0, reasoning="Sanctions.")
        ]
        
        updated_state = executive_report_agent(self.state)
        report = updated_state.executive_report
        
        self.assertIn("Geopolitical", report.major_risks[0])
        self.assertIn("Strategic", report.major_risks[1])
        self.assertIn("News", report.major_risks[2])

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
        self.assertFalse(any("resilience review" in r.lower() for r in report2.recommendations))

    def test_summary_avoids_disruption_exposure_when_no_supplier_risks(self):
        self.state.target_company = "Dell"
        self.state.suppliers = [
            SupplierInfo(name="Broadcom", canonical_name="Broadcom Inc.", location="United States", products=["Chips"]),
            SupplierInfo(name="Compal Electronics", location="Taiwan", products=["Contract manufacturing"]),
            SupplierInfo(name="Marvell Technology", canonical_name="Marvell Technology, Inc.", location="United States", products=["Storage controllers"]),
            SupplierInfo(name="Quanta Computer", location="Taiwan", products=["ODM manufacturing"]),
        ]
        self.state.risk_assessments = []

        report = executive_report_agent(self.state).executive_report

        self.assertIn("No supplier-specific risks detected", report.executive_summary)
        self.assertIn(
            "The main concern is limited verification depth or supplier concentration.",
            report.executive_summary,
        )
        self.assertNotIn("supplier-specific disruption exposure", report.executive_summary)
        self.assertNotIn("geographic disruption exposure", report.executive_summary)

if __name__ == '__main__':
    unittest.main()
