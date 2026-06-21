import tempfile
import unittest
from unittest.mock import patch

from scraping.supplier_discovery import (
    SupplierDiscoveryScraper,
    discovery_queries,
    expected_tier1_suppliers,
)


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


class TestOpenWorldSupplierDiscovery(unittest.TestCase):
    def run_discovery(self, company, search_results=None, extracts=None):
        with tempfile.TemporaryDirectory() as cache_dir:
            scraper = SupplierDiscoveryScraper()
            scraper.cache_dir = cache_dir
            scraper.session = FakeWikipediaSession(search_results, extracts)
            with patch("scraping.supplier_discovery.time.sleep", return_value=None):
                suppliers = scraper.find_suppliers(company)
            return suppliers, scraper.session.seen_queries

    def test_required_fallback_queries_are_configured(self):
        queries = discovery_queries("AMD")

        self.assertIn("AMD foundry suppliers", queries)
        self.assertIn("AMD manufacturing partners", queries)
        self.assertIn("AMD chip packaging suppliers", queries)
        self.assertIn("AMD supply chain", queries)
        self.assertIn("AMD contract manufacturers", queries)

    def test_curated_expected_sets_are_not_discovery_results(self):
        suppliers, _queries = self.run_discovery("Apple")

        self.assertEqual(suppliers, [])

    def test_amd_expected_tier1_regression_suppliers_exist_for_evaluation(self):
        expected = expected_tier1_suppliers("AMD")

        self.assertEqual(
            expected,
            {
                "TSMC",
                "GlobalFoundries",
                "Samsung Electronics",
                "ASE Technology",
                "Amkor Technology",
            },
        )

    def test_amd_discovers_foundry_suppliers_from_open_world_evidence(self):
        suppliers, queries = self.run_discovery(
            "AMD",
            search_results={
                "AMD": [
                    {
                        "title": "AMD",
                        "snippet": "Advanced Micro Devices semiconductor manufacturing profile.",
                    }
                ]
            },
            extracts={
                "AMD": (
                    "Initially manufacturing its own processors, AMD outsourced its "
                    "manufacturing after GlobalFoundries was spun off in 2009. "
                    "AMD has pursued production with other foundries including "
                    "TSMC and Samsung."
                )
            },
        )
        names = {supplier["name"] for supplier in suppliers}

        self.assertTrue({"TSMC", "GlobalFoundries"} & names)
        self.assertIn("AMD contract manufacturers", queries)

    def test_qualcomm_discovers_foundry_supplier_from_title_evidence(self):
        suppliers, _queries = self.run_discovery(
            "Qualcomm",
            search_results={
                "Qualcomm foundry suppliers": [
                    {
                        "title": "TSMC",
                        "snippet": (
                            "As the leading dedicated contract chipmaker, it serves "
                            "as the main supplier for Nvidia, Apple, Broadcom, and "
                            "Qualcomm."
                        ),
                    }
                ]
            },
        )
        names = {supplier["name"] for supplier in suppliers}

        self.assertIn("TSMC", names)

    def test_dell_discovers_manufacturing_odm_supplier(self):
        suppliers, _queries = self.run_discovery(
            "Dell",
            search_results={
                "Dell ODM suppliers": [
                    {
                        "title": "Dell Inspiron laptops",
                        "snippet": (
                            "The Dell Inspiron 3500 is a lightweight laptop "
                            "manufactured by original design manufacturer (ODM) "
                            "Compal for Dell."
                        ),
                    }
                ]
            },
        )
        names = {supplier["name"] for supplier in suppliers}

        self.assertIn("Compal", names)


if __name__ == "__main__":
    unittest.main()
