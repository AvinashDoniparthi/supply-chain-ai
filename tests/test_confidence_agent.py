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
        
        # Calculation:
        # Discovery: 0.92 * 0.20 = 0.184
        # Relationship: 0.98 * 0.30 = 0.294
        # Verification: 0.85 * 0.35 = 0.2975
        # Risk: 0.9 * 0.15 = 0.135
        # Total: 0.9105 -> 0.91
        
        self.assertEqual(conf.supplier_name, "Foxconn")
        self.assertEqual(conf.final_confidence, 0.91)
        self.assertIn("Successfully verified", conf.reasoning)
        self.assertIn("No operational or strategic risks", conf.reasoning)

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
        
        # Calculation:
        # Discovery: 0.5 * 0.20 = 0.10
        # Relationship: 0.5 * 0.30 = 0.15
        # Verification: (0.4 * 0.5) * 0.35 = 0.07 (verification failed: conf * 0.5)
        # Risk: 0.9 * 0.15 = 0.135
        # Total: 0.455 -> 0.46
        
        self.assertEqual(conf.final_confidence, 0.46)
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
        
        # Calculation:
        # Discovery: 0.8 * 0.20 = 0.16
        # Relationship: 0.9 * 0.30 = 0.27
        # Verification: 0.9 * 0.35 = 0.315
        # Risk: 0.4 * 0.15 = 0.06 (High risk = 0.4)
        # Total: 0.805 -> 0.81
        
        self.assertEqual(conf.final_confidence, 0.81)
        self.assertIn("Exposure to high severity risks", conf.reasoning)

    def test_missing_verification_data(self):
        """Test supplier with missing verification data."""
        self.state.suppliers = [SupplierInfo(name="NewGuy", location="Unknown")]
        
        updated_state = confidence_agent(self.state)
        conf = updated_state.supplier_confidence_scores[0]
        
        # Discovery: 0.5 (default) * 0.20 = 0.10
        # Relationship: 0.5 (default) * 0.30 = 0.15
        # Verification: 0.3 (missing) * 0.35 = 0.105
        # Risk: 0.9 * 0.15 = 0.135
        # Total: 0.49
        
        self.assertEqual(conf.final_confidence, 0.49)
        self.assertIn("No verification data available", conf.reasoning)

if __name__ == '__main__':
    unittest.main()
