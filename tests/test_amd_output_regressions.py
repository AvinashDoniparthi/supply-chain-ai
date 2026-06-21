import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.executive_report_agent import executive_report_agent
from agents.risk_agent import GeopoliticalRiskProvider, NewsRiskProvider
from agents.supplier_agent import supplier_agent
from agents.verification_agent import CuratedCompanyVerificationProvider
from models.relationship import RelationshipResult
from models.state import (
    AgentState,
    CompanyInfo,
    RiskAnalysis,
    SupplierConfidence,
    SupplierCriticality,
    SupplierInfo,
    SupplyChainHealth,
)
from models.verification import VerificationResult
from scraping.supplier_discovery import normalize_supplier_candidate_name
from utils.identity_resolution import resolver
from utils.output import render_final_report


class TestAMDOutputRegressions(unittest.TestCase):
    def _amd_report_state(self):
        state = AgentState(target_company="AMD")
        state.company = CompanyInfo(name="AMD")
        state.suppliers = [
            SupplierInfo(
                name="TSMC",
                canonical_name="Taiwan Semiconductor Manufacturing Company",
                location="Taiwan",
                products=["Semiconductor foundry"],
                tier=1,
                parent_company="AMD",
                relationship_path=["AMD", "Taiwan Semiconductor Manufacturing Company"],
                discovery_confidence=0.96,
                propagated_confidence=0.96,
            ),
            SupplierInfo(
                name="ASML",
                canonical_name="ASML",
                location="Netherlands",
                products=["EUV lithography systems"],
                tier=2,
                parent_company="Taiwan Semiconductor Manufacturing Company",
                relationship_path=[
                    "AMD",
                    "Taiwan Semiconductor Manufacturing Company",
                    "ASML",
                ],
                discovery_confidence=0.95,
                propagated_confidence=0.91,
            ),
        ]
        state.relationship_results = [
            RelationshipResult(
                target_company="AMD",
                candidate_company="TSMC",
                relationship_type="supplier",
                confidence_score=0.95,
                reasoning="TSMC manufactures AMD chips.",
                evidence_text="TSMC manufactures AMD chips.",
            ),
            RelationshipResult(
                target_company="Taiwan Semiconductor Manufacturing Company",
                candidate_company="ASML",
                relationship_type="upstream_supplier",
                confidence_score=0.92,
                reasoning="ASML supplies lithography systems to TSMC.",
                evidence_text="ASML supplies EUV lithography systems to TSMC.",
            ),
        ]
        state.verification_results = [
            VerificationResult(
                supplier_name="TSMC",
                relationship_type="supplier",
                verified=True,
                confidence_score=0.9,
                reasoning="Confirmed.",
            ),
            VerificationResult(
                supplier_name="ASML",
                relationship_type="upstream_supplier",
                verified=False,
                confidence_score=0.42,
                reasoning="Relationship evidence could not be verified.",
            ),
        ]
        state.supplier_confidence_scores = [
            SupplierConfidence(
                supplier_name="TSMC",
                discovery_confidence=0.96,
                relationship_confidence=0.95,
                verification_confidence=0.9,
                risk_confidence=0.75,
                final_confidence=0.91,
                reasoning="Strong direct foundry evidence.",
            ),
            SupplierConfidence(
                supplier_name="ASML",
                discovery_confidence=0.95,
                relationship_confidence=0.92,
                verification_confidence=0.21,
                risk_confidence=0.75,
                final_confidence=0.64,
                reasoning="Upstream supplier with failed verification.",
            ),
        ]
        state.supplier_criticality_scores = [
            SupplierCriticality(
                supplier_name="TSMC",
                criticality_score=0.9,
                criticality_level="Critical",
                reasoning="Core foundry.",
            ),
            SupplierCriticality(
                supplier_name="ASML",
                criticality_score=0.7,
                criticality_level="High",
                reasoning="Upstream equipment dependency.",
            ),
        ]
        state.risk_assessments = [
            RiskAnalysis(
                supplier_name="ASML",
                risk_type="Strategic",
                severity="High",
                confidence=0.42,
                reasoning="Supplier failed verification. Reasoning: relationship evidence could not be verified.",
            ),
            RiskAnalysis(
                supplier_name="TSMC",
                risk_type="Geopolitical",
                severity="Medium",
                confidence=0.7,
                reasoning="Supplier located in region with increasing trade or political tensions (Taiwan).",
            ),
        ]
        state.supply_chain_health = SupplyChainHealth(
            overall_score=72.0,
            status="Good",
            supplier_count=2,
            critical_suppliers=1,
            high_risk_suppliers=0,
            summary="Good with data-quality warnings.",
        )
        return state

    def test_amd_report_groups_suppliers_by_tier_and_marks_asml_upstream(self):
        state = executive_report_agent(self._amd_report_state())
        summary = state.executive_report.executive_summary

        self.assertIn("TIER 1 SUPPLIERS", summary)
        self.assertIn("TIER 2 SUPPLIERS", summary)
        self.assertNotIn("SUPPLIERS IDENTIFIED", summary)

        tier1_block = summary.split("TIER 1 SUPPLIERS", 1)[1].split("TIER 2 SUPPLIERS", 1)[0]
        tier2_block = summary.split("TIER 2 SUPPLIERS", 1)[1].split("TIER 3 SUPPLIERS", 1)[0]

        self.assertIn("- TSMC", tier1_block)
        self.assertNotIn("- ASML", tier1_block)
        self.assertIn("- ASML", tier2_block)
        self.assertIn("Parent: Taiwan Semiconductor Manufacturing Company", tier2_block)
        self.assertIn("Relationship: upstream_supplier", tier2_block)

    def test_verification_failure_is_data_quality_warning_not_top_risk(self):
        state = executive_report_agent(self._amd_report_state())
        summary = state.executive_report.executive_summary
        top_risks = summary.split("TOP RISKS", 1)[1].split("DATA QUALITY WARNINGS", 1)[0]
        warnings = summary.split("DATA QUALITY WARNINGS", 1)[1].split("CRITICAL SUPPLIERS", 1)[0]

        self.assertNotIn("Supplier failed verification", top_risks)
        self.assertIn("Supplier failed verification: ASML", warnings)
        self.assertIn("Reason: Relationship evidence could not be verified.", warnings)

    def test_final_renderer_uses_tier_sections_not_flat_supplier_list(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            render_final_report(self._amd_report_state())
        output = buffer.getvalue()

        self.assertIn("TIER 1 SUPPLIERS", output)
        self.assertIn("TIER 2 SUPPLIERS", output)
        self.assertNotIn("SUPPLIERS IDENTIFIED", output)
        self.assertNotIn("[HIGH] Supplier failed verification", output)
        self.assertIn("DATA QUALITY WARNINGS", output)

    def test_thinkpad_is_rejected_as_product_or_brand(self):
        self.assertIsNone(normalize_supplier_candidate_name("ThinkPad"))

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_amd_rejects_qualcomm_without_explicit_supplier_evidence_to_amd(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Qualcomm",
                "location": "United States",
                "products": ["Mobile chipsets"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": "Qualcomm provides modem chipsets to Samsung Electronics devices."
                    }
                ],
            }
        ]

        state = AgentState(target_company="AMD")
        state.company = CompanyInfo(name="AMD")
        state.suppliers = [
            SupplierInfo(
                name="Samsung",
                canonical_name="Samsung Electronics",
                location="South Korea",
                products=["Foundry services"],
                tier=1,
                parent_company="AMD",
                relationship_path=["AMD", "Samsung Electronics"],
                discovery_confidence=0.88,
                propagated_confidence=0.88,
            )
        ]
        state.mapping_queue = ["Samsung Electronics"]
        state.seen_companies = ["AMD", "Samsung Electronics"]
        state.max_depth = 2

        updated_state = supplier_agent(state)

        self.assertEqual([supplier.name for supplier in updated_state.suppliers], ["Samsung"])

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_amd_keeps_qualcomm_when_supplier_evidence_to_amd_is_explicit(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Qualcomm",
                "location": "United States",
                "products": ["Connectivity chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": "Qualcomm supplies connectivity chips to AMD for embedded systems."
                    }
                ],
            }
        ]

        state = AgentState(target_company="AMD")
        state.company = CompanyInfo(name="AMD")
        state.mapping_queue = ["AMD"]
        state.seen_companies = ["AMD"]

        updated_state = supplier_agent(state)

        self.assertEqual([supplier.name for supplier in updated_state.suppliers], ["Qualcomm"])

    def test_taiwan_geopolitical_risk_names_tsmc_supply_path(self):
        state = self._amd_report_state()

        risks = GeopoliticalRiskProvider().assess_risk(state)

        tsmc_risk = next(risk for risk in risks if risk.supplier_name == "TSMC")
        self.assertEqual(tsmc_risk.severity, "High")
        self.assertIn("TSMC", tsmc_risk.reasoning)
        self.assertIn("Affected path: AMD -> TSMC", tsmc_risk.reasoning)
        self.assertIn("Taiwan", tsmc_risk.reasoning)

    def test_generic_industry_news_is_not_high_without_direct_supplier_impact(self):
        provider = NewsRiskProvider()
        samsung = SupplierInfo(
            name="Samsung",
            canonical_name="Samsung Electronics",
            location="South Korea",
        )
        generic_item = {
            "title": "Chinese memory brands ditch Samsung and Micron",
            "snippet": (
                "The semiconductor industry article discusses a possible memory "
                "shortage and market disruption among customers and brands."
            ),
            "pub_date": "Sun, 21 Jun 2026 00:00:00 GMT",
        }
        direct_item = {
            "title": "Samsung factory fire causes production disruption",
            "snippet": "A Samsung Electronics fab halted output after a fire.",
            "pub_date": "Sun, 21 Jun 2026 00:00:00 GMT",
        }

        generic_risk, _ = provider._analyze_headline_with_keywords(
            samsung, generic_item, "AMD"
        )
        direct_risk, _ = provider._analyze_headline_with_keywords(
            samsung, direct_item, "AMD"
        )

        self.assertIsNotNone(generic_risk)
        self.assertIn(generic_risk.severity, {"Low", "Medium"})
        self.assertNotEqual(generic_risk.severity, "High")
        self.assertIsNotNone(direct_risk)
        self.assertIn(direct_risk.severity, {"High", "Critical"})

    def test_sony_semiconductor_canonicalizes_for_verification(self):
        canonical = resolver.resolve("Sony Semiconductor")
        verification = CuratedCompanyVerificationProvider().verify(canonical, [])

        self.assertEqual(canonical, "Sony Semiconductor Solutions")
        self.assertTrue(verification.verified)

    def test_amd_executive_summary_is_two_sentences_and_names_main_risk(self):
        state = self._amd_report_state()
        state.suppliers.extend(
            [
                SupplierInfo(
                    name="Samsung",
                    canonical_name="Samsung Electronics",
                    location="South Korea",
                    products=["Foundry services"],
                    tier=1,
                    parent_company="AMD",
                    relationship_path=["AMD", "Samsung Electronics"],
                    discovery_confidence=0.88,
                    propagated_confidence=0.88,
                ),
                SupplierInfo(
                    name="ASE Technology",
                    canonical_name="ASE Technology",
                    location="Taiwan",
                    products=["Semiconductor packaging", "Assembly and test"],
                    tier=1,
                    parent_company="AMD",
                    relationship_path=["AMD", "ASE Technology"],
                    discovery_confidence=0.87,
                    propagated_confidence=0.87,
                ),
                SupplierInfo(
                    name="Amkor Technology",
                    canonical_name="Amkor Technology",
                    location="United States / Asia",
                    products=["Semiconductor packaging", "Assembly and test"],
                    tier=1,
                    parent_company="AMD",
                    relationship_path=["AMD", "Amkor Technology"],
                    discovery_confidence=0.86,
                    propagated_confidence=0.86,
                ),
            ]
        )
        state.risk_assessments.append(
            RiskAnalysis(
                supplier_name="ASE Technology",
                risk_type="News",
                severity="High",
                confidence=0.75,
                reasoning="Supplier labor disruption signal for ASE Technology: ASE Technology workers strike at packaging facility.",
            )
        )

        state = executive_report_agent(state)
        summary = state.executive_report.executive_summary.split("EXECUTIVE SUMMARY", 1)[1].strip()
        sentences = [part for part in re.split(r"(?<=[.!?])\s+", summary) if part]

        self.assertLessEqual(len(sentences), 2)
        self.assertNotIn("primary risk", summary.lower())
        self.assertNotIn("..", summary)
        self.assertIn("TSMC", summary)
        self.assertIn("Samsung", summary)
        self.assertIn("geographic and labor disruption exposure", summary)


if __name__ == "__main__":
    unittest.main()
