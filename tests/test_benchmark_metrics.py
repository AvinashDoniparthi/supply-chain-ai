import time

import pytest

from models.state import AgentState
from utils.benchmark_metrics import build_benchmark_record, record_primary_model_result
from utils.runtime_controls import start_workflow_timer


@pytest.mark.parametrize("mode", ["llm", "rag", "slm"])
def test_completed_modes_emit_total_runtime_and_stage_runtimes(mode):
    state = AgentState(
        target_company="Apple",
        execution_mode=mode,
        provider="ollama" if mode == "slm" else "google",
        model="gemma3:4b" if mode == "slm" else "gemini-2.5-flash",
    )
    start_workflow_timer(state)
    time.sleep(0.002)
    state.stage_durations.update(
        {
            "company_research": 0.001,
            "supplier_discovery": 0.001,
            "verification": 0.001,
            "risk_analysis": 0.001,
            "executive_report_generation": 0.001,
        }
    )
    if mode == "rag":
        state.stage_durations["retrieval"] = 0.001
        state.rag_context = ["retrieved context"]

    record = build_benchmark_record(state, "completed")

    assert record["total_runtime_seconds"] is not None
    assert record["total_runtime_seconds"] >= 0
    assert all(
        value is None or value >= 0 for value in record["stage_runtimes"].values()
    )
    assert all(
        value is None or record["total_runtime_seconds"] >= value
        for value in record["stage_runtimes"].values()
    )
    assert record["retrieved_chunk_count"] == (1 if mode == "rag" else 0)


def test_fallback_assisted_run_still_emits_runtime():
    state = AgentState(target_company="Apple", execution_mode="slm")
    start_workflow_timer(state)
    record_primary_model_result(
        state,
        stage="relationship_classification",
        success=False,
        fallback=True,
        warning="Ollama unavailable",
    )

    record = build_benchmark_record(state, "completed")

    assert record["total_runtime_seconds"] is not None
    assert record["primary_model_success"] is False
    assert record["fallback_used"] is True
    assert record["fallback_stages"] == ["relationship_classification"]


def test_skipped_or_never_entered_stages_use_null_not_zero():
    state = AgentState(target_company="Apple", execution_mode="llm")
    start_workflow_timer(state)
    state.stage_durations["company_research"] = 0.001

    record = build_benchmark_record(state, "completed")

    assert record["stage_runtimes"]["company_research"] == 0.001
    assert record["stage_runtimes"]["risk_analysis"] is None
    assert record["stage_runtimes"]["retrieval"] is None
