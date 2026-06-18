import unittest
from unittest.mock import MagicMock, patch
import json
from agents.relationship_agent import LLMRelationshipClassifier
from models.relationship import RelationshipResult

class TestLLMRelationshipClassifier(unittest.TestCase):
    def setUp(self):
        # Mock the OpenAI client
        self.mock_client = MagicMock()
        with patch('openai.OpenAI', return_value=self.mock_client):
            self.classifier = LLMRelationshipClassifier()
            # Manually set the client if the patch didn't work as expected in __init__
            self.classifier.client = self.mock_client

    def _mock_response(self, relationship, confidence, reasoning):
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "relationship": relationship,
            "confidence": confidence,
            "reasoning": reasoning
        })
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_client.chat.completions.create.return_value = mock_response

    def test_supplier_detection(self):
        self._mock_response("supplier", 0.95, "Candidate provides components to Target.")
        result = self.classifier.classify("Apple", "TSMC", "TSMC manufactures chips for Apple.")
        
        self.assertEqual(result.relationship_type, "supplier")
        self.assertEqual(result.confidence_score, 0.95)
        self.assertIn("TSMC", result.candidate_company)

    def test_customer_detection(self):
        self._mock_response("customer", 0.9, "Target sells GPUs to Candidate.")
        result = self.classifier.classify("Nvidia", "Dell", "Dell sells servers powered by Nvidia GPUs.")
        
        self.assertEqual(result.relationship_type, "customer")
        self.assertEqual(result.confidence_score, 0.9)

    def test_competitor_detection(self):
        self._mock_response("competitor", 0.85, "Both compete in the cloud market.")
        result = self.classifier.classify("AWS", "Azure", "Azure is gaining market share against AWS.")
        
        self.assertEqual(result.relationship_type, "competitor")

    def test_partner_detection(self):
        self._mock_response("partner", 0.8, "Joint development of AI models.")
        result = self.classifier.classify("Microsoft", "OpenAI", "Microsoft and OpenAI have a strategic partnership.")
        
        self.assertEqual(result.relationship_type, "partner")

    def test_malformed_response_handling(self):
        # LLM returns something that is not one of the labels
        self._mock_response("friend", 0.5, "They are friends.")
        result = self.classifier.classify("Company A", "Company B", "Evidence text")
        
        self.assertEqual(result.relationship_type, "unknown")
        self.assertEqual(result.confidence_score, 0.1)
        self.assertIn("Invalid label", result.reasoning)

    def test_json_parse_error_fallback(self):
        # Mocking a response that isn't valid JSON
        mock_choice = MagicMock()
        mock_choice.message.content = "Not a JSON"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        self.mock_client.chat.completions.create.return_value = mock_response
        
        result = self.classifier.classify("Company A", "Company B", "Evidence text")
        
        self.assertEqual(result.relationship_type, "unknown")
        self.assertEqual(result.confidence_score, 0.1)
        self.assertIn("Classification error", result.reasoning)

if __name__ == "__main__":
    unittest.main()
