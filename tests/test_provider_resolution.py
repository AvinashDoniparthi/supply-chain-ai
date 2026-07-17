import unittest
from unittest.mock import patch

from providers.llm_provider import (
    get_llm,
    provider_model_for_execution_mode,
    resolve_provider,
)


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

    def test_llm_execution_mode_does_not_route_to_ollama(self):
        self.assertEqual(provider_model_for_execution_mode("llm"), (None, None))

    def test_rag_execution_mode_does_not_route_to_ollama(self):
        self.assertEqual(provider_model_for_execution_mode("rag"), (None, None))

    def test_slm_execution_mode_routes_to_ollama(self):
        self.assertEqual(
            provider_model_for_execution_mode("slm"),
            ("ollama", "gemma3:4b"),
        )

    def test_slm_provider_alias_resolves_to_ollama_gemma(self):
        config = resolve_provider(provider="slm")
        self.assertEqual(config.provider, "ollama")
        self.assertEqual(config.model, "gemma3:4b")

    @patch("providers.llm_provider.ChatGoogleGenerativeAI")
    def test_gemini_timeout_defaults_and_clamps_to_minimum(
        self, mock_google_llm
    ):
        with patch.dict(
            "os.environ",
            {"GOOGLE_API_KEY": "google-test-key"},
            clear=True,
        ):
            get_llm(provider="google")
            self.assertTrue(mock_google_llm.called)
            self.assertEqual(mock_google_llm.call_args.kwargs["timeout"], 30.0)

            mock_google_llm.reset_mock()
            get_llm(provider="google", timeout=1)
            self.assertTrue(mock_google_llm.called)
            self.assertEqual(mock_google_llm.call_args.kwargs["timeout"], 10.0)
