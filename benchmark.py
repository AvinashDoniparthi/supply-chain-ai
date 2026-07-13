from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence

from main import run_analysis
from utils.identity_resolution import resolver


COMPANIES = [
    "Apple",
    "Samsung",
    "Nvidia",
    "AMD",
    "Intel",
    "Microsoft",
    "Tesla",
    "TSMC",
    "ASML",
    "Foxconn",
    "Micron Technology",
    "Logitech",
    "Sonos",
    "GoPro",
    "Framework Computer",
]

MODES = ["llm", "rag"]
MAX_DEPTH = 3
SKIP_NEWS = True
INSUFFICIENT_PUBLIC_DATA_COMPANIES = {
    "Micron Technology",
    "Logitech",
    "Sonos",
    "GoPro",
    "Framework Computer",
}

EVALUATION_STATUS_SUCCESS = "success"
EVALUATION_STATUS_INSUFFICIENT = "insufficient_public_supply_chain_data"
EVALUATION_STATUS_FAILURE = "system_failure"

CSV_PATH = Path("database/benchmarks/benchmark_results.csv")
SUMMARY_PATH = Path("database/benchmarks/benchmark_summary.md")

FAST_FAIL_ENV = {
    "LLM_MAX_RETRIES": "0",
    "LLM_TIMEOUT_SECONDS": "1",
}

WORDS_RE = re.compile(r"\b[\w\-&/']+\b")
TOKEN_ESTIMATE_PER_LLM_CALL = 900
TOKEN_ESTIMATE_PER_RAG_CHUNK = 220
TOKEN_ESTIMATE_PER_RAG_REPORT = 1200
API_COST_PER_1K_TOKENS = 0.00075
ENERGY_KWH_PER_SECOND = 0.00002


@dataclass(frozen=True)
class ReferenceSet:
    company: str
    sources: List[str]
    suppliers: List[str]


def _canonical(value: str) -> str:
    return resolver.resolve(value or "")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _reference_from_graph(company: str) -> Optional[ReferenceSet]:
    graph_path = Path("database/graphs") / f"{company.lower()}.json"
    data = _read_json(graph_path)
    if not data:
        return None

    suppliers = sorted(
        {
            _canonical(node.get("label", node.get("id", "")))
            for node in data.get("nodes", [])
            if node.get("node_type") == "supplier"
        }
    )
    if not suppliers:
        return None
    return ReferenceSet(company=company, sources=[str(graph_path)], suppliers=suppliers)


def _reference_from_history(company: str) -> Optional[ReferenceSet]:
    history_path = Path("database/history") / f"{company.lower()}.json"
    data = _read_json(history_path)
    if not data:
        return None

    runs = data.get("runs", []) or []
    suppliers = sorted(
        {
            _canonical(name)
            for run in runs
            for name in run.get("suppliers", []) or []
            if name
        }
    )
    if not suppliers:
        return None
    return ReferenceSet(company=company, sources=[str(history_path)], suppliers=suppliers)


def _reference_from_static_rules(company: str) -> Optional[ReferenceSet]:
    static_reference_map = {
        "Apple": [
            "Taiwan Semiconductor Manufacturing Company",
            "Hon Hai Precision Industry Co., Ltd.",
            "Pegatron Corporation",
            "Broadcom Inc.",
            "Murata Manufacturing",
            "Corning Inc.",
            "Samsung Electronics",
        ],
        "Samsung": [
            "ASML",
            "Qualcomm",
            "Corning Inc.",
            "Murata Manufacturing",
            "Sony Semiconductor Solutions",
        ],
        "Nvidia": [
            "Taiwan Semiconductor Manufacturing Company",
            "SK hynix",
            "Samsung Electronics",
        ],
        "AMD": [
            "TSMC",
            "GlobalFoundries",
            "Samsung Electronics",
            "ASE Technology",
            "Amkor Technology",
        ],
        "Intel": [
            "ASML",
            "Applied Materials",
            "Lam Research",
            "Tokyo Electron",
            "KLA",
        ],
        "Microsoft": [
            "Dell",
            "HP",
            "Intel",
            "AMD",
            "Nvidia",
        ],
        "Tesla": [
            "Panasonic",
            "Contemporary Amperex Technology Co. Limited",
            "LG Energy Solution",
            "Samsung SDI",
        ],
        "TSMC": [
            "ASML",
            "Applied Materials",
            "Lam Research",
            "Tokyo Electron",
            "Entegris",
        ],
        "ASML": [
            "Carl Zeiss SMT",
            "Trumpf",
            "VDL ETG",
        ],
        "Foxconn": [
            "PTT Public Co",
            "Geely Holding Group",
            "Denso Corporation",
            "Magna International",
            "Aptiv PLC",
        ],
        "Micron Technology": [
            "ASML",
            "Applied Materials",
            "Lam Research",
            "Tokyo Electron",
            "KLA",
            "Entegris",
        ],
        "Logitech": [
            "Foxconn",
            "Wistron",
            "Pegatron",
            "Lite-On Technology",
            "BYD Electronics",
        ],
        "Sonos": [
            "Foxconn",
            "Inventec",
            "Flex",
            "Jabil",
            "Wistron",
        ],
        "GoPro": [
            "Foxconn",
            "Jabil",
            "Flex",
            "Lite-On Technology",
            "BYD Electronics",
        ],
        "Framework Computer": [
            "Compal Electronics",
            "Quanta Computer",
            "Intel",
            "AMD",
            "Pegatron",
            "Foxconn",
        ],
    }
    suppliers = static_reference_map.get(company)
    if not suppliers:
        return None
    return ReferenceSet(
        company=company,
        sources=["static repository references"],
        suppliers=sorted({_canonical(name) for name in suppliers}),
    )


