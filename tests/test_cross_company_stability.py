import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agents.deduplication_agent import deduplication_agent
from agents.supplier_agent import supplier_agent
from agents.verification_agent import verification_agent
from models.relationship import RelationshipResult
from models.state import AgentState, CompanyInfo, SupplierInfo
from scraping.supplier_discovery import (
    SupplierDiscoveryScraper,
    discovery_queries,
    validate_supplier_candidate_name,
)
from utils.identity_resolution import resolver


class FakeWikipediaResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeWikipediaSession:
    def __init__(self, search_results=None, extracts=None):
        self.search_results = search_results or {}
        self.extracts = extracts or {}
        self.seen_queries = []

    def get(self, _url, params=None, **_kwargs):
        params = params or {}
        if params.get("list") == "search":
            query = params.get("srsearch", "")
            self.seen_queries.append(query)
            return FakeWikipediaResponse(
                {"query": {"search": self.search_results.get(query, [])}}
            )

        if params.get("prop") == "extracts":
            title = params.get("titles", "")
            return FakeWikipediaResponse(
                {
                    "query": {
                        "pages": {
                            "1": {
                                "title": title,
                                "extract": self.extracts.get(title, ""),
                            }
                        }
                    }
                }
            )

        return FakeWikipediaResponse({})


def supplier(name, snippet, canonical_name=None, tier=1, parent="Apple"):
    return SupplierInfo(
        name=name,
        canonical_name=canonical_name,
        location="Unknown",
        products=["Components"],
        tier=tier,
        parent_company=parent,
        relationship_path=[parent, canonical_name or name],
        discovery_confidence=0.9,
        propagated_confidence=0.9,
        evidence=[
            {
                "title": f"{name} supplier evidence",
                "link": f"curated://test/{name}",
                "snippet": snippet,
            }
        ],
    )


def relationship(target, candidate, evidence, rel_type="supplier", confidence=0.9):
    return RelationshipResult(
        target_company=target,
        candidate_company=candidate,
        relationship_type=rel_type,
        confidence_score=confidence,
        reasoning="Fixture relationship evidence.",
        evidence_text=evidence,
    )


