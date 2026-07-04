import unittest

from api_server import _analysis_kwargs, run_analysis_request
from models.state import AgentState, CompanyInfo


class TestApiServer(unittest.TestCase):
    def test_analysis_kwargs_parse_boolean_strings(self):
        kwargs = _analysis_kwargs(
            {
                "skip_risk": "true",
                "skip_news": "0",
                "supplier_cache_enabled": "false",
                "refresh_supplier_cache": "yes",
                "supplier_cache_only": "off",
            }
        )

        self.assertTrue(kwargs["skip_risk"])
        self.assertFalse(kwargs["skip_news"])
        self.assertFalse(kwargs["supplier_cache_enabled"])
        self.assertTrue(kwargs["refresh_supplier_cache"])
        self.assertFalse(kwargs["supplier_cache_only"])

    def test_run_analysis_request_serializes_state(self):
        state = AgentState(target_company="Dell")
        state.company = CompanyInfo(name="Dell", industry="Computers")

        status_code, response = run_analysis_request(
            {"company": "Dell"},
            runner=lambda company, **kwargs: state,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["company"], "Dell")
        self.assertEqual(response["result"]["target_company"], "Dell")
        self.assertEqual(response["result"]["company"]["name"], "Dell")

    def test_run_analysis_request_requires_company(self):
        status_code, response = run_analysis_request({}, runner=lambda *args, **kwargs: None)

        self.assertEqual(status_code, 400)
        self.assertFalse(response["ok"])
        self.assertIn("company is required", response["error"])


if __name__ == "__main__":
    unittest.main()
