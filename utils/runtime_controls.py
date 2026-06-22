import time
from typing import Any, Optional


STAGE_ORDER = [
    ("company_research", "Company Research"),
    ("supplier_discovery", "Supplier Discovery"),
    ("relationship_classification", "Relationship Classification"),
    ("verification", "Verification"),
    ("risk_analysis", "Risk Analysis"),
    ("report_generation", "Report Generation"),
]

STAGE_TIMEOUT_MESSAGES = {
    "company_research": "Company research exceeded {timeout} seconds. Continuing with available company data.",
    "supplier_discovery": "Supplier discovery exceeded {timeout} seconds. Continuing with discovered suppliers.",
    "relationship_classification": "Relationship classification exceeded {timeout} seconds. Continuing with classified relationships.",
    "verification": "Verification exceeded {timeout} seconds. Continuing with verified suppliers.",
    "risk_analysis": "Risk analysis exceeded {timeout} seconds. Continuing with generated risks.",
    "report_generation": "Report generation exceeded {timeout} seconds. Continuing with partial report.",
}


def _emit(message: str = "") -> None:
    from utils.output import OutputMode, emit

    emit(message, OutputMode.NORMAL)


def _now() -> float:
    return time.monotonic()


def _timeout_value(state: Any) -> int:
    return max(1, int(getattr(state, "timeout_seconds", 180) or 180))


def start_stage(state: Any, stage_key: str) -> None:
    if state is None:
        return
    if stage_key not in state.stage_started_at:
        state.stage_started_at[stage_key] = _now()
    state.active_stage = stage_key


def finish_stage(state: Any, stage_key: str) -> None:
    if state is None:
        return
    started_at = state.stage_started_at.pop(stage_key, None)
    if started_at is not None:
        elapsed = _now() - started_at
        state.stage_durations[stage_key] = (
            state.stage_durations.get(stage_key, 0.0) + elapsed
        )
    if getattr(state, "active_stage", None) == stage_key:
        state.active_stage = None


def finish_all_stages(state: Any) -> None:
    if state is None:
        return
    for stage_key in list(state.stage_started_at.keys()):
        finish_stage(state, stage_key)


def stage_elapsed(state: Any, stage_key: str) -> float:
    if state is None:
        return 0.0
    elapsed = float(state.stage_durations.get(stage_key, 0.0))
    started_at = state.stage_started_at.get(stage_key)
    if started_at is not None:
        elapsed += _now() - started_at
    return elapsed


def stage_timed_out(state: Any, stage_key: str) -> bool:
    return stage_elapsed(state, stage_key) >= _timeout_value(state)


def timeout_stage(state: Any, stage_key: str) -> bool:
    if state is None:
        return True

    if stage_key not in state.timed_out_stages:
        message = STAGE_TIMEOUT_MESSAGES.get(
            stage_key,
            "{stage} exceeded {timeout} seconds. Continuing with partial results.",
        ).format(stage=stage_key.replace("_", " "), timeout=_timeout_value(state))
        _emit(f"[TIMEOUT] {message}")
        state.timed_out_stages.append(stage_key)
        state.history.append(
            {
                "agent": "runtime_controls",
                "action": "stage_timeout",
                "stage": stage_key,
                "elapsed_seconds": round(stage_elapsed(state, stage_key), 2),
                "timeout_seconds": _timeout_value(state),
                "status": "timeout",
            }
        )
    finish_stage(state, stage_key)
    return True


def stop_if_timed_out(state: Any, stage_key: str) -> bool:
    if stage_timed_out(state, stage_key):
        return timeout_stage(state, stage_key)
    return False


def remaining_stage_timeout(
    state: Optional[Any], stage_key: str, default_timeout: float = 10.0
) -> float:
    if state is None:
        return default_timeout
    remaining = _timeout_value(state) - stage_elapsed(state, stage_key)
    if remaining <= 0:
        return 0.0
    return max(1.0, min(float(default_timeout), remaining))


def emit_limit_once(state: Optional[Any], key: str, message: str) -> None:
    if state is not None:
        if key in state.limit_events:
            return
        state.limit_events.append(key)
        state.history.append(
            {
                "agent": "runtime_controls",
                "action": "limit_reached",
                "limit": key,
                "message": message,
                "status": "limited",
            }
        )
    _emit(f"[LIMIT] {message}")


def emit_skip_once(state: Optional[Any], key: str, message: str) -> None:
    if state is not None:
        if key in state.skip_events:
            return
        state.skip_events.append(key)
        state.history.append(
            {
                "agent": "runtime_controls",
                "action": "stage_skipped",
                "skip": key,
                "message": message,
                "status": "skipped",
            }
        )
    _emit(f"[SKIPPED] {message}")


def can_consume_web_query(
    state: Optional[Any], stage_key: str, label: str = "web query"
) -> bool:
    if state is None:
        return True
    start_stage(state, stage_key)
    if stop_if_timed_out(state, stage_key):
        return False

    used = int(state.runtime_counters.get("web_queries", 0))
    max_queries = int(getattr(state, "max_web_queries", 40) or 40)
    if used >= max_queries:
        emit_limit_once(
            state,
            "max_web_queries",
            f"Max web queries reached ({max_queries}). Skipping {label}.",
        )
        return False

    state.runtime_counters["web_queries"] = used + 1
    return True


def can_consume_llm_call(
    state: Optional[Any], stage_key: str, label: str = "LLM call"
) -> bool:
    if state is None:
        return True
    start_stage(state, stage_key)
    if stop_if_timed_out(state, stage_key):
        return False

    used = int(state.runtime_counters.get("llm_calls", 0))
    max_calls = int(getattr(state, "max_llm_calls", 30) or 30)
    if used >= max_calls:
        emit_limit_once(
            state,
            "max_llm_calls",
            f"Max LLM calls reached ({max_calls}). Skipping {label}.",
        )
        return False

    state.runtime_counters["llm_calls"] = used + 1
    return True


def render_stage_timings(state: Any) -> None:
    finish_all_stages(state)
    _emit("")
    for stage_key, label in STAGE_ORDER:
        _emit(f"{label}: {stage_elapsed(state, stage_key):.1f} seconds")
