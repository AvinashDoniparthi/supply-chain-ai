import argparse
import logging

from models.state import AgentState
from utils.output import (
    add_output_args,
    configure_output,
    emit,
    mode_from_args,
    render_final_report,
)
from utils.runtime_controls import finish_all_stages, render_stage_timings
from workflows.supply_chain_workflow import supply_chain_app

logger = logging.getLogger(__name__)


def run_analysis(
    company_name: str,
    *,
    max_depth: int = 2,
    max_candidates_per_company: int = 5,
    timeout_seconds: int = 180,
    skip_risk: bool = False,
    skip_news: bool = False,
    supplier_cache_enabled: bool = True,
    refresh_supplier_cache: bool = False,
    supplier_cache_only: bool = False,
    execution_mode: str = "llm",
):
    """
    Executes the supply chain analysis using the LangGraph workflow.
    """
    emit("=" * 50)
    emit(f"SUPPLY CHAIN ANALYSIS: {company_name}")
    emit("=" * 50)
    emit("")
    emit(f"Company being analyzed: {company_name}")

    # 1. Initialize the shared state
    initial_state = AgentState(
        target_company=company_name,
        current_task=f"Starting analysis for {company_name}",
        max_depth=max_depth,
        max_candidates_per_company=max_candidates_per_company,
        timeout_seconds=timeout_seconds,
        skip_risk=skip_risk,
        skip_news=skip_news,
        supplier_cache_enabled=supplier_cache_enabled,
        refresh_supplier_cache=refresh_supplier_cache,
        supplier_cache_only=supplier_cache_only,
        execution_mode=execution_mode,
        run_metadata={"mode": execution_mode},
    )

    try:
        # 2. Invoke the graph
        # In LangGraph, invoke returns the final state
        final_state_dict = supply_chain_app.invoke(initial_state)

        # If it returns a dict (depending on LangGraph version/config),
        # but since we passed an AgentState (BaseModel), it should return that or something we can convert.
        # Actually, StateGraph(AgentState) will work with the Pydantic model.
        final_state = (
            final_state_dict
            if isinstance(final_state_dict, AgentState)
            else AgentState(**final_state_dict)
        )

        render_final_report(final_state, include_header=False)
        render_stage_timings(final_state)

        return final_state

    except Exception as e:
        logger.exception("Error during graph execution")
        emit(f"Analysis failed: {str(e)}")
        finish_all_stages(initial_state)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supply Chain Intelligence System")
    parser.add_argument("company", nargs="?", default=None)
    parser.add_argument("--company", dest="company_flag", help="Company to analyze.")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum recursive supplier discovery depth. Default: 2.",
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
        "--mode",
        choices=["llm", "rag"],
        default="llm",
        help="Execution mode: llm uses the current pipeline; rag augments evidence with vector retrieval.",
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
