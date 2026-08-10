import unittest
import json
import os
import re
from unittest.mock import MagicMock, patch

from providers.llm_provider import LLMConfig
from agents.relationship_agent import (
    HeuristicRelationshipClassifier,
    LLMRelationshipClassifier,
    relationship_agent,
)
from chains.relationship_chain import (
    RelationshipBatchClassification,
    RelationshipBatchOutputParser,
    RelationshipClassification,
)
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

    def _batch_classifier_for_raw_response(self, raw_response):
        classifier = object.__new__(LLMRelationshipClassifier)
        classifier.batch_parser = RelationshipBatchOutputParser(
            pydantic_object=RelationshipBatchClassification
        )
        classifier.batch_chain = MagicMock()
        classifier.batch_chain.invoke.return_value = classifier.batch_parser.parse(
            raw_response
        )
        return classifier

    def test_wrapped_batch_response_parses(self):
        classifier = self._batch_classifier_for_raw_response(json.dumps({
            "results": [{
                "supplier_name": "TSMC",
                "relationship": "supplier",
                "confidence": 0.9,
                "reasoning": "Direct supply evidence.",
            }]
        }))

        valid, invalid = classifier.classify_batch([{
            "candidate_entity": "TSMC",
            "target_company": "Apple",
            "evidence": "TSMC supplies chips to Apple.",
        }])

        self.assertEqual(valid["TSMC"].relationship, "supplier")
        self.assertEqual(invalid, {})

    def test_bare_batch_list_parses_after_normalization(self):
        classifier = self._batch_classifier_for_raw_response(json.dumps([{
            "supplier_name": "TSMC",
            "relationship": "supplier",
            "confidence": 0.9,
            "reasoning": "Direct supply evidence.",
        }]))

        valid, invalid = classifier.classify_batch([{
            "candidate_entity": "TSMC",
            "target_company": "Apple",
            "evidence": "TSMC supplies chips to Apple.",
        }])

        self.assertEqual(valid["TSMC"].relationship, "supplier")
        self.assertEqual(invalid, {})

    def test_malformed_batch_json_fails(self):
        with self.assertRaises(Exception):
            self._batch_classifier_for_raw_response("{not valid json")

    def test_unknown_batch_supplier_names_still_fail(self):
        classifier = self._batch_classifier_for_raw_response(json.dumps([{
            "supplier_name": "Unknown",
            "relationship": "supplier",
            "confidence": 0.9,
            "reasoning": "Unexpected supplier.",
        }]))
        with self.assertRaisesRegex(RuntimeError, "unknown supplier result"):
            classifier.classify_batch([{
                "candidate_entity": "TSMC",
                "target_company": "Apple",
                "evidence": "TSMC supplies chips to Apple.",
            }])

    def test_duplicate_supplier_results_are_deduplicated_without_fallback(self):
        classifier = self._batch_classifier_for_raw_response(json.dumps([
            {
                "supplier_name": "LG Display",
                "relationship": "supplier",
                "confidence": 0.9,
                "reasoning": "First result.",
            },
            {
                "supplier_name": "LG Display",
                "relationship": "supplier",
                "confidence": 0.8,
                "reasoning": "Duplicate result.",
            },
        ]))
        valid, invalid = classifier.classify_batch([{
            "candidate_entity": "LG Display",
            "target_company": "Samsung",
            "evidence": "LG Display supplies panels to Samsung.",
        }])
        self.assertEqual(set(valid), {"LG Display"})
        self.assertEqual(valid["LG Display"].confidence, 0.9)
        self.assertEqual(invalid, {})

    def test_alias_duplicate_supplier_results_are_deduplicated(self):
        classifier = self._batch_classifier_for_raw_response(json.dumps([
            {
                "supplier_name": "Pegatron",
                "relationship": "supplier",
                "confidence": 0.9,
                "reasoning": "First result.",
            },
            {
                "supplier_name": "Pegatron Corporation",
                "relationship": "supplier",
                "confidence": 0.8,
                "reasoning": "Alias duplicate.",
            },
        ]))
        valid, invalid = classifier.classify_batch([{
            "candidate_entity": "Pegatron",
            "target_company": "Samsung",
            "evidence": "Pegatron supplies assembled devices to Samsung.",
        }])
        self.assertEqual(set(valid), {"Pegatron"})
        self.assertEqual(invalid, {})


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
        mock_classifier.classify_batch = MagicMock(return_value=(
            {
                "TSMC": RelationshipClassification(
                    relationship="supplier",
                    confidence=0.91,
                    reasoning="TSMC manufactures chips for Apple.",
                )
            },
            {},
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
        mock_classifier.classify_batch.assert_called_once()
        batch_items = mock_classifier.classify_batch.call_args.args[0]
        self.assertIn("TSMC", batch_items[0]["candidate_entity"])
        self.assertIn("Canonical company: Taiwan Semiconductor Manufacturing Company", batch_items[0]["evidence"])
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

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_heuristic_exception_is_not_retried_as_the_same_fallback(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        state = AgentState(
            target_company="Apple",
            benchmark_fast_mode=True,
            execution_mode="llm",
        )
        state.suppliers = [
            SupplierInfo(
                name="TSMC",
                canonical_name="TSMC",
                location="Taiwan",
                evidence=[{"snippet": "TSMC supplies chips to Apple."}],
            )
        ]

        with patch.object(
            HeuristicRelationshipClassifier,
            "classify",
            side_effect=RuntimeError("heuristic bug"),
        ):
            with self.assertRaisesRegex(RuntimeError, "heuristic bug"):
                relationship_agent(state)

    def _batch_state(self, count=11):
        state = AgentState(target_company="Apple", execution_mode="llm")
        state.company = type("Company", (), {"name": "Apple"})()
        state.suppliers = [
            SupplierInfo(
                name=f"Supplier {index}",
                canonical_name=f"Supplier {index}",
                location="US",
                evidence=[{"snippet": f"Supplier {index} supplies parts to Apple."}],
            )
            for index in range(count)
        ]
        return state

    def _batch_classifier(self, side_effect=None):
        classifier = object.__new__(LLMRelationshipClassifier)
        classifier.config = LLMConfig(
            provider="google",
            model="gemini-2.5-flash",
            key_source="GOOGLE_API_KEY",
            api_key="google-test-key",
        )

        def classify(items):
            if side_effect:
                return side_effect(items)
            return (
                {
                    item["candidate_entity"]: RelationshipClassification(
                        relationship="supplier",
                        confidence=0.9,
                        reasoning="Valid supplier result.",
                    )
                    for item in items
                },
                {},
            )

        classifier.classify_batch = MagicMock(side_effect=classify)
        return classifier

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_eleven_suppliers_use_three_batches_without_fallback(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        classifier = self._batch_classifier()
        state = self._batch_state()
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ), patch.dict(os.environ, {"RELATIONSHIP_CLASSIFICATION_BATCH_SIZE": "5"}):
            updated = relationship_agent(state)

        self.assertEqual(classifier.classify_batch.call_count, 3)
        self.assertEqual(len(updated.relationship_results), 11)
        self.assertTrue(updated.run_metadata["primary_model_success"])
        self.assertFalse(updated.run_metadata.get("fallback_used", False))

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_invalid_result_falls_back_only_for_that_supplier(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state

        def partial(items):
            first = items[0]["candidate_entity"]
            return (
                {
                    item["candidate_entity"]: RelationshipClassification(
                        relationship="supplier", confidence=0.9, reasoning="valid"
                    )
                    for item in (items[0], items[2])
                },
                {items[1]["candidate_entity"]: "invalid supplier classification result"},
            )

        classifier = self._batch_classifier(partial)
        state = self._batch_state(3)
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ):
            updated = relationship_agent(state)

        self.assertEqual(len(updated.relationship_results), 3)
        self.assertEqual(updated.relationship_results[0].reasoning, "valid")
        self.assertIn("Evidence contains direct supplier", updated.relationship_results[1].reasoning)
        self.assertEqual(updated.relationship_results[2].reasoning, "valid")
        self.assertFalse(updated.run_metadata["primary_model_success"])
        self.assertEqual(updated.run_metadata["fallback_stages"], ["relationship_classification"])

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_failed_batch_falls_back_only_for_its_suppliers(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        calls = 0

        def fail_second(items):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("ordinary parse error")
            return self._batch_classifier().classify_batch(items)

        classifier = self._batch_classifier(fail_second)
        state = self._batch_state(6)
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ):
            updated = relationship_agent(state)

        self.assertEqual(classifier.classify_batch.call_count, 2)
        self.assertEqual(updated.relationship_results[0].reasoning, "Valid supplier result.")
        self.assertIn("Evidence contains direct supplier", updated.relationship_results[5].reasoning)
        self.assertFalse(updated.run_metadata["primary_model_success"])
        self.assertFalse(updated.quota_exhausted)

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_quota_status_requires_quota_signature(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        for message, expected in (("ordinary parse error", False), ("429 ResourceExhausted", True)):
            classifier = self._batch_classifier(
                lambda items, message=message: (_ for _ in ()).throw(RuntimeError(message))
            )
            state = self._batch_state(2)
            with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
                "agents.relationship_agent.print_llm_config_once"
            ):
                updated = relationship_agent(state)
            self.assertEqual(updated.quota_exhausted, expected)

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_all_successful_batches_keep_primary_model_success_true(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        classifier = self._batch_classifier()
        state = self._batch_state(11)
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ):
            updated = relationship_agent(state)
        self.assertIs(updated.run_metadata["primary_model_success"], True)

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_bare_list_batches_do_not_trigger_fallback(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state
        classifier = object.__new__(LLMRelationshipClassifier)
        classifier.config = LLMConfig(
            provider="ollama",
            model="gemma3:4b",
            key_source=None,
            api_key=None,
        )
        classifier.batch_parser = RelationshipBatchOutputParser(
            pydantic_object=RelationshipBatchClassification
        )
        classifier.batch_chain = MagicMock()

        def parse_bare_list(payload):
            names = re.findall(r"Input supplier_name: ([^\n]+)", payload["batch_evidence"])
            return classifier.batch_parser.parse(json.dumps([
                {
                    "supplier_name": name,
                    "relationship": "supplier",
                    "confidence": 0.9,
                    "reasoning": "Valid bare-list result.",
                }
                for name in names
            ]))

        classifier.batch_chain.invoke.side_effect = parse_bare_list
        state = self._batch_state(11)
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ):
            updated = relationship_agent(state)

        self.assertEqual(len(updated.relationship_results), 11)
        self.assertIs(updated.run_metadata["primary_model_success"], True)
        self.assertFalse(updated.run_metadata.get("fallback_used", False))
        self.assertNotIn("relationship_classification", updated.run_metadata.get("fallback_stages", []))

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    def test_any_supplier_fallback_makes_primary_model_success_false(self, mock_enrich):
        mock_enrich.side_effect = lambda state, stage: state

        def partial(items):
            return ({items[0]["candidate_entity"]: RelationshipClassification(
                relationship="supplier", confidence=0.9, reasoning="valid"
            )}, {})

        classifier = self._batch_classifier(partial)
        state = self._batch_state(2)
        with patch("agents.relationship_agent.get_classifier", return_value=classifier), patch(
            "agents.relationship_agent.print_llm_config_once"
        ):
            updated = relationship_agent(state)
        self.assertIs(updated.run_metadata["primary_model_success"], False)


if __name__ == "__main__":
    unittest.main()
