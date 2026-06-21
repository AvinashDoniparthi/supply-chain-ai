import unittest
from unittest.mock import MagicMock, patch
from models.state import AgentState, CompanyInfo
from models.relationship import RelationshipResult
from agents.company_agent import company_agent
from agents.supplier_agent import supplier_agent
from workflows.supply_chain_workflow import create_supply_chain_workflow, tier_router


class TestTierMapping(unittest.TestCase):
    def setUp(self):
        self.state = AgentState(target_company="Apple")

    @patch("agents.company_agent.CompanyScraper")
    def test_company_agent_initializes_queue_and_seen(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.search_company.return_value = {
            "name": "Apple",
            "industry": "Consumer Electronics",
            "headquarters": "Cupertino, CA",
            "description": "Apple Inc.",
            "website": "https://apple.com",
        }

        updated_state = company_agent(self.state)

        self.assertEqual(updated_state.company.name, "Apple")
        self.assertEqual(updated_state.current_depth, 0)
        self.assertEqual(updated_state.mapping_queue, ["Apple"])
        self.assertIn("Apple Inc.", updated_state.seen_companies)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_processes_one_company_per_invocation(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        apple_suppliers = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            },
            {
                "name": "Foxconn",
                "location": "China",
                "products": ["Assembly"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.8,
                "source_evidence": [],
            },
        ]
        tsmc_suppliers = [
            {
                "name": "ASML",
                "location": "Netherlands",
                "products": ["Lithography"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {
                        "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                    }
                ],
            }
        ]

        def side_effect(company_name):
            if company_name == "Apple":
                return apple_suppliers
            if "Taiwan Semiconductor" in company_name:
                return tsmc_suppliers
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]
        self.state.max_depth = 3

        # First invocation should process Apple only
        first_state = supplier_agent(self.state)
        self.assertEqual(len(first_state.suppliers), 2)
        self.assertEqual(
            first_state.mapping_queue,
            [
                "Taiwan Semiconductor Manufacturing Company",
                "Hon Hai Precision Industry Co., Ltd.",
            ],
        )

        # Second invocation should process TSMC and enqueue ASML
        second_state = supplier_agent(first_state)
        self.assertEqual(len(second_state.suppliers), 3)
        self.assertIn("ASML", [s.name for s in second_state.suppliers])
        self.assertEqual(second_state.mapping_queue[-1], "ASML")

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_filters_low_confidence_and_malformed_names(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.7,
                "source_evidence": [],
            },
            {
                "name": "a supplier of Apple",
                "location": "Unknown",
                "products": ["Components"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.85,
                "source_evidence": [],
            },
            {
                "name": "Hon Hai Precision Industry",
                "location": "China",
                "products": ["Assembly"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.85,
                "source_evidence": [],
            },
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)

        self.assertEqual(len(updated_state.suppliers), 1)
        self.assertEqual(updated_state.suppliers[0].name, "Hon Hai Precision Industry")
        self.assertEqual(
            updated_state.mapping_queue,
            ["Hon Hai Precision Industry Co., Ltd."],
        )

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_normalizes_fragments_before_creating_supplier_info(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Micron became a major supplier to Apple Inc",
                "location": "United States",
                "products": ["Memory"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            },
            {
                "name": "International with Magna Electronics Corporation",
                "location": "Canada",
                "products": ["Electronics"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.85,
                "source_evidence": [],
            },
            {
                "name": "Fabless manufacturing",
                "location": "Unknown",
                "products": ["Components"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.9,
                "source_evidence": [],
            },
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in updated_state.suppliers]
        self.assertEqual(supplier_names, ["Micron", "Magna Electronics Corporation"])
        self.assertNotIn("Fabless manufacturing", supplier_names)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_top_k_limits_candidate_suppliers(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": f"Supplier{i}",
                "location": "Unknown",
                "products": ["Component"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.8 + i * 0.01,
                "source_evidence": [],
            }
            for i in range(7)
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)

        self.assertEqual(len(updated_state.suppliers), 5)
        self.assertEqual(len(updated_state.mapping_queue), 5)
        self.assertEqual(
            [s.name for s in updated_state.suppliers],
            [f"Supplier{i}" for i in range(6, 1, -1)],
        )

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_deduplicates_against_seen_and_queue(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            },
            {
                "name": "Taiwan Semiconductor Manufacturing Company",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            },
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)

        self.assertEqual(len(updated_state.suppliers), 1)
        self.assertEqual(
            updated_state.suppliers[0].canonical_name,
            "Taiwan Semiconductor Manufacturing Company",
        )
        self.assertEqual(len(updated_state.mapping_queue), 1)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_respects_queue_size_limit(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "ASML",
                "location": "Netherlands",
                "products": ["Lithography"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            }
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"] + [f"Company{i}" for i in range(50)]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)

        self.assertEqual(len(updated_state.mapping_queue), 50)
        self.assertNotIn("ASML", updated_state.mapping_queue)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_respects_max_depth(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        # Single-level discovery only
        mock_scraper.find_suppliers.return_value = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            }
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]
        self.state.max_depth = 0

        updated_state = supplier_agent(self.state)

        self.assertEqual(len(updated_state.suppliers), 1)
        self.assertEqual(updated_state.mapping_queue, [])

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_supplier_agent_prevents_cycles(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        mock_scraper.find_suppliers.return_value = [
            {
                "name": "Apple",
                "location": "Cupertino",
                "products": ["Software"],
                "tier": 1,
                "criticality": "High",
                "confidence": 1.0,
                "source_evidence": [],
            }
        ]

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        updated_state = supplier_agent(self.state)
        self.assertEqual(len(updated_state.suppliers), 0)
        self.assertEqual(updated_state.mapping_queue, [])

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_three_tier_discovery_and_confidence_propagation(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        apple_suppliers = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            }
        ]
        tsmc_suppliers = [
            {
                "name": "ASML",
                "location": "Netherlands",
                "products": ["Lithography"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {
                        "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                    }
                ],
            }
        ]
        asml_suppliers = [
            {
                "name": "Zeiss",
                "location": "Germany",
                "products": ["Optics"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.85,
                "source_evidence": [
                    {"snippet": "ASML procures precision optics from Zeiss under a supply agreement."},
                    {"snippet": "Zeiss supplies lithography components to ASML."},
                ],
            }
        ]

        def side_effect(company_name):
            if company_name == "Apple":
                return apple_suppliers
            if company_name == "TSMC" or "Taiwan Semiconductor" in company_name:
                return tsmc_suppliers
            if company_name == "ASML":
                return asml_suppliers
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]
        self.state.max_depth = 3

        while self.state.mapping_queue:
            self.state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in self.state.suppliers]
        self.assertEqual(supplier_names, ["TSMC", "ASML", "Zeiss"])

        tsmc = next(s for s in self.state.suppliers if s.name == "TSMC")
        asml = next(s for s in self.state.suppliers if s.name == "ASML")
        zeiss = next(s for s in self.state.suppliers if s.name == "Zeiss")

        self.assertEqual(tsmc.tier, 1)
        self.assertEqual(asml.tier, 2)
        self.assertEqual(zeiss.tier, 3)

        self.assertEqual(tsmc.parent_company, "Apple")
        self.assertEqual(
            asml.parent_company, "Taiwan Semiconductor Manufacturing Company"
        )
        self.assertEqual(zeiss.parent_company, "ASML")

        self.assertEqual(
            tsmc.relationship_path,
            ["Apple", "Taiwan Semiconductor Manufacturing Company"],
        )
        self.assertEqual(
            asml.relationship_path,
            ["Apple", "Taiwan Semiconductor Manufacturing Company", "ASML"],
        )
        self.assertEqual(
            zeiss.relationship_path,
            [
                "Apple",
                "Taiwan Semiconductor Manufacturing Company",
                "ASML",
                "Carl Zeiss SMT",
            ],
        )

        self.assertEqual(tsmc.propagated_confidence, 0.9)
        self.assertEqual(round(asml.propagated_confidence, 2), 0.86)
        self.assertEqual(round(zeiss.propagated_confidence, 2), 0.73)

        discovery_trace = []
        for supplier in self.state.suppliers:
            discovery_trace.extend(
                [
                    f"Company: {supplier.name}",
                    f"Tier: {supplier.tier}",
                    f"Parent: {supplier.parent_company}",
                    f"Relationship Path: {supplier.relationship_path}",
                    f"Propagated Confidence: {supplier.propagated_confidence:.2f}",
                    "---",
                ]
            )
        print("\n".join(discovery_trace))

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_tsmc_tier_two_semiconductor_candidates_survive_weighted_evidence(
        self, mock_scraper_class
    ):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        apple_suppliers = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            }
        ]
        tsmc_suppliers = [
            {
                "name": "GlobalFoundries",
                "location": "USA",
                "products": ["Foundry services"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.88,
                "source_evidence": [
                    {
                        "snippet": (
                            "GlobalFoundries is referenced with TSMC in semiconductor "
                            "ecosystem reporting and foundry manufacturing analysis."
                        )
                    }
                ],
            },
            {
                "name": "United Microelectronics Corporation",
                "location": "Taiwan",
                "products": ["Semiconductors"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.87,
                "source_evidence": [
                    {
                        "snippet": (
                            "United Microelectronics Corporation appears in TSMC "
                            "supply-chain report coverage as a semiconductor "
                            "manufacturing ecosystem company."
                        )
                    }
                ],
            },
        ]

        def side_effect(company_name):
            if company_name == "Apple":
                return apple_suppliers
            if company_name == "TSMC" or "Taiwan Semiconductor" in company_name:
                return tsmc_suppliers
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        while self.state.mapping_queue:
            self.state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in self.state.suppliers]
        self.assertIn("GlobalFoundries", supplier_names)
        self.assertIn("United Microelectronics Corporation", supplier_names)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_max_depth_prevents_tier_3(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        apple_suppliers = [
            {
                "name": "TSMC",
                "location": "Taiwan",
                "products": ["Chips"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.9,
                "source_evidence": [],
            }
        ]
        tsmc_suppliers = [
            {
                "name": "ASML",
                "location": "Netherlands",
                "products": ["Lithography"],
                "tier": 1,
                "criticality": "High",
                "confidence": 0.95,
                "source_evidence": [
                    {
                        "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                    }
                ],
            }
        ]
        asml_suppliers = [
            {
                "name": "Zeiss",
                "location": "Germany",
                "products": ["Optics"],
                "tier": 1,
                "criticality": "Medium",
                "confidence": 0.85,
                "source_evidence": [],
            }
        ]

        def side_effect(company_name):
            if company_name == "Apple":
                return apple_suppliers
            if company_name == "TSMC" or "Taiwan Semiconductor" in company_name:
                return tsmc_suppliers
            if company_name == "ASML":
                return asml_suppliers
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]
        self.state.max_depth = 2

        while self.state.mapping_queue:
            self.state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in self.state.suppliers]
        self.assertEqual(supplier_names, ["TSMC", "ASML"])
        self.assertNotIn("Zeiss", supplier_names)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_cycle_detection_terminates_without_duplicates(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        def side_effect(company_name):
            if company_name == "Apple":
                return [
                    {
                        "name": "TSMC",
                        "location": "Taiwan",
                        "products": ["Chips"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.9,
                        "source_evidence": [],
                    }
                ]
            if company_name == "TSMC":
                return [
                    {
                        "name": "Apple",
                        "location": "Cupertino",
                        "products": ["Software"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.95,
                        "source_evidence": [],
                    }
                ]
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        while self.state.mapping_queue:
            self.state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in self.state.suppliers]
        self.assertEqual(supplier_names, ["TSMC"])
        self.assertEqual(self.state.mapping_queue, [])
        self.assertEqual(self.state.seen_companies.count("Apple Inc."), 1)

    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    def test_shared_dependency_appears_once(self, mock_scraper_class):
        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        def side_effect(company_name):
            if company_name == "Apple":
                return [
                    {
                        "name": "TSMC",
                        "location": "Taiwan",
                        "products": ["Chips"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.9,
                        "source_evidence": [],
                    },
                    {
                        "name": "Samsung",
                        "location": "South Korea",
                        "products": ["Memory"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.85,
                        "source_evidence": [],
                    },
                ]
            if company_name == "TSMC" or "Taiwan Semiconductor" in company_name:
                return [
                    {
                        "name": "ASML",
                        "location": "Netherlands",
                        "products": ["Lithography"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.95,
                        "source_evidence": [
                            {
                                "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                            }
                        ],
                    }
                ]
            if company_name == "Samsung" or company_name == "Samsung Electronics":
                return [
                    {
                        "name": "ASML",
                        "location": "Netherlands",
                        "products": ["Lithography"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.95,
                        "source_evidence": [
                            {
                                "snippet": "ASML supplies EUV lithography systems used by Samsung Electronics for semiconductor manufacturing."
                            }
                        ],
                    }
                ]
            return []

        mock_scraper.find_suppliers.side_effect = side_effect

        self.state.company = CompanyInfo(name="Apple")
        self.state.mapping_queue = ["Apple"]
        self.state.seen_companies = ["Apple Inc."]

        while self.state.mapping_queue:
            self.state = supplier_agent(self.state)

        supplier_names = [supplier.name for supplier in self.state.suppliers]
        self.assertCountEqual(supplier_names, ["TSMC", "Samsung", "ASML"])
        self.assertEqual(supplier_names.count("ASML"), 1)

        asml = next(s for s in self.state.suppliers if s.name == "ASML")
        self.assertEqual(
            asml.relationship_path,
            ["Apple", "Taiwan Semiconductor Manufacturing Company", "ASML"],
        )

    def test_tier_router_decision_logic(self):
        self.state.mapping_queue = ["Apple"]
        self.assertEqual(tier_router(self.state), "continue_discovery")
        self.state.mapping_queue = []
        self.assertEqual(tier_router(self.state), "discovery_complete")

    @patch("agents.company_agent.CompanyScraper")
    @patch("agents.supplier_agent.SupplierDiscoveryScraper")
    @patch("workflows.supply_chain_workflow.deduplication_agent")
    @patch("workflows.supply_chain_workflow.relationship_agent")
    def test_workflow_recursively_invokes_supplier_agent_until_queue_empty(
        self,
        mock_relationship_agent,
        mock_deduplication_agent,
        mock_scraper_class,
        mock_company_scraper_class,
    ):
        mock_company_scraper = MagicMock()
        mock_company_scraper_class.return_value = mock_company_scraper
        mock_company_scraper.search_company.return_value = {
            "name": "Apple",
            "industry": "Consumer Electronics",
            "headquarters": "Cupertino, CA",
            "description": "Apple Inc.",
            "website": "https://apple.com",
        }

        mock_scraper = MagicMock()
        mock_scraper_class.return_value = mock_scraper

        def supplier_side_effect(company_name):
            if company_name == "Apple":
                return [
                    {
                        "name": "TSMC",
                        "location": "Taiwan",
                        "products": ["Chips"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.9,
                        "source_evidence": [],
                    }
                ]
            if "Taiwan Semiconductor" in company_name or company_name == "TSMC":
                return [
                    {
                        "name": "ASML",
                        "location": "Netherlands",
                        "products": ["Lithography"],
                        "tier": 1,
                        "criticality": "High",
                        "confidence": 0.95,
                        "source_evidence": [
                            {
                                "snippet": "ASML supplies EUV lithography systems to TSMC for advanced semiconductor manufacturing."
                            }
                        ],
                    }
                ]
            return []

        mock_scraper.find_suppliers.side_effect = supplier_side_effect

        observed_calls = []

        def fake_relationship(state):
            observed_calls.append("relationship_agent")
            self.assertEqual(state.mapping_queue, [])
            return state

        def fake_deduplication(state):
            return state

        mock_relationship_agent.side_effect = fake_relationship
        mock_deduplication_agent.side_effect = fake_deduplication

        workflow = create_supply_chain_workflow()
        final_state = workflow.invoke(AgentState(target_company="Apple", max_depth=3))

        if not isinstance(final_state, AgentState):
            final_state = AgentState(**final_state)

        self.assertGreaterEqual(mock_scraper.find_suppliers.call_count, 3)
        self.assertEqual(final_state.mapping_queue, [])
        self.assertEqual(observed_calls, ["relationship_agent"])
        self.assertIn(
            "Taiwan Semiconductor Manufacturing Company", final_state.seen_companies
        )
        self.assertIn("ASML", [supplier.name for supplier in final_state.suppliers])


if __name__ == "__main__":
    unittest.main()
