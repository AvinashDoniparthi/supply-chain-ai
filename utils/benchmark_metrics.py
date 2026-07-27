"""Structured, mode-independent benchmark metrics for one workflow run."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from models.state import AgentState
from utils.output import OutputMode, emit
from utils.runtime_controls import finish_all_stages, finish_workflow_timer
from providers.llm_provider import resolve_provider


BENCHMARK_STAGE_KEYS = {
    "company_research": "company_research",
    "supplier_discovery": "supplier_discovery",
    "verification": "verification",
    "risk_analysis": "risk_analysis",
    "retrieval": "retrieval",
    "executive_report_generation": "executive_report",
}


def record_primary_model_result(
    state: AgentState,
    *,
    stage: str,
    success: bool,
    fallback: bool = False,
    warning: Optional[str] = None,
) -> None:
    metadata = state.run_metadata
    metadata["primary_model_invoked"] = True
    if metadata.get("primary_model_success") is not False:
        metadata["primary_model_success"] = bool(success)
    if fallback:
        metadata["fallback_used"] = True
        stages = metadata.setdefault("fallback_stages", [])
        if stage not in stages:
            stages.append(stage)
    if warning:
        warnings = metadata.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)


def record_warning(state: AgentState, warning: str) -> None:
    if not warning:
        return
    warnings = state.run_metadata.setdefault("warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def _stage_runtime(state: AgentState, key: str) -> Optional[float]:
    if key not in state.stage_durations and key not in state.stage_started_at:
        return None
    return max(0.0, float(state.stage_durations.get(key, 0.0)))


def build_benchmark_record(state: AgentState, workflow_status: str) -> Dict[str, Any]:
    finish_all_stages(state)
    total_runtime = state.run_metadata.get("total_runtime_seconds")
    if total_runtime is None:
        total_runtime = finish_workflow_timer(state)

    verification_confidence = state.confidence_scores.get("verification")
    if verification_confidence is None and state.verification_results:
        verification_confidence = round(
            sum(result.confidence_score for result in state.verification_results)
            / len(state.verification_results),
            2,
        )

    provider = state.provider
    model = state.model
    if provider is None or model is None:
        try:
            config = resolve_provider(provider=provider, model=model)
            provider = config.provider
            model = config.model
        except Exception:
            pass

    discovered = state.discovered_suppliers
    if not discovered and state.discovered_entities:
        discovered = state.discovered_entities
    discovered_names = [
        supplier.canonical_name or supplier.name
        for supplier in (discovered or [])
    ]
    discarded_names = [
        item.get("canonical_name") or item.get("supplier_name")
        for item in state.discarded_suppliers
        if item.get("canonical_name") or item.get("supplier_name")
    ]
    discard_reasons = [
        {
            "supplier": item.get("canonical_name") or item.get("supplier_name"),
            "reason": item.get("reason") or "unspecified",
        }
        for item in state.discarded_suppliers
    ]
    system_failure = workflow_status not in {"completed", "insufficient_public_data"}
    insufficient_public_data = (
        workflow_status == "insufficient_public_data"
        or (
            workflow_status == "completed"
            and not state.suppliers
            and not system_failure
        )
    )

    record = {
        "company": state.target_company or (state.company.name if state.company else None),
        "execution_mode": state.execution_mode,
        "provider": provider,
        "model": model,
        "workflow_status": workflow_status,
        "primary_model_success": state.run_metadata.get("primary_model_success"),
        "fallback_used": bool(state.run_metadata.get("fallback_used", False)),
        "fallback_stages": list(state.run_metadata.get("fallback_stages", [])),
        "suppliers_discovered": len(discovered_names),
        "discovered_supplier_names": discovered_names,
        "suppliers_discarded": len(discarded_names),
        "discarded_supplier_names": discarded_names,
        "discard_reasons": discard_reasons,
        "suppliers_retained": len(state.suppliers),
        "retained_supplier_names": [
            supplier.canonical_name or supplier.name for supplier in state.suppliers
        ],
        "risk_input_count": len(state.suppliers),
        "risks_identified": len(state.risk_assessments),
        "verification_confidence": verification_confidence,
        "retrieved_chunk_count": len(state.rag_context) if state.execution_mode == "rag" else 0,
        "stage_runtimes": {
            name: _stage_runtime(state, key)
            for key, name in BENCHMARK_STAGE_KEYS.items()
        },
        "total_runtime_seconds": total_runtime,
        "errors": list(state.errors),
        "warnings": list(state.run_metadata.get("warnings", [])),
        "insufficient_public_data": insufficient_public_data,
        "system_failure": system_failure,
    }
    state.run_metadata["benchmark_record"] = record
    return record


def emit_benchmark_record(record: Dict[str, Any]) -> None:
    emit(
        "BENCHMARK_RECORD "
        + json.dumps(record, sort_keys=True, separators=(",", ":")),
        OutputMode.QUIET,
    )
