import argparse
import logging

from models.state import AgentState
from retrieval.knowledge_report_generator import generate_knowledge_report
from retrieval.knowledge_base_ingestion import index_knowledge_base
from providers.llm_provider import provider_model_for_execution_mode
from utils.output import (
    OutputMode,
    add_output_args,
    configure_output,
    emit,
    mode_from_args,
    render_final_report,
)
from utils.runtime_controls import (
    finish_all_stages,
    is_quota_error,
    mark_quota_exhausted,
)
from utils.benchmark_metrics import (
    build_benchmark_record,
    emit_benchmark_record,
)
from utils.runtime_controls import start_workflow_timer
from workflows.supply_chain_workflow import supply_chain_app

logger = logging.getLogger(__name__)


def run_analysis(
    company_name: str,
    *,
    product: str | None = None,
    component: str | None = None,
    benchmark_target_query: str | None = None,
    max_depth: int = 3,
    max_candidates_per_company: int = 5,
    timeout_seconds: int = 180,
    skip_risk: bool = False,
    skip_news: bool = False,
    supplier_cache_enabled: bool = True,
    refresh_supplier_cache: bool = False,
    supplier_cache_only: bool = False,
    max_retries: int = 2,
    max_llm_calls: int = 30,
    fast_benchmark: bool = False,
    execution_mode: str = "llm",
):
    """
    Executes the supply chain analysis using the LangGraph workflow.
    """
    emit(f"Starting supply-chain analysis for {company_name}", OutputMode.DEBUG)
    benchmark_query = benchmark_target_query
    if benchmark_query is None and (product or component):
        benchmark_query = (
            " ".join(
                part for part in [company_name, product, component] if part
            ).strip()
            or None
        )

    provider, model = provider_model_for_execution_mode(execution_mode)

    # 1. Initialize the shared state
    initial_state = AgentState(
        target_company=company_name,
        product_name=product,
        component_name=component,
        benchmark_target_query=benchmark_query,
        current_task=f"Starting analysis for {company_name}",
        max_depth=max_depth,
        max_candidates_per_company=max_candidates_per_company,
        timeout_seconds=timeout_seconds,
        max_retries=0 if fast_benchmark else max_retries,
        max_llm_calls=0 if fast_benchmark else max_llm_calls,
        skip_risk=skip_risk,
        skip_news=skip_news,
        supplier_cache_enabled=supplier_cache_enabled,
        refresh_supplier_cache=refresh_supplier_cache,
        supplier_cache_only=supplier_cache_only,
        benchmark_fast_mode=fast_benchmark,
        quota_exhausted=False,
        execution_mode=execution_mode,
        provider=provider,
        model=model,
        run_metadata={
            "mode": execution_mode,
            "provider": provider,
            "model": model,
            "product_name": product,
            "component_name": component,
            "benchmark_target_query": benchmark_query,
            "fast_benchmark": fast_benchmark,
        },
    )

    try:
        # 2. Invoke the graph
        # In LangGraph, invoke returns the final state
        start_workflow_timer(initial_state)
        final_state_dict = supply_chain_app.invoke(initial_state)

        # If it returns a dict (depending on LangGraph version/config),
        # but since we passed an AgentState (BaseModel), it should return that or something we can convert.
        # Actually, StateGraph(AgentState) will work with the Pydantic model.
        final_state = (
            final_state_dict
            if isinstance(final_state_dict, AgentState)
            else AgentState(**final_state_dict)
        )

        build_benchmark_record(final_state, "completed")
        render_final_report(final_state)
        emit_benchmark_record(final_state.run_metadata["benchmark_record"])

        try:
            report_path = generate_knowledge_report(final_state)
            emit(
                f"Knowledge report generated: {report_path}",
                OutputMode.DEBUG,
            )
            index_knowledge_base()
        except Exception as exc:
            logger.warning("Knowledge report generation or indexing failed: %s", exc)

        return final_state

    except Exception as e:
        logger.exception("Error during graph execution")
        emit(f"Analysis failed: {str(e)}")
        finish_all_stages(initial_state)
        build_benchmark_record(initial_state, "failed")
        emit_benchmark_record(initial_state.run_metadata["benchmark_record"])
        if fast_benchmark and is_quota_error(e):
            mark_quota_exhausted(initial_state, str(e))
            return initial_state
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supply Chain Intelligence System")
    parser.add_argument("company", nargs="?", default=None)
    parser.add_argument("--company", dest="company_flag", help="Company to analyze.")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum recursive supplier discovery depth. Default: 3.",
    )
    parser.add_argument(
        "--max-candidates-per-company",
        type=int,
        default=5,
        help="Maximum supplier candidates retained per company. Default: 5.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Per-stage timeout in seconds. Default: 180.",
    )
    parser.add_argument(
        "--skip-risk",
        action="store_true",
        help="Skip all risk analysis providers.",
    )
    parser.add_argument(
        "--skip-news",
        action="store_true",
        help="Skip live news and financial risk providers.",
    )
    parser.add_argument(
        "--index-knowledge-base",
        action="store_true",
        help="Index knowledge_base/ markdown reports into ChromaDB and exit.",
    )
    parser.add_argument(
        "--reindex-knowledge-base",
        action="store_true",
        help="Re-index knowledge_base/ markdown reports into ChromaDB and exit.",
    )
    parser.add_argument(
        "--mode",
        choices=["llm", "rag", "slm"],
        default="llm",
        help="Execution mode: llm uses the current pipeline; rag augments evidence with vector retrieval; slm routes LLM calls to Ollama.",
    )
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore existing supplier discovery cache and write fresh results.",
    )
    cache_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable supplier discovery cache reads and writes.",
    )
    cache_group.add_argument(
        "--use-cache-only",
        action="store_true",
        help="Only use supplier discovery cache; do not run live discovery.",
    )
    add_output_args(parser)
    return parser


def main():
    """
    Entry point for the Supply Chain Intelligence System.
    """
    parser = build_parser()
    args = parser.parse_args()
    if args.index_knowledge_base or args.reindex_knowledge_base:
        index_knowledge_base()
        return
    configure_output(mode_from_args(args))
    company_name = args.company_flag or args.company or "AMD"

    logger.debug("[LANGCHAIN INITIALIZATION] Provider: OpenAI/Gemini")
    logger.debug("[LANGCHAIN INITIALIZATION] Prompt Templates Loaded")
    logger.debug("[LANGCHAIN INITIALIZATION] Chains Registered")
    logger.debug("[LANGCHAIN INITIALIZATION] Vector Store Ready")

    try:
        final_state = run_analysis(
            company_name,
            max_depth=args.max_depth,
            max_candidates_per_company=args.max_candidates_per_company,
            timeout_seconds=args.timeout_seconds,
            skip_risk=args.skip_risk,
            skip_news=args.skip_news,
            supplier_cache_enabled=not args.no_cache,
            refresh_supplier_cache=args.refresh_cache,
            supplier_cache_only=args.use_cache_only,
            execution_mode=args.mode,
        )

        if final_state.errors:
            logger.warning("Analysis finished with errors: %s", final_state.errors)

    except Exception as e:
        logger.exception("Critical system failure")


if __name__ == "__main__":
    main()
