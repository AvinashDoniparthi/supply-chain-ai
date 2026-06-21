import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import email.utils

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.risk_agent import FinancialRiskProvider
from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult

class TestFinancialRiskProvider(unittest.TestCase):
    def setUp(self):
        self.provider = FinancialRiskProvider()
        self.supplier_name = "FinCorp"
        self.state = AgentState(
            target_company="Client",
            suppliers=[
                SupplierInfo(name=self.supplier_name, location="USA"),
                SupplierInfo(name="UnverifiedCorp", location="USA")
            ],
            verification_results=[
                VerificationResult(
                    supplier_name=self.supplier_name,
                    relationship_type="Supplier",
                    verified=True,
                    confidence_score=1.0,
                    reasoning="Verified"
                ),
                VerificationResult(
                    supplier_name="UnverifiedCorp",
                    relationship_type="Supplier",
                    verified=False,
                    confidence_score=0.5,
                    reasoning="Unverified"
                )
            ]
        )

    def create_mock_rss(self, items):
        rss_template = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                {}
            </channel>
        </rss>
        """
        item_template = """
        <item>
            <title>{}</title>
            <link>http://example.com</link>
            <description>{}</description>
            <pubDate>{}</pubDate>
        </item>
        """
        items_xml = "".join([item_template.format(i['title'], i['snippet'], i['pub_date']) for i in items])
        return rss_template.format(items_xml).encode('utf-8')

    @patch('requests.get')
    def test_keyword_detection_critical(self, mock_get):
        recent_date = email.utils.format_datetime(datetime.now())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([{
            "title": "FinCorp files for bankruptcy protection",
            "snippet": "Major financial collapse.",
            "pub_date": recent_date
        }])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].severity, "Critical")
        self.assertIn("bankruptcy", risks[0].reasoning.lower())

    @patch('requests.get')
    def test_keyword_detection_high(self, mock_get):
        recent_date = email.utils.format_datetime(datetime.now())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([{
            "title": "FinCorp announces major layoffs amid revenue collapse",
            "snippet": "Significant workforce reduction.",
            "pub_date": recent_date
        }])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].severity, "High")
        self.assertIn("high supplier-specific financial risk", risks[0].reasoning.lower())

    @patch('requests.get')
    def test_date_filtering_180_days(self, mock_get):
        # 170 days ago (should be included)
        within_date = email.utils.format_datetime(datetime.now() - timedelta(days=170))
        # 190 days ago (should be excluded)
        outside_date = email.utils.format_datetime(datetime.now() - timedelta(days=190))
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([
            {"title": "FinCorp reports recent earnings miss", "snippet": "FinCorp cited declining revenue", "pub_date": within_date},
            {"title": "Old bankruptcy news", "snippet": "bankruptcy", "pub_date": outside_date}
        ])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)
        # Should only have 1 risk from the within_date article
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].severity, "Medium")

    @patch('requests.get')
    def test_verified_supplier_filtering(self, mock_get):
        recent_date = email.utils.format_datetime(datetime.now())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([{
            "title": "UnverifiedCorp default",
            "snippet": "liquidation",
            "pub_date": recent_date
        }])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)
        # UnverifiedCorp should be skipped, FinCorp will have 1 risk if news is found for it.
        # But our mock returns news for "query", which is supplier specific.
        # Actually, our assess_risk iterates through all suppliers and makes requests for each.
        # For UnverifiedCorp, it should NOT make a request.
        # For FinCorp, it makes 6 requests.
        self.assertTrue(mock_get.call_count >= 1)
        # Check that UnverifiedCorp was not analyzed
        analyzed_suppliers = [r.supplier_name for r in risks]
        self.assertNotIn("UnverifiedCorp", analyzed_suppliers)

    @patch('requests.get')
    def test_no_news_scenario(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)
        self.assertEqual(len(risks), 0)

    def test_random_saks_bankruptcy_does_not_create_supplier_risk(self):
        item = {
            "title": "Saks files for bankruptcy protection",
            "snippet": "Analysts mentioned FinCorp once in a market roundup.",
            "pub_date": email.utils.format_datetime(datetime.now()),
        }

        risk, keywords = self.provider._analyze_financial_headline(
            self.state.suppliers[0], item
        )

        self.assertIsNone(risk)
        self.assertEqual(keywords, [])

    def test_random_airline_bankruptcy_does_not_create_supplier_risk(self):
        item = {
            "title": "Spirit Airlines bankruptcy plan approved",
            "snippet": "The airline industry story is unrelated to FinCorp operations.",
            "pub_date": email.utils.format_datetime(datetime.now()),
        }

        risk, keywords = self.provider._analyze_financial_headline(
            self.state.suppliers[0], item
        )

        self.assertIsNone(risk)
        self.assertEqual(keywords, [])

    def test_supplier_bankruptcy_article_creates_critical_risk(self):
        item = {
            "title": "FinCorp files for bankruptcy protection",
            "snippet": "FinCorp filed for bankruptcy after a debt default.",
            "pub_date": email.utils.format_datetime(datetime.now()),
        }

        risk, keywords = self.provider._analyze_financial_headline(
            self.state.suppliers[0], item
        )

        self.assertIsNotNone(risk)
        self.assertEqual(risk.supplier_name, self.supplier_name)
        self.assertEqual(risk.severity, "Critical")
        self.assertIn("bankruptcy", keywords)

if __name__ == '__main__':
    unittest.main()