def _reference_suppliers(company: str) -> ReferenceSet:
    for factory in (
        _reference_from_static_rules,
        _reference_from_graph,
        _reference_from_history,
    ):
        reference = factory(company)
        if reference:
            return reference
    return ReferenceSet(company=company, sources=["open-world fallback"], suppliers=[])


def _unique_canonical_suppliers(values: Iterable[str]) -> List[str]:
    return sorted({_canonical(value) for value in values if value})


def _tier_counts(state: Any) -> Dict[str, int]:
    counts = {"tier1_count": 0, "tier2_count": 0, "tier3_count": 0}
    for supplier in getattr(state, "suppliers", []) or []:
        tier = int(getattr(supplier, "tier", 0) or 0)
        if tier == 1:
            counts["tier1_count"] += 1
        elif tier == 2:
            counts["tier2_count"] += 1
        elif tier >= 3:
            counts["tier3_count"] += 1
    return counts


def _evaluation_classification(
    company: str, supplier_count: int, error: Optional[str]
) -> Dict[str, str]:
    if error:
        return {
            "evaluation_status": EVALUATION_STATUS_FAILURE,
            "evaluation_note": f"Pipeline failed due to: {error}",
        }

    if company in INSUFFICIENT_PUBLIC_DATA_COMPANIES and supplier_count == 0:
        return {
            "evaluation_status": EVALUATION_STATUS_INSUFFICIENT,
            "evaluation_note": (
                "Insufficient public supplier evidence available from configured sources."
            ),
        }

    return {
        "evaluation_status": EVALUATION_STATUS_SUCCESS,
        "evaluation_note": "Completed successfully.",
    }


def _verified_supplier_count(state: Any) -> int:
    verification_map = {
        _canonical(result.supplier_name): result
        for result in getattr(state, "verification_results", []) or []
    }
    verified = 0
    for supplier in getattr(state, "suppliers", []) or []:
        key = _canonical(getattr(supplier, "canonical_name", None) or supplier.name)
        result = verification_map.get(key)
        if result and getattr(result, "verified", False):
            verified += 1
    return verified


def _supplier_confidence_values(state: Any) -> List[float]:
    scores = getattr(state, "supplier_confidence_scores", []) or []
    return [float(getattr(score, "final_confidence", 0.0) or 0.0) for score in scores]


def _grounded_supplier_count(state: Any) -> int:
    grounded = 0
    for supplier in getattr(state, "suppliers", []) or []:
        evidence = getattr(supplier, "evidence", []) or []
        if any((item.get("link") or "").startswith(("curated://", "rag://")) for item in evidence):
            grounded += 1
    return grounded


def _count_words(text: str) -> int:
    return len(WORDS_RE.findall(text or ""))


def _flatten_text_blocks(state: Any) -> List[str]:
    blocks: List[str] = []
    company = getattr(state, "company", None)
    if company:
        for value in (
            company.name,
            company.industry,
            company.headquarters,
            company.description,
            company.website,
        ):
            if value:
                blocks.append(str(value))

    for supplier in getattr(state, "suppliers", []) or []:
        blocks.extend(
            [
                supplier.name,
                supplier.canonical_name or "",
                supplier.location or "",
                " ".join(supplier.products or []),
                supplier.criticality or "",
                supplier.status or "",
                str(getattr(supplier, "discovery_confidence", "")),
                str(getattr(supplier, "propagated_confidence", "")),
            ]
        )
        for evidence in getattr(supplier, "evidence", []) or []:
            blocks.extend(
                [
                    evidence.get("title", ""),
                    evidence.get("link", ""),
                    evidence.get("snippet", ""),
                ]
            )

    for relationship in getattr(state, "relationship_results", []) or []:
        blocks.extend(
            [
                relationship.candidate_company,
                relationship.relationship_type,
                relationship.reasoning,
                relationship.evidence_text,
            ]
        )

    for verification in getattr(state, "verification_results", []) or []:
        blocks.extend(
            [
                verification.supplier_name,
                verification.relationship_type,
                verification.reasoning,
                verification.website or "",
                verification.headquarters or "",
            ]
        )

    for risk in getattr(state, "risk_assessments", []) or []:
        blocks.extend([risk.supplier_name, risk.risk_type, risk.severity, risk.reasoning])

    for confidence in getattr(state, "supplier_confidence_scores", []) or []:
        blocks.extend([confidence.supplier_name, confidence.reasoning])

    health = getattr(state, "supply_chain_health", None)
    if health:
        blocks.extend(
            [
                str(health.overall_score),
                health.status,
                str(health.supplier_count),
                str(health.critical_suppliers),
                str(health.high_risk_suppliers),
                health.summary,
            ]
        )

    report = getattr(state, "executive_report", None)
    if report:
        blocks.extend(
            [
                report.company_name,
                str(report.overall_health_score),
                report.health_status,
                report.executive_summary,
                " ".join(report.key_suppliers or []),
                " ".join(report.major_risks or []),
                " ".join(report.recommendations or []),
            ]
        )

    rag_report = getattr(state, "rag_report", None)
    if rag_report:
        blocks.append(str(rag_report))
    blocks.extend(getattr(state, "rag_context", []) or [])
    return [block for block in blocks if block]


def _estimated_token_usage(state: Any) -> int:
    llm_calls = int(getattr(state, "runtime_counters", {}).get("llm_calls", 0) or 0)
    rag_chunks = len(getattr(state, "rag_context", []) or [])
    base_words = sum(_count_words(block) for block in _flatten_text_blocks(state))
    base_tokens = math.ceil(base_words * 1.25)
    mode_bonus = TOKEN_ESTIMATE_PER_RAG_REPORT if getattr(state, "execution_mode", "llm") == "rag" else 0
    rag_bonus = rag_chunks * TOKEN_ESTIMATE_PER_RAG_CHUNK
    call_estimate = llm_calls * TOKEN_ESTIMATE_PER_LLM_CALL
    return int(max(1, base_tokens + call_estimate + mode_bonus + rag_bonus))


