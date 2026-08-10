import unittest
import requests
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agents.supplier_agent import supplier_agent
from agents.verification_agent import verification_agent
from models.relationship import RelationshipResult
from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult
from product_benchmark import PRODUCT_COMPONENT_MAP
from scraping.supplier_discovery import SupplierDiscoveryScraper


EVIDENCE = [
    {
        "title": "Supplier relationship",
        "link": "https://example.com/supplier",
        "snippet": "Qualcomm supplies application processors to Apple for the iPhone 16 Pro.",
    }
]


def _state():
    return AgentState(
        target_company="Apple",
        product_name="iPhone 16 Pro",
        component_name="Application Processor",
        benchmark_target_query="Apple iPhone 16 Pro Application Processor",
        execution_mode="slm",
        provider="ollama",
        model="gemma3:4b",
        supplier_cache_enabled=True,
        mapping_queue=["Apple"],
    )


def _generation_chain(candidate_name="Qualcomm"):
    chain = Mock()
    chain.invoke.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(name=candidate_name, rationale="contextual hypothesis")]
    )
    parser = Mock()
    parser.get_format_instructions.return_value = "JSON schema"
    return chain, parser


class SlmCandidateGenerationTest(unittest.TestCase):
    def test_generated_evidence_retries_dns_and_rate_limit_failures(self):
        scraper = SupplierDiscoveryScraper(use_cache=False)
        response = SimpleNamespace(
            status_code=200,
            headers={},
            json=lambda: {"query": {"search": [{
                "title": "Qualcomm",
                "snippet": "Qualcomm supplies application processors to Apple.",
            }]}},
        )
        response.raise_for_status = lambda: None
        scraper.session.get = Mock(side_effect=[
            requests.exceptions.ConnectionError("DNS failure"),
            SimpleNamespace(status_code=429, headers={"Retry-After": "0"}),
            response,
            response,
            response,
        ])
        with patch("scraping.supplier_discovery.time.sleep") as sleep:
            evidence = scraper.retrieve_supplier_candidate_evidence(
                "Apple", "Qualcomm", component_name="Application Processor"
            )
        self.assertTrue(evidence)
        self.assertEqual(scraper.session.get.call_count, 5)
        self.assertEqual(sleep.call_count, 2)

    def test_generated_evidence_keeps_matching_cached_evidence_when_wikipedia_is_unavailable(self):
        scraper = SupplierDiscoveryScraper(use_cache=False)
        cached = [{
            "title": "Cached supplier record",
            "link": "cache://supplier",
            "snippet": "Qualcomm supplies application processors to Apple.",
        }]
        scraper._cached_candidate_evidence = Mock(return_value=cached)
        scraper.session.get = Mock(
            side_effect=requests.exceptions.ConnectionError("DNS failure")
        )
        with patch("scraping.supplier_discovery.time.sleep"):
            evidence = scraper.retrieve_supplier_candidate_evidence(
                "Apple", "Qualcomm", component_name="Application Processor"
            )
        self.assertEqual(evidence, cached)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper.find_suppliers", return_value=[])
    @patch(
        "agents.supplier_agent.SupplierDiscoveryScraper.retrieve_supplier_candidate_evidence",
        return_value=EVIDENCE,
    )
    @patch("agents.supplier_agent.get_candidate_generation_chain")
    def test_zero_normal_candidates_trigger_gemma_generation(
        self, get_chain, retrieve_evidence, find_suppliers
    ):
        get_chain.return_value = _generation_chain()
        state = _state()

        updated = supplier_agent(state)

        get_chain.assert_called_once_with("ollama", "gemma3:4b")
        self.assertEqual(updated.run_metadata["model_invocation_status"], "succeeded")
        self.assertIs(updated.run_metadata["model_invoked"], True)
        self.assertEqual(updated.run_metadata["candidate_source"], "gemma_generation")
        self.assertEqual(updated.run_metadata["generated_candidate_count"], 1)
        self.assertEqual(len(updated.suppliers), 1)
        self.assertTrue(updated.suppliers[0].model_generated)
        self.assertEqual(updated.suppliers[0].candidate_source, "gemma_generation")

    @patch("agents.supplier_agent.SupplierDiscoveryScraper.find_suppliers", return_value=[])
    @patch(
        "agents.supplier_agent.SupplierDiscoveryScraper.retrieve_supplier_candidate_evidence",
        return_value=[],
    )
    @patch("agents.supplier_agent.get_candidate_generation_chain")
    def test_unsupported_generated_candidates_are_rejected(
        self, get_chain, retrieve_evidence, find_suppliers
    ):
        get_chain.return_value = _generation_chain("Unsupported Vendor")
        updated = supplier_agent(_state())
        self.assertEqual(updated.suppliers, [])
        self.assertEqual(updated.run_metadata["generated_candidate_count"], 1)
        self.assertIs(updated.run_metadata["model_invoked"], True)

    def test_generated_candidates_are_verified_before_retention(self):
        supplier = SupplierInfo(
            name="Qualcomm",
            canonical_name="Qualcomm",
            location="Unknown",
            tier=1,
            discovery_confidence=0.75,
            model_generated=True,
            candidate_source="gemma_generation",
            evidence=EVIDENCE,
        )
        state = _state()
        state.mapping_queue = []
        state.suppliers = [supplier]
        state.relationship_results = [
            RelationshipResult(
                target_company="Apple",
                candidate_company="Qualcomm",
                relationship_type="supplier",
                confidence_score=0.9,
                reasoning="model-classified supplier",
                evidence_text=EVIDENCE[0]["snippet"],
            )
        ]
        verified = VerificationResult(
            supplier_name="Qualcomm",
            relationship_type="supplier",
            verified=True,
            company_exists=True,
            relationship_verified=True,
            evidence_quality=0.9,
            source_quality=0.8,
            confidence_score=0.85,
            verification_status="VERIFIED",
            reasoning="verified",
        )
        with patch("agents.verification_agent.VerificationAggregator.aggregate", return_value=verified):
            updated = verification_agent(state)
        self.assertEqual(len(updated.suppliers), 1)
        self.assertEqual(updated.run_metadata["verified_generated_candidate_count"], 1)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper.find_suppliers", return_value=[])
    @patch(
        "agents.supplier_agent.SupplierDiscoveryScraper.retrieve_supplier_candidate_evidence",
        return_value=EVIDENCE,
    )
    @patch("agents.supplier_agent.get_candidate_generation_chain")
    def test_generation_prompt_contains_no_reference_data(
        self, get_chain, retrieve_evidence, find_suppliers
    ):
        chain, parser = _generation_chain()
        get_chain.return_value = chain, parser
        supplier_agent(_state())
        prompt_values = chain.invoke.call_args.args[0]
        self.assertEqual(
            prompt_values,
            {
                "company": "Apple",
                "product": "iPhone 16 Pro",
                "component": "Application Processor",
                "format_instructions": "JSON schema",
            },
        )

    @patch("agents.supplier_agent.SupplierDiscoveryScraper.find_suppliers", return_value=[])
    @patch(
        "agents.supplier_agent.SupplierDiscoveryScraper.retrieve_supplier_candidate_evidence",
        return_value=EVIDENCE,
    )
    @patch("agents.supplier_agent.get_candidate_generation_chain")
    def test_every_slm_product_component_row_can_invoke_gemma(
        self, get_chain, retrieve_evidence, find_suppliers
    ):
        get_chain.return_value = _generation_chain()
        count = 0
        for company, product_info in PRODUCT_COMPONENT_MAP.items():
            for component in product_info["components"]:
                state = AgentState(
                    target_company=company,
                    product_name=product_info["product"],
                    component_name=component,
                    benchmark_target_query=f"{company} {product_info['product']} {component}",
                    execution_mode="slm",
                    provider="ollama",
                    model="gemma3:4b",
                    supplier_cache_enabled=True,
                    mapping_queue=[company],
                )
                updated = supplier_agent(state)
                self.assertTrue(updated.run_metadata["model_invoked"])
                count += 1
        self.assertEqual(count, 17)
        self.assertEqual(get_chain.call_count, 17)


if __name__ == "__main__":
    unittest.main()
