import unittest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import email.utils
from agents.risk_agent import NewsRiskProvider
from models.state import AgentState, SupplierInfo
from models.verification import VerificationResult

class TestNewsRiskProvider(unittest.TestCase):
    def setUp(self):
        self.provider = NewsRiskProvider()
        self.supplier_name = "TestCorp"
        self.state = AgentState(
            target_company="Client",
            suppliers=[SupplierInfo(name=self.supplier_name, location="USA")],
            verification_results=[
                VerificationResult(
                    supplier_name=self.supplier_name,
                    relationship_type="Supplier",
                    verified=True,
                    confidence_score=1.0,
                    reasoning="Test verification"
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
    def test_assess_risk_with_real_news(self, mock_get):
        # Mocking 4 queries (they return the same for simplicity in this test)
        recent_date = email.utils.format_datetime(datetime.now())
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([
            {
                "title": "TestCorp factory explosion causes massive disruption",
                "snippet": "A major explosion occurred at the TestCorp factory.",
                "pub_date": recent_date
            }
        ])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)

        # 4 queries are made, but they are deduplicated by title
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].supplier_name, self.supplier_name)
        self.assertEqual(risks[0].severity, "Critical")
        self.assertIn("explosion", risks[0].reasoning)

    @patch('requests.get')
    def test_filter_out_old_news(self, mock_get):
        old_date = email.utils.format_datetime(datetime.now() - timedelta(days=95))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([
            {
                "title": "Old news about TestCorp strike",
                "snippet": "Old strike happened long ago.",
                "pub_date": old_date
            }
        ])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)

        self.assertEqual(len(risks), 0)

    @patch('requests.get')
    def test_multiple_risk_levels(self, mock_get):
        recent_date = email.utils.format_datetime(datetime.now())
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Return different news for different queries (mocked by returning different results if possible, 
        # but here we just return all in one)
        mock_response.content = self.create_mock_rss([
            {
                "title": "TestCorp strike update",
                "snippet": "Workers are on strike.",
                "pub_date": recent_date
            },
            {
                "title": "TestCorp investigation launched",
                "snippet": "Regulators are investigating.",
                "pub_date": recent_date
            }
        ])
        mock_get.return_value = mock_response

        risks = self.provider.assess_risk(self.state)

        # Expected: 1 High (strike) and 1 Medium (investigation)
        self.assertEqual(len(risks), 2)
        severities = [r.severity for r in risks]
        self.assertIn("High", severities)
        self.assertIn("Medium", severities)

    @patch('requests.get')
    def test_no_news_found_logging(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = self.create_mock_rss([])
        mock_get.return_value = mock_response

        with patch('builtins.print') as mock_print:
            risks = self.provider.assess_risk(self.state)
            self.assertEqual(len(risks), 0)
            mock_print.assert_any_call("No recent risk-related news found")

if __name__ == '__main__':
    unittest.main()
