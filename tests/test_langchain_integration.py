import unittest
import os
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from providers.llm_provider import get_llm
from prompts.relationship_prompt import relationship_prompt
from prompts.executive_report_prompt import executive_report_prompt
from chains.relationship_chain import get_relationship_chain, RelationshipClassification
from chains.executive_summary_chain import get_executive_summary_chain
from memory.conversation_memory import create_conversation_memory
from retrieval.vector_store import index_analysis
from tools.supply_chain_tools import get_supplier_info, get_risk_info, get_historical_trends
from models.state import AgentState

class TestLangChainIntegration(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "google-test-key",
                "OPENAI_API_KEY": "openai-test-key",
            },
            clear=True,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
    
    def test_provider_factory(self):
        """Verify provider factory works for both openai and gemini."""
        openai_llm = get_llm(provider="openai")
        self.assertIsNotNone(openai_llm)
        
        gemini_llm = get_llm(provider="gemini")
        self.assertIsNotNone(gemini_llm)

    def test_prompt_templates_render(self):
        """Verify prompt templates render correctly with inputs."""
        rendered_rel = relationship_prompt.format_messages(
            target_company="Apple",
            candidate_entity="Foxconn",
            evidence="Foxconn assembles iPhones.",
            format_instructions="Return JSON"
        )
        self.assertTrue(len(rendered_rel) > 0)
        
        rendered_exec = executive_report_prompt.format_messages(
            health_score="80",
            suppliers="Foxconn",
            risks="None"
        )
        self.assertTrue(len(rendered_exec) > 0)

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_relationship_chain_and_parser(self, mock_invoke):
        """Verify relationship chain executes and output parser works."""
        mock_invoke.return_value = AIMessage(
            content='{"relationship": "supplier", "confidence": 0.95, "reasoning": "Assembles iPhones."}'
        )
        
        chain = get_relationship_chain(provider="openai")
        result = chain.invoke({
            "target_company": "Apple",
            "candidate_entity": "Foxconn",
            "evidence": "Foxconn assembles iPhones.",
            "format_instructions": "JSON schema instructions"
        })
        
        self.assertIsInstance(result, RelationshipClassification)
        self.assertEqual(result.relationship, "supplier")
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.reasoning, "Assembles iPhones.")

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_executive_summary_chain(self, mock_invoke):
        """Verify executive summary chain executes successfully."""
        mock_invoke.return_value = AIMessage(
            content="Apple's supply chain is healthy with strong ties to Foxconn."
        )
        
        chain = get_executive_summary_chain(provider="openai")
        result = chain.invoke({
            "health_score": "90/100",
            "suppliers": "Foxconn",
            "risks": "Low risk"
        })
        
        self.assertIn("Apple's supply chain", result)

    def test_conversation_memory(self):
        """Verify conversation memory creation."""
        memory = create_conversation_memory()
        self.assertIsNotNone(memory)
        self.assertEqual(memory.memory_key, "chat_history")

    @patch('langchain_community.vectorstores.Chroma.add_documents')
    @patch('retrieval.vector_store.get_embeddings')
    def test_vector_store_indexing(self, mock_get_embed, mock_add_docs):
        """Verify indexing analysis into vector store."""
        mock_get_embed.return_value = MagicMock()
        state = AgentState(
            target_company="Apple",
            current_task="Test task"
        )
        state.suppliers = []
        state.risk_assessments = []
        
        vector_store = index_analysis(state, provider="openai")
        self.assertIsNotNone(vector_store)

    def test_tools_abstraction(self):
        """Verify supply chain tool definitions."""
        self.assertEqual(get_supplier_info.name, "get_supplier_info")
        self.assertEqual(get_risk_info.name, "get_risk_info")
        self.assertEqual(get_historical_trends.name, "get_historical_trends")

if __name__ == "__main__":
    unittest.main()