class TestCrossCompanyStability(unittest.TestCase):
    def run_discovery(self, company, search_results=None, extracts=None):
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper()
            scraper.cache_dir = cache_dir
            scraper.session = FakeWikipediaSession(search_results, extracts)
            with patch("scraping.supplier_discovery.time.sleep", return_value=None):
                suppliers = scraper.find_suppliers(company)
            return suppliers, scraper.session.seen_queries

    def test_apple_hon_hai_foxconn_aliases_merge_and_verify(self):
        evidence = (
            "Foxconn, also known as Hon Hai Precision Industry, is a contract "
            "manufacturer and assembly partner for Apple hardware."
        )
        state = AgentState(target_company="Apple")
        state.company = CompanyInfo(name="Apple")
        state.suppliers = [
            supplier("Foxconn", evidence),
            supplier("Hon Hai Precision Industry", evidence),
            supplier("Hon Hai Technology Group", evidence),
        ]
        state.relationship_results = [
            relationship("Apple", "Foxconn", evidence),
            relationship("Apple", "Hon Hai Precision Industry", evidence),
            relationship("Apple", "Hon Hai Technology Group", evidence),
        ]

        state = deduplication_agent(state)
        self.assertEqual(len(state.suppliers), 1)
        self.assertEqual(
            state.suppliers[0].canonical_name,
            "Hon Hai Precision Industry Co., Ltd.",
        )

        state = verification_agent(state)
        self.assertEqual(len(state.verification_results), 1)
        self.assertTrue(state.verification_results[0].verified)
        self.assertEqual(
            state.verification_results[0].supplier_name,
            "Hon Hai Precision Industry Co., Ltd.",
        )

    def test_apple_pegatron_verifies_as_corporation(self):
        evidence = (
            "Pegatron manufactures and assembles Apple devices as an OEM and "
            "contract manufacturing partner."
        )
        state = AgentState(target_company="Apple")
        state.company = CompanyInfo(name="Apple")
        state.suppliers = [supplier("Pegatron", evidence)]
        state.relationship_results = [relationship("Apple", "Pegatron", evidence)]

        state = verification_agent(state)

        self.assertTrue(state.verification_results[0].verified)
        self.assertEqual(
            state.verification_results[0].supplier_name,
            "Pegatron Corporation",
        )

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_apple_rejects_contract_as_supplier(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Contract",
                "location": "Unknown",
                "products": ["Manufacturing"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {"snippet": "Contract supplies manufacturing services to Apple."}
                ],
            }
        ]

        state = AgentState(target_company="Apple")
        state.company = CompanyInfo(name="Apple")
        state.mapping_queue = ["Apple"]
        state.seen_companies = ["Apple Inc."]

        state = supplier_agent(state)

        self.assertEqual(state.suppliers, [])

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_apple_does_not_retain_geely_under_hon_hai_without_supplier_evidence(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Geely Holding Group",
                "location": "China",
                "products": ["Vehicles"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": (
                            "Geely Holding Group and Hon Hai Technology Group formed "
                            "a joint venture for EV manufacturing."
                        )
                    }
                ],
            }
        ]

        state = AgentState(target_company="Apple", max_depth=2)
        state.company = CompanyInfo(name="Apple")
        state.suppliers = [
            SupplierInfo(
                name="Hon Hai Precision Industry",
                canonical_name="Hon Hai Precision Industry Co., Ltd.",
                location="Taiwan",
                products=["Assembly"],
                tier=1,
                parent_company="Apple",
                relationship_path=["Apple", "Hon Hai Precision Industry Co., Ltd."],
                discovery_confidence=0.95,
                propagated_confidence=0.95,
            )
        ]
        state.mapping_queue = ["Hon Hai Precision Industry Co., Ltd."]
        state.seen_companies = ["Apple Inc.", "Hon Hai Precision Industry Co., Ltd."]

        state = supplier_agent(state)

        self.assertNotIn(
            "Geely Holding Group",
            {supplier.name for supplier in state.suppliers},
        )

    def test_qualcomm_query_patterns_and_foundry_discovery(self):
        queries = discovery_queries("Qualcomm")
        self.assertIn("Qualcomm foundry supplier", queries)
        self.assertIn("Qualcomm chip manufacturing partner", queries)
        self.assertIn("Qualcomm semiconductor supply chain", queries)
        self.assertIn("Qualcomm TSMC Samsung foundry", queries)
        self.assertIn("Qualcomm packaging supplier ASE Amkor", queries)
        self.assertIn("Qualcomm outsourced semiconductor assembly and test", queries)

        suppliers, _queries = self.run_discovery(
            "Qualcomm",
            search_results={
                "Qualcomm foundry supplier": [
                    {
                        "title": "TSMC",
                        "snippet": (
                            "TSMC serves as the main supplier for Nvidia, Apple, "
                            "Broadcom, and Qualcomm."
                        ),
                    }
                ]
            },
        )

        names = {supplier["name"] for supplier in suppliers}
        self.assertTrue({"TSMC", "Samsung"} & names)

    def test_qualcomm_incorporated_uses_qualcomm_specific_patterns(self):
        queries = discovery_queries("Qualcomm Incorporated")

        self.assertIn("Qualcomm foundry supplier", queries)
        self.assertIn("Qualcomm TSMC Samsung foundry", queries)
        self.assertIn("Qualcomm packaging supplier ASE Amkor", queries)

    def test_qualcomm_discovery_ignores_stale_empty_cache(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper()
            scraper.cache_dir = cache_dir
            with open(scraper._get_cache_path("Qualcomm"), "w") as cache_file:
                json.dump([], cache_file)

            scraper.session = FakeWikipediaSession(
                {
                    "Qualcomm foundry supplier": [
                        {
                            "title": "TSMC",
                            "snippet": (
                                "TSMC serves as the main supplier for Nvidia, Apple, "
                                "Broadcom, and Qualcomm."
                            ),
                        }
                    ]
                }
            )

            with patch("scraping.supplier_discovery.time.sleep", return_value=None):
                suppliers = scraper.find_suppliers("Qualcomm")

        names = {supplier["name"] for supplier in suppliers}
        self.assertIn("TSMC", names)
        self.assertIn("Qualcomm foundry supplier", scraper.session.seen_queries)
        self.assertEqual(scraper.get_stats()["Cache Used"], 0)

    def test_qualcomm_refresh_cache_bypasses_curated_fast_path(self):
        state = AgentState(target_company="Qualcomm", refresh_supplier_cache=True)
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper(runtime_state=state, prefer_curated=True)
            scraper.cache_dir = cache_dir
            scraper.session = FakeWikipediaSession(
                {
                    "Qualcomm foundry supplier": [
                        {
                            "title": "Samsung Electronics",
                            "snippet": (
                                "Samsung Electronics provides foundry manufacturing "
                                "services for Qualcomm chipsets."
                            ),
                        }
                    ]
                }
            )

            with patch("scraping.supplier_discovery.time.sleep", return_value=None):
                suppliers = scraper.find_suppliers("Qualcomm")

        names = {supplier["name"] for supplier in suppliers}
        self.assertIn("Samsung Electronics", names)
        self.assertIn("Qualcomm foundry supplier", scraper.session.seen_queries)

    def test_qualcomm_returns_verified_tier1_tsmc_when_evidence_exists(self):
        suppliers, _queries = self.run_discovery(
            "Qualcomm",
            search_results={
                "Qualcomm foundry supplier": [
                    {
                        "title": "TSMC",
                        "snippet": (
                            "TSMC serves as the main supplier for Nvidia, Apple, "
                            "Broadcom, and Qualcomm."
                        ),
                    }
                ]
            },
        )
        tsmc = next(supplier for supplier in suppliers if supplier["name"] == "TSMC")
        canonical_name = resolver.resolve(tsmc["name"])

        state = AgentState(target_company="Qualcomm")
        state.company = CompanyInfo(name="Qualcomm")
        state.suppliers = [
            SupplierInfo(
                name=tsmc["name"],
                canonical_name=canonical_name,
                location=tsmc["location"],
                products=tsmc["products"],
                tier=tsmc["tier"],
                parent_company="Qualcomm",
                relationship_path=["Qualcomm", canonical_name],
                discovery_confidence=tsmc["confidence"],
                propagated_confidence=tsmc["confidence"],
                evidence=tsmc["source_evidence"],
            )
        ]
        state.relationship_results = [
            relationship(
                "Qualcomm",
                canonical_name,
                tsmc["source_evidence"][0]["snippet"],
            )
        ]

        state = verification_agent(state)

        verified_tier1_names = {
            result.supplier_name
            for result in state.verification_results
            if result.verified
        }
        self.assertEqual(tsmc["tier"], 1)
        self.assertIn(
            "Taiwan Semiconductor Manufacturing Company",
            verified_tier1_names,
        )

    def test_qualcomm_discovers_packaging_supplier_when_evidence_exists(self):
        suppliers, _queries = self.run_discovery(
            "Qualcomm",
            search_results={
                "Qualcomm packaging supplier ASE Amkor": [
                    {
                        "title": "ASE Technology",
                        "snippet": (
                            "ASE Technology provides outsourced semiconductor "
                            "assembly and test services to Qualcomm."
                        ),
                    }
                ]
            },
        )

        names = {supplier["name"] for supplier in suppliers}
        self.assertIn("ASE Technology", names)

    def test_location_ecosystem_labels_are_rejected_as_suppliers(self):
        for candidate in [
            "Silicon Wadi",
            "Silicon Valley",
            "technology hub",
            "Industrial Park",
            "Economic Zone",
            "Hsinchu Science Park",
        ]:
            valid, reason = validate_supplier_candidate_name(candidate, "Dell")
            self.assertFalse(valid, candidate)
            self.assertTrue(
                "location" in reason or "ecosystem" in reason,
                f"{candidate}: {reason}",
            )

    def test_dell_query_patterns_and_supplier_verification(self):
        queries = discovery_queries("Dell")
        self.assertIn("Dell ODM suppliers", queries)
        self.assertIn("Dell contract manufacturers", queries)
        self.assertIn("Dell laptop manufacturing Compal Quanta Wistron", queries)
        self.assertIn("Dell supply chain suppliers", queries)
        self.assertIn("Dell component suppliers Broadcom Marvell", queries)

        broadcom_evidence = "Broadcom provides chips to Dell."
        compal_evidence = "Compal Electronics manufactures laptops for Dell."
        marvell_evidence = "Marvell Technology Group supplies storage controllers to Dell."
        state = AgentState(target_company="Dell")
        state.company = CompanyInfo(name="Dell")
        state.suppliers = [
            supplier("Broadcom", broadcom_evidence, parent="Dell"),
            supplier("Compal", compal_evidence, parent="Dell"),
            supplier("Marvell Technology Group", marvell_evidence, parent="Dell"),
        ]
        state.relationship_results = [
            relationship("Dell", "Broadcom", broadcom_evidence),
            relationship("Dell", "Compal", compal_evidence),
            relationship("Dell", "Marvell Technology Group", marvell_evidence),
        ]

        state = verification_agent(state)

        results = {result.supplier_name: result for result in state.verification_results}
        self.assertTrue(results["Broadcom Inc."].verified)
        self.assertTrue(results["Compal Electronics"].verified)
        self.assertTrue(results["Marvell Technology, Inc."].verified)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_nvidia_samsung_requires_direct_supplier_evidence(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Samsung",
                "location": "South Korea",
                "products": ["Memory"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {"snippet": "Samsung Electronics is a strategic partner of NVIDIA."}
                ],
            }
        ]

        weak_state = AgentState(target_company="NVIDIA")
        weak_state.company = CompanyInfo(name="NVIDIA")
        weak_state.mapping_queue = ["NVIDIA"]
        weak_state.seen_companies = ["NVIDIA"]

        weak_state = supplier_agent(weak_state)
        self.assertEqual(weak_state.suppliers, [])

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Samsung",
                "location": "South Korea",
                "products": ["Memory"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {
                        "snippet": (
                            "Samsung Electronics supplies memory components to "
                            "NVIDIA for GPU products."
                        )
                    }
                ],
            }
        ]

        direct_state = AgentState(target_company="NVIDIA")
        direct_state.company = CompanyInfo(name="NVIDIA")
        direct_state.mapping_queue = ["NVIDIA"]
        direct_state.seen_companies = ["NVIDIA"]

        direct_state = supplier_agent(direct_state)
        self.assertEqual(len(direct_state.suppliers), 1)
        self.assertEqual(direct_state.suppliers[0].tier, 1)
        self.assertEqual(
            direct_state.suppliers[0].canonical_name,
            "Samsung Electronics",
        )

    def test_alias_duplicates_merge_to_one_canonical_entity(self):
        self.assertEqual(
            resolver.resolve("Hon Hai Technology Group"),
            resolver.resolve("Foxconn"),
        )
        self.assertEqual(
            resolver.resolve("Hon Hai Precision Industry"),
            "Hon Hai Precision Industry Co., Ltd.",
        )


if __name__ == "__main__":
    unittest.main()
