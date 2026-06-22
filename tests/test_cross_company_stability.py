import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agents.deduplication_agent import deduplication_agent
from agents.risk_agent import risk_agent
from agents.supplier_agent import supplier_agent
from agents.verification_agent import verification_agent
from models.relationship import RelationshipResult
from models.state import AgentState, CompanyInfo, RiskAnalysis, SupplierInfo
from scraping.supplier_discovery import (
    SupplierDiscoveryScraper,
    discovery_queries,
    is_location_or_ecosystem_entity,
    is_product_or_brand_name,
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
        self.assertEqual(
            queries[:6],
            [
                "Qualcomm foundry supplier",
                "Qualcomm chip manufacturing partner",
                "Qualcomm semiconductor supply chain",
                "Qualcomm TSMC Samsung foundry",
                "Qualcomm ASE Amkor packaging supplier",
                "Qualcomm outsourced semiconductor assembly and test",
            ],
        )
        self.assertIn("Qualcomm foundry supplier", queries)
        self.assertIn("Qualcomm chip manufacturing partner", queries)
        self.assertIn("Qualcomm semiconductor supply chain", queries)
        self.assertIn("Qualcomm TSMC Samsung foundry", queries)
        self.assertIn("Qualcomm ASE Amkor packaging supplier", queries)
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
        self.assertIn("Qualcomm ASE Amkor packaging supplier", queries)

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

    def test_qualcomm_current_empty_cache_forces_live_even_with_legacy_cache(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper()
            scraper.cache_dir = cache_dir
            with open(scraper._get_cache_path("Qualcomm"), "w") as cache_file:
                json.dump([], cache_file)
            legacy_cache_path = scraper._get_cache_path("Qualcomm").replace(
                f"_v{scraper.cache_version}.json",
                f"_v{scraper.cache_version - 1}.json",
            )
            with open(legacy_cache_path, "w") as cache_file:
                json.dump(
                    [
                        {
                            "name": "Amkor Technology",
                            "source_evidence": [
                                {
                                    "title": "Amkor Technology",
                                    "link": "https://en.wikipedia.org/wiki/Amkor_Technology",
                                    "snippet": (
                                        "Amkor Technology was recognized as Supplier "
                                        "of the Year by Qualcomm Technologies."
                                    ),
                                }
                            ],
                        }
                    ],
                    cache_file,
                )

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
        self.assertNotIn("Amkor Technology", names)
        self.assertIn("Qualcomm foundry supplier", scraper.session.seen_queries)
        self.assertEqual(scraper.get_stats()["Cache Used"], 0)

    def test_qualcomm_uses_non_empty_legacy_cache_when_current_cache_missing(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper()
            scraper.cache_dir = cache_dir
            legacy_cache_path = scraper._get_cache_path("Qualcomm").replace(
                f"_v{scraper.cache_version}.json",
                f"_v{scraper.cache_version - 1}.json",
            )
            with open(legacy_cache_path, "w") as cache_file:
                json.dump(
                    [
                        {
                            "name": "Amkor Technology",
                            "location": "Unknown (Verified by Research)",
                            "products": ["Semiconductor Packaging/Test"],
                            "tier": 1,
                            "criticality": "High",
                            "confidence": 0.91,
                            "justification": "Direct supplier evidence for Qualcomm",
                            "source_evidence": [
                                {
                                    "title": "Amkor Technology",
                                    "link": "https://en.wikipedia.org/wiki/Amkor_Technology",
                                    "snippet": (
                                        "Amkor Technology was recognized as Supplier "
                                        "of the Year by Qualcomm Technologies."
                                    ),
                                }
                            ],
                        }
                    ],
                    cache_file,
                )
            scraper.session = FakeWikipediaSession()

            suppliers = scraper.find_suppliers("Qualcomm")

        self.assertEqual([supplier["name"] for supplier in suppliers], ["Amkor Technology"])
        self.assertEqual(scraper.session.seen_queries, [])
        self.assertEqual(scraper.get_stats()["Cache Used"], 1)

    def test_qualcomm_cache_only_returns_stale_empty_cache_without_live_queries(self):
        state = AgentState(target_company="Qualcomm", supplier_cache_only=True)
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper(runtime_state=state)
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

        self.assertEqual(suppliers, [])
        self.assertEqual(scraper.session.seen_queries, [])

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
                "Qualcomm ASE Amkor packaging supplier": [
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
            "innovation district",
            "region",
            "cluster",
            "Hsinchu Science Park",
        ]:
            valid, reason = validate_supplier_candidate_name(candidate, "Dell")
            self.assertFalse(valid, candidate)
            self.assertTrue(
                "location" in reason or "ecosystem" in reason,
                f"{candidate}: {reason}",
            )
            self.assertTrue(is_location_or_ecosystem_entity(candidate), candidate)

        for company in ["Broadcom", "Compal Electronics", "Marvell Technology"]:
            valid, reason = validate_supplier_candidate_name(company, "Dell")
            self.assertTrue(valid, f"{company}: {reason}")
            self.assertFalse(is_location_or_ecosystem_entity(company), company)

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
    def test_dell_supplier_output_rejects_silicon_wadi_but_keeps_real_companies(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        dell_suppliers = [
            {
                "name": "Broadcom",
                "location": "United States",
                "products": ["Networking chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.87,
                "source_evidence": [],
            },
            {
                "name": "Compal",
                "location": "Taiwan",
                "products": ["Contract manufacturing"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.87,
                "source_evidence": [],
            },
            {
                "name": "Marvell Technology Group",
                "location": "United States",
                "products": ["Storage controllers"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.94,
                "source_evidence": [],
            },
        ]
        marvell_suppliers = [
            {
                "name": "Silicon Wadi",
                "location": "Israel",
                "products": ["General Components"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.79,
                "source_evidence": [
                    {
                        "title": "Silicon Wadi",
                        "link": "https://en.wikipedia.org/wiki/Silicon_Wadi",
                        "snippet": (
                            "Marvell to acquire LAN-chip supplier Galileo for "
                            "$2.7 billion in stock."
                        ),
                    }
                ],
            }
        ]

        def find_suppliers(company_name):
            if company_name == "Dell":
                return dell_suppliers
            if company_name == "Marvell Technology, Inc.":
                return marvell_suppliers
            return []

        mock_scraper.find_suppliers.side_effect = find_suppliers

        state = AgentState(target_company="Dell")
        state.company = CompanyInfo(name="Dell")
        state.mapping_queue = ["Dell"]
        state.seen_companies = ["Dell Technologies"]
        state.max_depth = 2

        state = supplier_agent(state)
        state = supplier_agent(state)

        supplier_names = {supplier.name for supplier in state.suppliers}
        canonical_names = {supplier.canonical_name for supplier in state.suppliers}
        self.assertNotIn("Silicon Wadi", supplier_names)
        self.assertIn("Broadcom Inc.", canonical_names)
        self.assertIn("Compal Electronics", canonical_names)
        self.assertIn("Marvell Technology, Inc.", canonical_names)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_dell_tier2_rejects_customers_products_and_unsupported_upstream(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        dell_suppliers = [
            {
                "name": "Broadcom",
                "location": "United States",
                "products": ["Networking chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {"snippet": "Broadcom provides networking chips to Dell."}
                ],
            },
            {
                "name": "Compal",
                "location": "Taiwan",
                "products": ["Contract manufacturing"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.94,
                "source_evidence": [
                    {"snippet": "Compal Electronics manufactures laptops for Dell."}
                ],
            },
            {
                "name": "Marvell Technology Group",
                "location": "United States",
                "products": ["Storage controllers"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.93,
                "source_evidence": [
                    {
                        "snippet": (
                            "Marvell Technology Group supplies storage controllers "
                            "to Dell."
                        )
                    }
                ],
            },
        ]
        compal_candidates = [
            {
                "name": "Apple Inc.",
                "location": "United States",
                "products": ["Consumer electronics"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": (
                            "Compal Electronics manufactures laptops for Apple Inc., "
                            "a major customer and brand owner."
                        )
                    }
                ],
            },
            {
                "name": "Dell Inspiron",
                "location": "Unknown",
                "products": ["Laptop line"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": (
                            "The Dell Inspiron product line is manufactured by "
                            "Compal Electronics for Dell."
                        )
                    }
                ],
            },
        ]
        broadcom_candidates = [
            {
                "name": "Semiconductor Manufacturing International Corporation",
                "location": "China",
                "products": ["Foundry services"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [
                    {
                        "snippet": (
                            "Broadcom and Semiconductor Manufacturing International "
                            "Corporation appear in semiconductor foundry partner "
                            "discussions."
                        )
                    }
                ],
            }
        ]

        def find_suppliers(company_name):
            if company_name == "Dell":
                return dell_suppliers
            if company_name == "Broadcom Inc.":
                return broadcom_candidates
            if company_name == "Compal Electronics":
                return compal_candidates
            return []

        mock_scraper.find_suppliers.side_effect = find_suppliers

        state = AgentState(target_company="Dell")
        state.company = CompanyInfo(name="Dell")
        state.mapping_queue = ["Dell"]
        state.seen_companies = ["Dell Technologies"]
        state.max_depth = 2

        for _ in range(4):
            state = supplier_agent(state)

        supplier_names = {supplier.name for supplier in state.suppliers}
        canonical_names = {supplier.canonical_name for supplier in state.suppliers}

        self.assertNotIn("Apple Inc.", canonical_names)
        self.assertNotIn("Dell Inspiron", supplier_names)
        self.assertNotIn(
            "Semiconductor Manufacturing International Corporation", supplier_names
        )
        self.assertIn("Broadcom Inc.", canonical_names)
        self.assertIn("Compal Electronics", canonical_names)
        self.assertIn("Marvell Technology, Inc.", canonical_names)

    def test_dell_product_or_brand_names_are_rejected(self):
        for candidate in [
            "Dell Inspiron",
            "Dell XPS",
            "ThinkPad",
            "MacBook",
            "iPhone",
            "iPad",
        ]:
            self.assertTrue(is_product_or_brand_name(candidate), candidate)
            valid, reason = validate_supplier_candidate_name(candidate, "Dell")
            self.assertFalse(valid, candidate)
            self.assertIn("product or brand", reason)

    @patch("agents.risk_agent.FinancialRiskProvider.assess_risk", return_value=[])
    @patch("agents.risk_agent.NewsRiskProvider.assess_risk", return_value=[])
    @patch("agents.risk_agent.GeopoliticalRiskProvider.assess_risk")
    def test_dell_risks_ignore_rejected_apple_entity(
        self, mock_geo_risk, _mock_news_risk, _mock_financial_risk
    ):
        mock_geo_risk.return_value = [
            RiskAnalysis(
                supplier_name="Apple Inc.",
                risk_type="Geopolitical",
                severity="High",
                confidence=0.9,
                reasoning="Apple-related risk should not propagate to Dell.",
            ),
            RiskAnalysis(
                supplier_name="Broadcom",
                risk_type="Geopolitical",
                severity="Medium",
                confidence=0.8,
                reasoning="Retained Broadcom supplier risk.",
            ),
        ]
        state = AgentState(target_company="Dell")
        state.company = CompanyInfo(name="Dell")
        state.suppliers = [
            SupplierInfo(
                name="Broadcom",
                canonical_name="Broadcom Inc.",
                location="United States",
                products=["Networking chips"],
            )
        ]

        state = risk_agent(state)

        risk_text = "\n".join(
            f"{risk.supplier_name} {risk.reasoning}"
            for risk in state.risk_assessments
        )
        self.assertNotIn("Apple", risk_text)
        self.assertIn("Broadcom", risk_text)

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