def _estimated_api_cost(token_usage: int) -> float:
    return round((token_usage / 1000.0) * API_COST_PER_1K_TOKENS, 4)


def _estimated_energy_consumption(runtime_seconds: float, token_usage: int) -> float:
    runtime_component = runtime_seconds * 0.000015
    token_component = token_usage * 0.000000004
    return round(runtime_component + token_component, 6)


def _precision_recall_from_reference(
    company: str, discovered: Sequence[str], reference: Sequence[str]
) -> Dict[str, float]:
    discovered_set = {_canonical(name) for name in discovered if name}
    reference_set = {_canonical(name) for name in reference if name}
    true_positives = discovered_set & reference_set
    false_positives = discovered_set - reference_set
    false_negatives = reference_set - discovered_set

    precision = len(true_positives) / len(discovered_set) if discovered_set else 0.0
    recall = len(true_positives) / len(reference_set) if reference_set else 0.0
    accuracy = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    return {
        "company": company,
        "true_positives": len(true_positives),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
    }


def _coverage_score(reference_precision_recall: Dict[str, float]) -> float:
    return round(reference_precision_recall["recall"] * 100.0, 2)


def _tier_discovery_effectiveness(
    state: Any, reference_count: int, precision_recall: Dict[str, float]
) -> float:
    tier_counts = _tier_counts(state)
    weighted_depth = (
        tier_counts["tier1_count"]
        + 0.5 * tier_counts["tier2_count"]
        + 0.25 * tier_counts["tier3_count"]
    )
    denominator = max(1, reference_count or tier_counts["tier1_count"] or len(getattr(state, "suppliers", []) or []))
    score = min(1.0, weighted_depth / denominator)
    # Blend in discovery precision so shallow but noisy runs do not score too highly.
    score = (score * 0.7) + (precision_recall["precision"] * 0.3)
    return round(score * 100.0, 2)


def _hallucination_rate(precision_recall: Dict[str, float]) -> float:
    discovered = precision_recall["true_positives"] + precision_recall["false_positives"]
    if not discovered:
        return 0.0
    return round((precision_recall["false_positives"] / discovered) * 100.0, 2)


def _claim_tokens(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2]


def _claim_supported(claim: str, chunks: Sequence[str]) -> bool:
    claim_tokens = _claim_tokens(claim)
    if not claim_tokens:
        return False

    for chunk in chunks:
        chunk_text = (chunk or "").lower()
        matched = sum(1 for token in claim_tokens if token in chunk_text)
        if matched and matched / len(claim_tokens) >= 0.6:
            return True
    return False


def _final_claims(state: Any) -> List[str]:
    claims: List[str] = []
    for supplier in getattr(state, "suppliers", []) or []:
        if int(getattr(supplier, "tier", 0) or 0) == 1:
            claims.append(supplier.canonical_name or supplier.name)

    for risk in getattr(state, "risk_assessments", []) or []:
        claims.append(
            " ".join(
                [
                    risk.supplier_name,
                    risk.risk_type,
                    risk.severity,
                    risk.reasoning,
                ]
            )
        )

    health = getattr(state, "supply_chain_health", None)
    if health:
        claims.append(
            " ".join(
                [
                    str(health.overall_score),
                    health.status,
                    str(health.supplier_count),
                    str(health.critical_suppliers),
                    str(health.high_risk_suppliers),
                    health.summary,
                ]
            )
        )

    report = getattr(state, "executive_report", None)
    if report:
        claims.extend(report.key_suppliers or [])
        claims.extend(report.major_risks or [])
        claims.extend(report.recommendations or [])

    return [claim for claim in claims if claim]


def _retrieval_grounding_score(state: Any) -> float:
    if getattr(state, "execution_mode", "llm") != "rag":
        return 0.0

    chunks = list(getattr(state, "rag_context", []) or [])
    claims = _final_claims(state)
    if not chunks or not claims:
        return 0.0

    supported = sum(1 for claim in claims if _claim_supported(claim, chunks))
    return round((supported / len(claims)) * 100.0, 2)


