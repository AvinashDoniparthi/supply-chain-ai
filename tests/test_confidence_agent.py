import unittest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, SupplierConfidence
from models.relationship import RelationshipResult
from models.verification import VerificationResult
from agents.confidence_agent import confidence_agent

class TestConfidenceAgent(unittest.TestCase):
    def setUp(self):
        self.state = AgentState(target_company="Apple Inc.")

    def test_verified_supplier_no_risks(self):
        """Test a strongly verified supplier with no risks."""
        self.state.suppliers = [SupplierInfo(name="Foxconn", location="Taiwan", discovery_confidence=0.92)]
        self.state.relationship_results = [
            RelationshipResult(
                target_company="Apple Inc.",
                candidate_company="Foxconn",
                relationship_type="supplier",
                confidence_score=0.98,
                reasoning="Long-term assembly partner.",
                evidence_text="Foxconn assembles iPhones."
            )
        ]
        self.state.verification_results = [
            VerificationResult(
                supplier_name="Foxconn",
                relationship_type="supplier",
                verified=True,
                confidence_score=0.85,
                reasoning="Confirmed via annual reports."
            )
        ]
        # No risk_assessments for Foxconn
        
        updated_state = confidence_agent(self.state)
        conf = updated_state.supplier_confidence_scores[0]
        
        # Plain AgentState fixtures use open-world coverage, so discovered
        # Tier-1 suppliers are not capped by benchmark expected sets.

        self.assertEqual(conf.supplier_name, "Foxconn")
        self.assertEqual(conf.final_confidence, 0.89)
        self.assertIn("Successfully verified", conf.reasoning)
        self.assertIn("No supplier-specific risk signals", conf.reasoning)

    def test_failed_verification(self):
        """Test a supplier that failed verification."""
        self.state.suppliers = [SupplierInfo(name="Sketchy Corp", location="Unknown", discovery_confidence=0.5)]
        self.state.relationship_results = [
            RelationshipResult(
                target_company="Apple Inc.",
                candidate_company="Sketchy Corp",
                relationship_type="unknown",
                confidence_score=0.5,
                reasoning="Vague mentions in social media.",
                evidence_text="..."
            )
        ]
        self.state.verification_results = [
            VerificationResult(
                supplier_name="Sketchy Corp",
                relationship_type="unknown",
                verified=False,
                confidence_score=0.4,
                reasoning="Company registry not found."
            )
        ]
        
        updated_state = confidence_agent(self.state)
        conf = updated_state.supplier_confidence_scores[0]
        
        # Open-world coverage does not apply benchmark expected supplier caps.

        self.assertEqual(conf.final_confidence, 0.43)
        self.assertIn("Verification failed", conf.reasoning)

    def test_high_risk_supplier(self):
        """Test a verified supplier but with high severity risk."""
        self.state.suppliers = [SupplierInfo(name="RiskCo", location="Conflict Zone", discovery_confidence=0.8)]
        self.state.relationship_results = [
            RelationshipResult(
                target_company="Apple Inc.",
                candidate_company="RiskCo",
                relationship_type="supplier",
                confidence_score=0.9,
                reasoning="Known supplier.",
                evidence_text="..."
            )
        ]
        self.state.verification_results = [
            VerificationResult(
                supplier_name="RiskCo",
                relationship_type="supplier",
                verified=True,
                confidence_score=0.9,
                reasoning="Verified."
            )
        ]
        self.state.risk_assessments = [
            RiskAnalysis(
                supplier_name="RiskCo",
                risk_type="Geopolitical",
                severity="High",
                confidence=1.0,
                reasoning="Active conflict."
            )
        ]
        
        updated_state = confidence_agent(self.state)
        conf = updated_state.supplier_confidence_scores[0]
        
        # Strong individual evidence is not capped by benchmark expected sets in
        # open-world mode.

        self.assertEqual(conf.final_confidence, 0.81)
        self.assertIn("Exposure to high severity risks", conf.reasoning)

    def test_missing_verification_data(self):
        """Test supplier with missing verification data."""
        self.state.suppliers = [SupplierInfo(name="NewGuy", location="Unknown")]
        
        updated_state = confidence_agent(self.state)
        conf = updated_state.supplier_confidence_scores[0]
        
        # Missing verification lowers confidence, but benchmark expected sets do
        # not cap plain open-world fixtures.

        self.assertEqual(conf.final_confidence, 0.47)
        self.assertIn("No verification data available", conf.reasoning)

if __name__ == '__main__':
    unittest.main()
