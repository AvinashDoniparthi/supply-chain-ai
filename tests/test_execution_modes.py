import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from agents.relationship_agent import relationship_agent
from agents.executive_report_agent import executive_report_agent
from chains.rag_report_chain import generate_rag_report
from main import build_parser, run_analysis
from models.state import AgentState, CompanyInfo, SupplierInfo, SupplyChainHealth
from retrieval.rag_enrichment import enrich_supplier_evidence_with_rag
from utils.output import render_final_report
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


class TestExecutionModes(unittest.TestCase):
    def test_main_accepts_llm_mode(self):
        args = build_parser().parse_args(["--company", "Dell", "--mode", "llm"])

        self.assertEqual(args.mode, "llm")

    def test_main_accepts_rag_mode(self):
        args = build_parser().parse_args(["--company", "Dell", "--mode", "rag"])

        self.assertEqual(args.mode, "rag")

    def test_main_accepts_slm_mode(self):
        args = build_parser().parse_args(["--company", "Dell", "--mode", "slm"])

        self.assertEqual(args.mode, "slm")

    @patch("main.supply_chain_app.invoke")
    def test_mode_is_propagated_into_workflow_state(self, mock_invoke):
        mock_invoke.side_effect = lambda state: state

        with redirect_stdout(io.StringIO()):
            state = run_analysis("Dell", execution_mode="rag")

        self.assertEqual(state.execution_mode, "rag")
        self.assertEqual(state.run_metadata["mode"], "rag")
        invoked_state = mock_invoke.call_args.args[0]
        self.assertEqual(invoked_state.execution_mode, "rag")
        self.assertIsNone(invoked_state.provider)
        self.assertIsNone(invoked_state.model)

    @patch("main.supply_chain_app.invoke")
    def test_llm_mode_keeps_cloud_provider_selection(self, mock_invoke):
        mock_invoke.side_effect = lambda state: state

        with redirect_stdout(io.StringIO()):
            state = run_analysis("Dell", execution_mode="llm")

        self.assertEqual(state.execution_mode, "llm")
        self.assertIsNone(state.provider)
        self.assertIsNone(state.model)
        invoked_state = mock_invoke.call_args.args[0]
        self.assertIsNone(invoked_state.provider)
        self.assertIsNone(invoked_state.model)

    @patch("main.supply_chain_app.invoke")
    def test_slm_mode_routes_ollama_into_workflow_state(self, mock_invoke):
        mock_invoke.side_effect = lambda state: state

        with redirect_stdout(io.StringIO()):
            state = run_analysis("Dell", execution_mode="slm")

        self.assertEqual(state.execution_mode, "slm")
        self.assertEqual(state.provider, "ollama")
        self.assertEqual(state.model, "gemma3:4b")
        self.assertEqual(state.run_metadata["provider"], "ollama")
        self.assertEqual(state.run_metadata["model"], "gemma3:4b")
        invoked_state = mock_invoke.call_args.args[0]
        self.assertEqual(invoked_state.provider, "ollama")
        self.assertEqual(invoked_state.model, "gemma3:4b")

    def test_final_report_includes_selected_mode(self):
        state = AgentState(target_company="Dell", execution_mode="rag")
        state.company = CompanyInfo(name="Dell")
        state.supply_chain_health = SupplyChainHealth(
            overall_score=80.0,
            status="Good",
            supplier_count=0,
            critical_suppliers=0,
            high_risk_suppliers=0,
            summary="Good.",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            render_final_report(state)

        self.assertIn("Mode: RAG", output.getvalue())

    @patch("chains.rag_report_chain.get_llm")
    @patch("chains.rag_report_chain.retrieve_context")
    def test_rag_report_chain_generates_from_retrieved_context(
        self, mock_retrieve_context, mock_get_llm
    ):
        mock_retrieve_context.side_effect = [
            ["Supply chain health for Dell\nOverall score: 80.0\nStatus: Good"],
            ["Supplier: Broadcom\nTier: 1\nProducts: networking chips"],
            ["Risk for Broadcom\nRisk type: Operational\nSeverity: High"],
            ["Mitigation: Diversify supplier base."],
        ]
        mock_get_llm.return_value = RunnableLambda(
            lambda _: AIMessage(content="Grounded RAG report for Broadcom.")
        )

        report, context = generate_rag_report("Dell")

        self.assertEqual(report, "Grounded RAG report for Broadcom.")
        self.assertEqual(len(context), 4)
        self.assertEqual(mock_retrieve_context.call_count, 4)
        self.assertTrue(
            any(
                "Overall score: 80.0" in chunk
                for chunk in context
            )
        )
        self.assertTrue(
            all(call.kwargs["company"] == "Dell" for call in mock_retrieve_context.call_args_list)
        )
        self.assertTrue(
            any(
                "health overall score status supplier count" in call.kwargs["query"]
                for call in mock_retrieve_context.call_args_list
            )
        )

    @patch("agents.executive_report_agent.generate_rag_report")
    def test_rag_mode_uses_rag_report_for_executive_report(
        self, mock_generate_rag_report
    ):
        mock_generate_rag_report.return_value = (
            "SUPPLY CHAIN HEALTH\nGrounded only in retrieved context.",
            ["Supply chain health for Dell\nStatus: Good"],
        )
        state = AgentState(target_company="Dell", execution_mode="rag")
        state.company = CompanyInfo(name="Dell")
        state.supply_chain_health = SupplyChainHealth(
            overall_score=80.0,
            status="Good",
            supplier_count=0,
            critical_suppliers=0,
            high_risk_suppliers=0,
            summary="Good.",
        )

        state = executive_report_agent(state)

        self.assertEqual(
            state.rag_report,
            "SUPPLY CHAIN HEALTH\nGrounded only in retrieved context.",
        )
        self.assertEqual(state.rag_context, ["Supply chain health for Dell\nStatus: Good"])
        self.assertEqual(state.executive_report.executive_summary, state.rag_report)
        self.assertEqual(state.run_metadata["rag_context_chunks"], 1)
        mock_generate_rag_report.assert_called_once_with("Dell", state=state)

        output = io.StringIO()
        with redirect_stdout(output):
            render_final_report(state)

        rendered_report = output.getvalue()
        self.assertIn("RAG REPORT", rendered_report)
        self.assertIn("Grounded only in retrieved context.", rendered_report)
        self.assertNotIn("2. DISCOVERY QUALITY", rendered_report)

    @patch("chains.rag_report_chain.get_llm")
    @patch("chains.rag_report_chain.retrieve_context")
    def test_rag_report_chain_injects_health_from_state_when_missing_from_retrieval(
        self, mock_retrieve_context, mock_get_llm
    ):
        mock_retrieve_context.side_effect = [
            [],
            ["Supplier: TSMC\nTier: 1\nProducts: semiconductor manufacturing"],
            ["Risk for TSMC\nRisk type: Geopolitical\nSeverity: High"],
            ["Mitigation: Diversify manufacturing footprint."],
        ]
        mock_get_llm.return_value = RunnableLambda(
            lambda _: AIMessage(content="Grounded RAG report with health score.")
        )

        state = AgentState(target_company="Apple")
        state.supply_chain_health = SupplyChainHealth(
            overall_score=72.0,
            status="Moderate",
            supplier_count=1,
            critical_suppliers=1,
            high_risk_suppliers=1,
            summary="Apple depends on TSMC for semiconductor manufacturing.",
        )

        report, context = generate_rag_report("Apple", state=state)

        self.assertEqual(report, "Grounded RAG report with health score.")
        self.assertTrue(any("Overall score: 72.0" in chunk for chunk in context))
        self.assertEqual(mock_retrieve_context.call_count, 4)

    @patch("chains.rag_report_chain.get_llm")
    @patch("chains.rag_report_chain.retrieve_context")
    def test_fast_benchmark_skips_rag_llm_generation_when_context_exists(
        self, mock_retrieve_context, mock_get_llm
    ):
        mock_retrieve_context.side_effect = [
            ["Supply chain health for Dell\nOverall score: 80.0\nStatus: Good"],
            ["Supplier: Broadcom\nTier: 1\nProducts: networking chips"],
            ["Risk for Broadcom\nRisk type: Operational\nSeverity: High"],
            ["Mitigation: Diversify supplier base."],
        ]

        state = AgentState(target_company="Dell", benchmark_fast_mode=True)
        state.company = CompanyInfo(name="Dell")
        state.supply_chain_health = SupplyChainHealth(
            overall_score=80.0,
            status="Good",
            supplier_count=0,
            critical_suppliers=0,
            high_risk_suppliers=0,
            summary="Good.",
        )

        report, context = generate_rag_report("Dell", state=state)

        self.assertIn("RAG EXECUTIVE SUMMARY", report)
        self.assertEqual(len(context), 5)
        mock_get_llm.assert_not_called()

    def test_executive_report_includes_llm_mode(self):
        state = AgentState(target_company="Dell", execution_mode="llm")
        state.supply_chain_health = SupplyChainHealth(
            overall_score=80.0,
            status="Good",
            supplier_count=0,
            critical_suppliers=0,
            high_risk_suppliers=0,
            summary="Good.",
        )

        state = executive_report_agent(state)

        self.assertIn("Mode: LLM-only", state.executive_report.executive_summary)
        self.assertEqual(state.history[-1]["mode"], "llm")

    @patch("retrieval.rag_enrichment.search_analysis")
    @patch("retrieval.rag_enrichment.index_analysis")
    def test_rag_mode_attaches_retrieved_supplier_evidence(
        self, mock_index_analysis, mock_search_analysis
    ):
        document = MagicMock()
        document.page_content = "Retrieved evidence: Broadcom supplies networking chips to Dell."
        document.metadata = {"type": "supplier", "name": "Broadcom"}
        mock_search_analysis.return_value = [document]
        state = AgentState(target_company="Dell", execution_mode="rag")
        state.suppliers = [
            SupplierInfo(
                name="Broadcom",
                canonical_name="Broadcom Inc.",
                location="United States",
                products=["Networking chips"],
                tier=1,
                evidence=[
                    {
                        "title": "Discovery",
                        "link": "curated://test",
                        "snippet": "Broadcom provides chips to Dell.",
                    }
                ],
            )
        ]

        state = enrich_supplier_evidence_with_rag(state, "relationship_classification")

        self.assertEqual(mock_index_analysis.call_count, 1)
        self.assertEqual(mock_search_analysis.call_count, 1)
        self.assertTrue(
            any(evidence["link"].startswith("rag://") for evidence in state.suppliers[0].evidence)
        )
        self.assertEqual(state.run_metadata["mode"], "rag")
        self.assertEqual(state.run_metadata["retrieval_chunks_attached"], 1)

    @patch("agents.relationship_agent.enrich_supplier_evidence_with_rag")
    @patch("agents.relationship_agent.get_classifier")
    def test_fast_benchmark_relationship_agent_uses_heuristics(
        self, mock_get_classifier, mock_enrich
    ):
        mock_enrich.side_effect = lambda state, stage: state

        state = AgentState(
            target_company="Apple",
            benchmark_fast_mode=True,
            execution_mode="llm",
        )
        state.suppliers = [
            SupplierInfo(
                name="TSMC",
                canonical_name="TSMC",
                location="Taiwan",
                products=["semiconductor manufacturing"],
                tier=1,
                evidence=[
                    {
                        "title": "Evidence",
                        "link": "curated://test",
                        "snippet": "TSMC supplies chips to Apple.",
                    }
                ],
            )
        ]

        updated_state = relationship_agent(state)

        mock_get_classifier.assert_not_called()
        self.assertEqual(updated_state.stage_statuses["relationship_classification"], "heuristic")
        self.assertEqual(updated_state.relationship_results[0].relationship_type, "supplier")


if __name__ == "__main__":
    unittest.main()