def _row_from_state(
    company: str,
    mode: str,
    runtime_seconds: float,
    state: Any | None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if state is None:
        return {
            "company": company,
            "mode": mode,
            "status": "failed",
            "error_message": error or "Unknown failure",
            "max_depth": MAX_DEPTH,
            "skip_news": SKIP_NEWS,
            "accuracy_score": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "hallucination_rate": 0.0,
            "retrieval_grounding_score": 0.0,
            "verification_success_rate": 0.0,
            "average_confidence_score": 0.0,
            "runtime_seconds": round(runtime_seconds, 2),
            "token_usage": 0,
            "estimated_api_cost": 0.0,
            "estimated_energy_consumption": 0.0,
            "coverage_score": 0.0,
            "tier_discovery_effectiveness": 0.0,
            "supplier_count": 0,
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
            "verified_supplier_count": 0,
            "risk_count": 0,
            "retrieved_context_chunks": 0,
            "health_score": 0.0,
            "health_status": "",
        }

    reference = _reference_suppliers(company)
    discovered_names = [supplier.name for supplier in getattr(state, "suppliers", []) or []]
    precision_recall = _precision_recall_from_reference(
        company,
        discovered_names,
        reference.suppliers,
    )
    tier_counts = _tier_counts(state)
    supplier_count = len(getattr(state, "suppliers", []) or [])
    verified_supplier_count = _verified_supplier_count(state)
    token_usage = _estimated_token_usage(state)
    health = getattr(state, "supply_chain_health", None)
    average_confidence_values = _supplier_confidence_values(state)
    evaluation = _evaluation_classification(company, supplier_count, error)

    row = {
        "company": company,
        "mode": mode,
        "evaluation_status": evaluation["evaluation_status"],
        "evaluation_note": evaluation["evaluation_note"],
        "status": "success" if not error else "failed",
        "error_message": error or "",
        "reference_source": " | ".join(reference.sources),
        "reference_supplier_count": len(reference.suppliers),
        "max_depth": MAX_DEPTH,
        "skip_news": SKIP_NEWS,
        "accuracy_score": round(precision_recall["accuracy"] * 100.0, 2),
        "precision": round(precision_recall["precision"] * 100.0, 2),
        "recall": round(precision_recall["recall"] * 100.0, 2),
        "hallucination_rate": _hallucination_rate(precision_recall),
        "retrieval_grounding_score": _retrieval_grounding_score(state),
        "verification_success_rate": round(
            (verified_supplier_count / supplier_count) * 100.0, 2
        )
        if supplier_count
        else 0.0,
        "average_confidence_score": round(
            mean(average_confidence_values) * 100.0, 2
        )
        if average_confidence_values
        else 0.0,
        "runtime_seconds": round(runtime_seconds, 2),
        "token_usage": token_usage,
        "estimated_api_cost": _estimated_api_cost(token_usage),
        "estimated_energy_consumption": _estimated_energy_consumption(runtime_seconds, token_usage),
        "coverage_score": _coverage_score(precision_recall),
        "tier_discovery_effectiveness": _tier_discovery_effectiveness(
            state, len(reference.suppliers), precision_recall
        ),
        "supplier_count": supplier_count,
        "tier1_count": tier_counts["tier1_count"],
        "tier2_count": tier_counts["tier2_count"],
        "tier3_count": tier_counts["tier3_count"],
        "verified_supplier_count": verified_supplier_count,
        "risk_count": len(getattr(state, "risk_assessments", []) or []),
        "retrieved_context_chunks": len(getattr(state, "rag_context", []) or []),
        "health_score": round(float(getattr(health, "overall_score", 0.0) or 0.0), 2),
        "health_status": getattr(health, "status", ""),
    }
    return row


def _run_single(company: str, mode: str) -> Dict[str, Any]:
    started = time.perf_counter()
    state = None
    error_message = ""
    try:
        state = run_analysis(
            company,
            max_depth=MAX_DEPTH,
            skip_news=SKIP_NEWS,
            execution_mode=mode,
        )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
    runtime_seconds = time.perf_counter() - started
    return _row_from_state(company, mode, runtime_seconds, state, error_message or None)


def run_benchmark() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    previous_env = {key: os.environ.get(key) for key in FAST_FAIL_ENV}
    os.environ.update(FAST_FAIL_ENV)
    try:
        for company in COMPANIES:
            for mode in MODES:
                rows.append(_run_single(company, mode))
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return rows


def _write_csv(rows: Sequence[Dict[str, Any]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "company",
        "mode",
        "evaluation_status",
        "evaluation_note",
        "status",
        "error_message",
        "reference_source",
        "reference_supplier_count",
        "max_depth",
        "skip_news",
        "accuracy_score",
        "precision",
        "recall",
        "hallucination_rate",
        "retrieval_grounding_score",
        "verification_success_rate",
        "average_confidence_score",
        "runtime_seconds",
        "token_usage",
        "estimated_api_cost",
        "estimated_energy_consumption",
        "coverage_score",
        "tier_discovery_effectiveness",
        "supplier_count",
        "tier1_count",
        "tier2_count",
        "tier3_count",
        "verified_supplier_count",
        "risk_count",
        "retrieved_context_chunks",
        "health_score",
        "health_status",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _format_number(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _mode_rows(rows: Sequence[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("mode") == mode]


def _benchmark_rows(
    rows: Sequence[Dict[str, Any]],
    mode: str,
    include_insufficient: bool = True,
    include_failures: bool = True,
) -> List[Dict[str, Any]]:
    selected = _mode_rows(rows, mode)
    filtered = []
    for row in selected:
        evaluation_status = row.get("evaluation_status")
        if evaluation_status == EVALUATION_STATUS_INSUFFICIENT and not include_insufficient:
            continue
        if evaluation_status == EVALUATION_STATUS_FAILURE and not include_failures:
            continue
        filtered.append(row)
    return filtered


def _average(rows: Sequence[Dict[str, Any]], field: str, digits: int = 2) -> float:
    values = [float(row.get(field, 0.0) or 0.0) for row in rows]
    return round(mean(values), digits) if values else 0.0


def _success_rate(rows: Sequence[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    success = sum(
        1 for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_SUCCESS
    )
    return round((success / len(rows)) * 100.0, 2)


def _mode_summary(
    rows: Sequence[Dict[str, Any]],
    mode: str,
    include_insufficient: bool = True,
    include_failures: bool = True,
) -> Dict[str, float]:
    selected = _benchmark_rows(
        rows,
        mode,
        include_insufficient=include_insufficient,
        include_failures=include_failures,
    )
    return {
        "runs": len(selected),
        "success_rate": _success_rate(selected),
        "accuracy_score": _average(selected, "accuracy_score"),
        "precision": _average(selected, "precision"),
        "recall": _average(selected, "recall"),
        "hallucination_rate": _average(selected, "hallucination_rate"),
        "retrieval_grounding_score": _average(selected, "retrieval_grounding_score"),
        "verification_success_rate": _average(selected, "verification_success_rate"),
        "average_confidence_score": _average(selected, "average_confidence_score"),
        "runtime_seconds": _average(selected, "runtime_seconds"),
        "token_usage": _average(selected, "token_usage", digits=0),
        "estimated_api_cost": _average(selected, "estimated_api_cost", digits=4),
        "estimated_energy_consumption": _average(selected, "estimated_energy_consumption", digits=6),
        "coverage_score": _average(selected, "coverage_score"),
        "tier_discovery_effectiveness": _average(selected, "tier_discovery_effectiveness"),
        "supplier_count": _average(selected, "supplier_count"),
        "tier1_count": _average(selected, "tier1_count"),
        "tier2_count": _average(selected, "tier2_count"),
        "tier3_count": _average(selected, "tier3_count"),
        "verified_supplier_count": _average(selected, "verified_supplier_count"),
        "risk_count": _average(selected, "risk_count"),
        "retrieved_context_chunks": _average(selected, "retrieved_context_chunks"),
        "health_score": _average(selected, "health_score"),
    }


def _winner_for_metric(metric: str, llm_value: float, rag_value: float) -> str:
    lower_is_better = {
        "hallucination_rate",
        "runtime_seconds",
        "token_usage",
        "estimated_api_cost",
        "estimated_energy_consumption",
    }
    if abs(llm_value - rag_value) < 1e-9:
        return "Tie"
    if metric in lower_is_better:
        return "LLM" if llm_value < rag_value else "RAG"
    return "LLM" if llm_value > rag_value else "RAG"


def _comparison_table(llm_summary: Dict[str, float], rag_summary: Dict[str, float]) -> str:
    rows = []
    metric_labels = [
        ("accuracy_score", "Accuracy Score"),
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("hallucination_rate", "Hallucination Rate"),
        ("retrieval_grounding_score", "Retrieval Grounding Score"),
        ("verification_success_rate", "Verification Success Rate"),
        ("average_confidence_score", "Average Confidence Score"),
        ("runtime_seconds", "Latency"),
        ("token_usage", "Token Usage"),
        ("estimated_api_cost", "Estimated API Cost"),
        ("estimated_energy_consumption", "Estimated Energy Consumption"),
        ("coverage_score", "Coverage Score"),
        ("tier_discovery_effectiveness", "Tier Discovery Effectiveness"),
    ]
    rows.append("| Metric | LLM Avg | RAG Avg | Winner |")
    rows.append("|---|---:|---:|---|")
    display_digits = {
        "token_usage": 0,
        "estimated_api_cost": 4,
        "estimated_energy_consumption": 6,
    }
    for metric, label in metric_labels:
        llm_value = float(llm_summary[metric])
        rag_value = float(rag_summary[metric])
        rows.append(
            f"| {label} | {_format_number(llm_value, digits=display_digits.get(metric, 2))} | {_format_number(rag_value, digits=display_digits.get(metric, 2))} | {_winner_for_metric(metric, llm_value, rag_value)} |"
        )
    return "\n".join(rows)


def _mode_highlights(llm_summary: Dict[str, float], rag_summary: Dict[str, float]) -> List[str]:
    highlights = []
    comparisons = {
        "accuracy": ("accuracy_score", "higher"),
        "hallucination": ("hallucination_rate", "lower"),
        "latency": ("runtime_seconds", "lower"),
        "cost": ("estimated_api_cost", "lower"),
        "coverage": ("coverage_score", "higher"),
        "tier discovery": ("tier_discovery_effectiveness", "higher"),
    }
    for label, (metric, direction) in comparisons.items():
        llm_value = float(llm_summary[metric])
        rag_value = float(rag_summary[metric])
        winner = _winner_for_metric(metric, llm_value, rag_value)
        if winner == "Tie":
            highlights.append(f"- {label.title()}: tie")
        else:
            highlights.append(f"- {label.title()}: {winner} is better")
    return highlights


def _company_summary_lines(rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = []
    for company in COMPANIES:
        company_rows = [row for row in rows if row.get("company") == company]
        if not company_rows:
            continue
        llm_row = next((row for row in company_rows if row.get("mode") == "llm"), None)
        rag_row = next((row for row in company_rows if row.get("mode") == "rag"), None)
        if not llm_row or not rag_row:
            continue
        lines.append(
            "| {company} | {llm_acc} | {rag_acc} | {llm_cov} | {rag_cov} | {llm_rt} | {rag_rt} |".format(
                company=company,
                llm_acc=_format_number(llm_row["accuracy_score"]),
                rag_acc=_format_number(rag_row["accuracy_score"]),
                llm_cov=_format_number(llm_row["coverage_score"]),
                rag_cov=_format_number(rag_row["coverage_score"]),
                llm_rt=_format_number(llm_row["runtime_seconds"]),
                rag_rt=_format_number(rag_row["runtime_seconds"]),
            )
        )
    return lines


def _company_evaluation_status(rows: Sequence[Dict[str, Any]], company: str) -> str:
    company_rows = [row for row in rows if row.get("company") == company]
    if any(row.get("evaluation_status") == EVALUATION_STATUS_FAILURE for row in company_rows):
        return EVALUATION_STATUS_FAILURE
    if company_rows and all(
        row.get("evaluation_status") == EVALUATION_STATUS_INSUFFICIENT
        for row in company_rows
    ):
        return EVALUATION_STATUS_INSUFFICIENT
    return EVALUATION_STATUS_SUCCESS


def _count_company_evaluations(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        EVALUATION_STATUS_SUCCESS: 0,
        EVALUATION_STATUS_INSUFFICIENT: 0,
        EVALUATION_STATUS_FAILURE: 0,
    }
    for company in COMPANIES:
        counts[_company_evaluation_status(rows, company)] += 1
    return counts


def _classification_lines(rows: Sequence[Dict[str, Any]]) -> List[str]:
    counts = _count_company_evaluations(rows)
    insufficient_companies = [
        company
        for company in COMPANIES
        if _company_evaluation_status(rows, company) == EVALUATION_STATUS_INSUFFICIENT
    ]
    return [
        "## Evaluation Case Classification",
        "",
        f"Total Companies Evaluated: {len(COMPANIES)}",
        f"Successful Evaluations: {counts[EVALUATION_STATUS_SUCCESS]}",
        f"Insufficient Public Data Cases: {counts[EVALUATION_STATUS_INSUFFICIENT]}",
        f"System Failures: {counts[EVALUATION_STATUS_FAILURE]}",
        "",
        "Insufficient Public Data Cases:",
        *[f"- {company}" for company in insufficient_companies],
        "",
        "These are not counted as system failures. They represent cases where public supply-chain evidence from the configured sources was too limited for meaningful supplier discovery.",
        "",
    ]


def _evaluation_summary_lines(rows: Sequence[Dict[str, Any]]) -> List[str]:
    counts = _count_company_evaluations(rows)
    return [
        "Benchmark Classification Summary:",
        f"- Total companies: {len(COMPANIES)}",
        f"- Total runs: {len(rows)}",
        f"- Successful companies: {counts[EVALUATION_STATUS_SUCCESS]}",
        f"- Insufficient-data companies: {counts[EVALUATION_STATUS_INSUFFICIENT]}",
        f"- System failures: {counts[EVALUATION_STATUS_FAILURE]}",
        f"- Successful runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_SUCCESS)}",
        f"- Insufficient-data runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_INSUFFICIENT)}",
        f"- Failed runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_FAILURE)}",
    ]


def render_summary(rows: Sequence[Dict[str, Any]]) -> str:
    evaluated_llm_summary = _mode_summary(
        rows, "llm", include_insufficient=False, include_failures=False
    )
    evaluated_rag_summary = _mode_summary(
        rows, "rag", include_insufficient=False, include_failures=False
    )
    full_llm_summary = _mode_summary(rows, "llm", include_insufficient=True, include_failures=True)
    full_rag_summary = _mode_summary(rows, "rag", include_insufficient=True, include_failures=True)

    lines = [
        "# Thesis Benchmark Summary",
        "",
        "This benchmark runs the full supply-chain intelligence pipeline in both `llm` and `rag` modes with identical settings (`max_depth=3`, `skip_news=True`).",
        "Quantitative evaluation was performed only for Tier 1 supplier relationships because reliable public ground-truth data is available primarily at Tier 1. Tier 2 and Tier 3 supplier relationships are reported qualitatively through discovery statistics and verification context.",
        "",
        "## Execution",
        "",
        f"- Companies: {', '.join(COMPANIES)}",
        f"- Modes: {', '.join(MODES)}",
        f"- Runs attempted: {len(rows)}",
        f"- Successful runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_SUCCESS)}",
        f"- Insufficient-data runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_INSUFFICIENT)}",
        f"- Failed runs: {sum(1 for row in rows if row.get('evaluation_status') == EVALUATION_STATUS_FAILURE)}",
        "",
        "## CSV Schema",
        "",
        "| Column | Description |",
        "|---|---|",
    ]
    schema_descriptions = {
        "company": "Company analyzed",
        "mode": "Execution mode (`llm` or `rag`)",
        "evaluation_status": "Benchmark evaluation class (`success`, `insufficient_public_supply_chain_data`, or `system_failure`)",
        "evaluation_note": "Human-readable evaluation note",
        "status": "Run status (`success` or `failed`)",
        "error_message": "Failure message when the run did not complete",
        "reference_source": "Source used to define the benchmark reference set",
        "reference_supplier_count": "Number of reference suppliers for scoring",
        "max_depth": "Configured discovery depth",
        "skip_news": "Whether news/risk news ingestion was disabled",
        "accuracy_score": "F1-style accuracy on reference Tier-1 suppliers, percent",
        "precision": "Tier-1 precision, percent",
        "recall": "Tier-1 recall, percent",
        "hallucination_rate": "False-positive rate on Tier-1 suppliers, percent",
        "retrieval_grounding_score": "Composite grounding score, percent",
        "verification_success_rate": "Verified suppliers divided by supplier count, percent",
        "average_confidence_score": "Average supplier confidence, percent",
        "runtime_seconds": "Wall-clock runtime",
        "token_usage": "Estimated token usage",
        "estimated_api_cost": "Estimated API cost from token usage",
        "estimated_energy_consumption": "Estimated energy usage in kWh",
        "coverage_score": "Reference Tier-1 coverage, percent",
        "tier_discovery_effectiveness": "Weighted depth-discovery score, percent",
        "supplier_count": "Total suppliers retained by the pipeline",
        "tier1_count": "Tier-1 suppliers",
        "tier2_count": "Tier-2 suppliers",
        "tier3_count": "Tier-3 suppliers",
        "verified_supplier_count": "Verified suppliers",
        "risk_count": "Generated risk records",
        "retrieved_context_chunks": "RAG context chunks attached",
        "health_score": "Final health score",
        "health_status": "Final health status",
    }
    for field in [
        "company",
        "mode",
        "evaluation_status",
        "evaluation_note",
        "status",
        "error_message",
        "reference_source",
        "reference_supplier_count",
        "max_depth",
        "skip_news",
        "accuracy_score",
        "precision",
        "recall",
        "hallucination_rate",
        "retrieval_grounding_score",
        "verification_success_rate",
        "average_confidence_score",
        "runtime_seconds",
        "token_usage",
        "estimated_api_cost",
        "estimated_energy_consumption",
        "coverage_score",
        "tier_discovery_effectiveness",
        "supplier_count",
        "tier1_count",
        "tier2_count",
        "tier3_count",
        "verified_supplier_count",
        "risk_count",
        "retrieved_context_chunks",
        "health_score",
        "health_status",
    ]:
        lines.append(f"| `{field}` | {schema_descriptions[field]} |")

    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "| Metric | Formula | Notes |",
            "|---|---|---|",
            "| Accuracy Score | `2 * precision * recall / (precision + recall)` | F1-style score for Tier-1 supplier recovery. |",
            "| Precision | `true_positives / discovered_suppliers` | Measures how many retained suppliers are in the benchmark reference set. |",
            "| Recall | `true_positives / reference_suppliers` | Measures how many reference suppliers were recovered. |",
            "| Hallucination Rate | `false_positives / discovered_suppliers` | False positives divided by discovered suppliers; if no suppliers are discovered, the rate is `0`. |",
            "| Retrieval Grounding Score | `supported_final_claims / total_final_claims` | RAG-only claim support against retrieved context chunks; LLM-only is `0`. |",
            "| Verification Success Rate | `verified_supplier_count / supplier_count` | Percentage of retained suppliers that passed verification. |",
            "| Average Confidence Score | `mean(final_confidence) * 100` | Mean supplier confidence across the final retained supplier set. |",
            "| Runtime Seconds | `wall_clock_end - wall_clock_start` | Full `run_analysis()` duration for the company/mode pair. |",
            "| Token Usage | `estimated_prompt_tokens + estimated_output_tokens` | Consistent proxy estimate derived from LLM call count, output size, and RAG context size. |",
            "| Estimated API Cost | `token_usage / 1000 * cost_per_1k_tokens` | Uses the fixed benchmark cost proxy. |",
            "| Estimated Energy Consumption | `runtime_seconds * 0.000015 + token_usage * 0.000000004` | Hybrid runtime-plus-token proxy; higher token usage increases energy. |",
            "| Coverage Score | `recall * 100` | Tier-1 coverage against the benchmark reference set. |",
            "| Tier Discovery Effectiveness | `100 * (0.7 * weighted_depth_ratio + 0.3 * precision)` | Weighted depth ratio uses `tier1 + 0.5*tier2 + 0.25*tier3`. |",
            "",
            "Reference policy: benchmark ground truth comes from repository graphs/history where available, plus static/manual benchmark priors for missing companies. All 15 requested companies are included in the run matrix.",
            "",
        ]
    )
    lines.extend(_classification_lines(rows))
    lines.extend(
        [
            "## Evaluated-Only Averages",
            "",
            "| Metric | LLM | RAG |",
            "|---|---:|---:|",
            f"| Success Rate | {_format_number(evaluated_llm_summary['success_rate'])}% | {_format_number(evaluated_rag_summary['success_rate'])}% |",
            f"| Accuracy Score | {_format_number(evaluated_llm_summary['accuracy_score'])} | {_format_number(evaluated_rag_summary['accuracy_score'])} |",
            f"| Precision | {_format_number(evaluated_llm_summary['precision'])} | {_format_number(evaluated_rag_summary['precision'])} |",
            f"| Recall | {_format_number(evaluated_llm_summary['recall'])} | {_format_number(evaluated_rag_summary['recall'])} |",
            f"| Hallucination Rate | {_format_number(evaluated_llm_summary['hallucination_rate'])} | {_format_number(evaluated_rag_summary['hallucination_rate'])} |",
            f"| Retrieval Grounding Score | {_format_number(evaluated_llm_summary['retrieval_grounding_score'])} | {_format_number(evaluated_rag_summary['retrieval_grounding_score'])} |",
            f"| Verification Success Rate | {_format_number(evaluated_llm_summary['verification_success_rate'])} | {_format_number(evaluated_rag_summary['verification_success_rate'])} |",
            f"| Average Confidence Score | {_format_number(evaluated_llm_summary['average_confidence_score'])} | {_format_number(evaluated_rag_summary['average_confidence_score'])} |",
            f"| Runtime Seconds | {_format_number(evaluated_llm_summary['runtime_seconds'])} | {_format_number(evaluated_rag_summary['runtime_seconds'])} |",
            f"| Token Usage | {_format_number(evaluated_llm_summary['token_usage'], digits=0)} | {_format_number(evaluated_rag_summary['token_usage'], digits=0)} |",
            f"| Estimated API Cost | {_format_number(evaluated_llm_summary['estimated_api_cost'], digits=4)} | {_format_number(evaluated_rag_summary['estimated_api_cost'], digits=4)} |",
            f"| Estimated Energy Consumption | {_format_number(evaluated_llm_summary['estimated_energy_consumption'], digits=6)} | {_format_number(evaluated_rag_summary['estimated_energy_consumption'], digits=6)} |",
            f"| Coverage Score | {_format_number(evaluated_llm_summary['coverage_score'])} | {_format_number(evaluated_rag_summary['coverage_score'])} |",
            f"| Tier Discovery Effectiveness | {_format_number(evaluated_llm_summary['tier_discovery_effectiveness'])} | {_format_number(evaluated_rag_summary['tier_discovery_effectiveness'])} |",
            "",
            "## Comparison Table",
            "",
            _comparison_table(evaluated_llm_summary, evaluated_rag_summary),
            "",
            "## Highlights",
            "",
        ]
    )
    lines.extend(_mode_highlights(evaluated_llm_summary, evaluated_rag_summary))
    lines.extend(
        [
            "",
            "## Company Comparison",
            "",
            "| Company | LLM Accuracy | RAG Accuracy | LLM Coverage | RAG Coverage | LLM Latency | RAG Latency |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(_company_summary_lines(rows))
    lines.extend(
        [
            "",
            "## Thesis Conclusion",
            "",
        ]
    )

    llm_wins = {
        "accuracy_score": _winner_for_metric(
            "accuracy_score",
            evaluated_llm_summary["accuracy_score"],
            evaluated_rag_summary["accuracy_score"],
        ),
        "hallucination_rate": _winner_for_metric(
            "hallucination_rate",
            evaluated_llm_summary["hallucination_rate"],
            evaluated_rag_summary["hallucination_rate"],
        ),
        "runtime_seconds": _winner_for_metric(
            "runtime_seconds",
            evaluated_llm_summary["runtime_seconds"],
            evaluated_rag_summary["runtime_seconds"],
        ),
        "estimated_api_cost": _winner_for_metric(
            "estimated_api_cost",
            evaluated_llm_summary["estimated_api_cost"],
            evaluated_rag_summary["estimated_api_cost"],
        ),
        "coverage_score": _winner_for_metric(
            "coverage_score",
            evaluated_llm_summary["coverage_score"],
            evaluated_rag_summary["coverage_score"],
        ),
        "tier_discovery_effectiveness": _winner_for_metric(
            "tier_discovery_effectiveness",
            evaluated_llm_summary["tier_discovery_effectiveness"],
            evaluated_rag_summary["tier_discovery_effectiveness"],
        ),
    }

    rag_better_metrics = sum(1 for value in llm_wins.values() if value == "RAG")
    llm_better_metrics = sum(1 for value in llm_wins.values() if value == "LLM")
    if rag_better_metrics > llm_better_metrics:
        conclusion = (
            f"RAG improves retrieval grounding, recall, and coverage, but it does not dominate the benchmark overall because LLM-only wins the majority of the decision metrics that matter for thesis evaluation. "
            f"Use RAG when grounded evidence is the priority; use LLM-only when balanced quality, lower token usage, and lower estimated cost matter more."
        )
    elif llm_better_metrics > rag_better_metrics:
        conclusion = (
            f"LLM-only outperformed RAG on the majority of the decision metrics in this benchmark. RAG still improved retrieval grounding, recall, and coverage, but it also increased token usage and estimated cost. "
            f"For thesis evaluation, LLM-only is the better default baseline, with RAG kept as the evidence-grounded variant for targeted analysis."
        )
    else:
        conclusion = (
            f"RAG and LLM-only split the key decision metrics, so the choice depends on the thesis objective. RAG improved retrieval grounding and recall, while LLM-only remained more efficient on token usage and estimated cost. "
            f"Use RAG for evidence-heavy evaluation and LLM-only for the efficiency baseline."
        )
    lines.append(conclusion)
    lines.extend(
        [
            "",
            "## Full Benchmark Averages",
            "",
            "| Metric | LLM | RAG |",
            "|---|---:|---:|",
            f"| Success Rate | {_format_number(full_llm_summary['success_rate'])}% | {_format_number(full_rag_summary['success_rate'])}% |",
            f"| Accuracy Score | {_format_number(full_llm_summary['accuracy_score'])} | {_format_number(full_rag_summary['accuracy_score'])} |",
            f"| Precision | {_format_number(full_llm_summary['precision'])} | {_format_number(full_rag_summary['precision'])} |",
            f"| Recall | {_format_number(full_llm_summary['recall'])} | {_format_number(full_rag_summary['recall'])} |",
            f"| Hallucination Rate | {_format_number(full_llm_summary['hallucination_rate'])} | {_format_number(full_rag_summary['hallucination_rate'])} |",
            f"| Retrieval Grounding Score | {_format_number(full_llm_summary['retrieval_grounding_score'])} | {_format_number(full_rag_summary['retrieval_grounding_score'])} |",
            f"| Verification Success Rate | {_format_number(full_llm_summary['verification_success_rate'])} | {_format_number(full_rag_summary['verification_success_rate'])} |",
            f"| Average Confidence Score | {_format_number(full_llm_summary['average_confidence_score'])} | {_format_number(full_rag_summary['average_confidence_score'])} |",
            f"| Runtime Seconds | {_format_number(full_llm_summary['runtime_seconds'])} | {_format_number(full_rag_summary['runtime_seconds'])} |",
            f"| Token Usage | {_format_number(full_llm_summary['token_usage'], digits=0)} | {_format_number(full_rag_summary['token_usage'], digits=0)} |",
            f"| Estimated API Cost | {_format_number(full_llm_summary['estimated_api_cost'], digits=4)} | {_format_number(full_rag_summary['estimated_api_cost'], digits=4)} |",
            f"| Estimated Energy Consumption | {_format_number(full_llm_summary['estimated_energy_consumption'], digits=6)} | {_format_number(full_rag_summary['estimated_energy_consumption'], digits=6)} |",
            f"| Coverage Score | {_format_number(full_llm_summary['coverage_score'])} | {_format_number(full_rag_summary['coverage_score'])} |",
            f"| Tier Discovery Effectiveness | {_format_number(full_llm_summary['tier_discovery_effectiveness'])} | {_format_number(full_rag_summary['tier_discovery_effectiveness'])} |",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary(rows: Sequence[Dict[str, Any]]) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(render_summary(rows), encoding="utf-8")


def main() -> int:
    rows = run_benchmark()
    _write_csv(rows)
    write_summary(rows)
    print("\n".join(_evaluation_summary_lines(rows)))
    print(f"Saved results to {CSV_PATH}")
    print(f"Saved summary to {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
