import unittest
from unittest.mock import patch

from providers.llm_provider import resolve_provider, get_llm


class TestProviderResolution(unittest.TestCase):
    def test_google_only_environment_prefers_google(self):
        with patch.dict(
            "os.environ",
            {"GOOGLE_API_KEY": "google-test-key"},
            clear=True,
        ):
            config = resolve_provider()
            self.assertEqual(config.provider, "google")
            self.assertEqual(config.key_source, "GOOGLE_API_KEY")

    def test_openai_only_environment_uses_openai(self):
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "openai-test-key"},
            clear=True,
        ):
            config = resolve_provider()
            self.assertEqual(config.provider, "openai")
            self.assertEqual(config.key_source, "OPENAI_API_KEY")

    def test_both_keys_prefers_google(self):
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_API_KEY": "google-test-key",
                "OPENAI_API_KEY": "openai-test-key",
            },
            clear=True,
        ):
            config = resolve_provider()
            self.assertEqual(config.provider, "google")
            self.assertEqual(config.key_source, "GOOGLE_API_KEY")

    def test_no_keys_raises_clear_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "No valid LLM API key configured"):
                resolve_provider()

    @patch("providers.llm_provider.ChatGoogleGenerativeAI")
    def test_get_llm_uses_google_constructor_when_google_key_exists(
        self, mock_google_llm
    ):
        with patch.dict(
            "os.environ",
            {"GOOGLE_API_KEY": "google-test-key"},
            clear=True,
        ):
            get_llm()
            self.assertTrue(mock_google_llm.called)

