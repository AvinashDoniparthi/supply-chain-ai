import unittest
from unittest.mock import MagicMock, patch

from providers.llm_provider import LLMConfig
from agents.relationship_agent import (
    HeuristicRelationshipClassifier,
    LLMRelationshipClassifier,
    relationship_agent,
)
from chains.relationship_chain import RelationshipClassification
from models.relationship import RelationshipResult
from models.state import AgentState, SupplierInfo


class TestLLMRelationshipClassifier(unittest.TestCase):
    def setUp(self):
        self.mock_chain = MagicMock()
        self.resolve_patcher = patch(
            "agents.relationship_agent.resolve_provider",
            return_value=LLMConfig(
                provider="google",
                model="gemini-2.5-flash",
                key_source="GOOGLE_API_KEY",
                api_key="google-test-key",
            ),
        )
        self.chain_patcher = patch(
            "agents.relationship_agent.get_relationship_chain",
            return_value=self.mock_chain,
        )
        self.resolve_patcher.start()
        self.chain_patcher.start()
        self.addCleanup(self.resolve_patcher.stop)
        self.addCleanup(self.chain_patcher.stop)
        self.classifier = LLMRelationshipClassifier()

    def test_supplier_detection(self):
        self.mock_chain.invoke.return_value = RelationshipClassification(
            relationship="supplier",
            confidence=0.95,
            reasoning="Candidate provides components to Target.",
        )

        result = self.classifier.classify("Apple", "TSMC", "TSMC manufactures chips for Apple.")

        self.assertEqual(result.relationship_type, "supplier")
        self.assertEqual(result.confidence_score, 0.95)
        self.assertEqual(result.candidate_company, "TSMC")

    def test_invalid_label_raises(self):
        self.mock_chain.invoke.return_value = RelationshipClassification(
            relationship="friend",
            confidence=0.5,
            reasoning="Invalid label.",
        )

        with self.assertRaisesRegex(RuntimeError, "Invalid relationship label"):
            self.classifier.classify("Company A", "Company B", "Evidence text")

    def test_chain_failure_raises(self):
        self.mock_chain.invoke.side_effect = Exception("parse error")

        with self.assertRaisesRegex(RuntimeError, "Relationship classification failed"):
            self.classifier.classify("Company A", "Company B", "Evidence text")


class TestRelationshipAgent(unittest.TestCase):
    @patch("agents.relationship_agent.print_llm_config_once")
    @patch("agents.relationship_agent.get_classifier")
    def test_relationship_agent_passes_context_to_classifier(
        self, mock_get_classifier, mock_print_config
    ):
        mock_classifier = object.__new__(LLMRelationshipClassifier)
        mock_classifier.config = LLMConfig(
            provider="google",
            model="gemini-2.5-flash",
            key_source="GOOGLE_API_KEY",
            api_key="google-test-key",
        )
        mock_classifier.classify = MagicMock(return_value=RelationshipResult(
            target_company="Apple",
            candidate_company="TSMC",
            relationship_type="supplier",
            confidence_score=0.91,
            reasoning="TSMC manufactures chips for Apple.",
            evidence_text="TSMC manufactures chips for Apple.",
        ))
        mock_get_classifier.return_value = mock_classifier

        state = AgentState(target_company="Apple")
        state.company = type("Company", (), {"name": "Apple"})()
        state.suppliers = [
            SupplierInfo(
                name="TSMC",
                canonical_name="Taiwan Semiconductor Manufacturing Company",
                location="Taiwan",
                parent_company="Apple",
                evidence=[{"snippet": "TSMC manufactures chips for Apple."}],
            )
        ]

        updated_state = relationship_agent(state)

        self.assertEqual(len(updated_state.relationship_results), 1)
        mock_classifier.classify.assert_called_once()
        args, kwargs = mock_classifier.classify.call_args
        self.assertIn("Supplier name: TSMC", kwargs["evidence"])
        self.assertIn("Canonical company: Taiwan Semiconductor Manufacturing Company", kwargs["evidence"])
        self.assertEqual(
            updated_state.relationship_results[0].evidence_text,
            "TSMC manufactures chips for Apple.",
        )

    def test_tier_two_supplier_is_labeled_upstream(self):
        state = AgentState(target_company="AMD", skip_risk=True, max_depth=2)
        state.company = type("Company", (), {"name": "AMD"})()
        state.suppliers = [
            SupplierInfo(
                name="ASML",
                canonical_name="ASML",
                location="Netherlands",
                tier=2,
                parent_company="Taiwan Semiconductor Manufacturing Company",
                evidence=[
                    {
                        "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                    }
                ],
            )
        ]

        updated_state = relationship_agent(state)

        self.assertEqual(
            updated_state.relationship_results[0].relationship_type,
            "upstream_supplier",
        )

    def test_heuristic_classifies_thinkpad_as_product_or_brand(self):
        classifier = HeuristicRelationshipClassifier()

        result = classifier.classify(
            "AMD",
            "ThinkPad",
            "ThinkPad laptops use AMD processors.",
        )

        self.assertEqual(result.relationship_type, "product_or_brand")


if __name__ == "__main__":
    unittest.main()
