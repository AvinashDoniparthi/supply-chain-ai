from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from utils.identity_resolution import resolver as identity_resolver

EVALUATION_STATUS_SUCCESS = "success"
EVALUATION_STATUS_FAILURE = "system_failure"
EVALUATION_STATUS_INSUFFICIENT_COMPONENT_SUPPLIER_EVIDENCE = (
    "insufficient_component_supplier_evidence"
)
EVALUATION_STATUS_QUOTA_EXHAUSTED = "quota_exhausted"

FAST_FAIL_ENV = {
    "LLM_MAX_RETRIES": "0",
    "LLM_TIMEOUT_SECONDS": "1",
}

REFERENCE_DATASET_PATH = Path("database/benchmarks/product_reference_dataset.csv")
REFERENCE_DATASET_AUDIT_PATH = Path("database/benchmarks/product_reference_dataset_audit.md")
OUTPUT_DIR = Path("database/benchmarks/product_level")
GLOBAL_MASTER_CSV_PATH = OUTPUT_DIR / "all_samples_master_results.csv"

COMPANY_FILE_MAP = {
    "Apple": "apple_product_benchmark.csv",
    "Samsung": "samsung_product_benchmark.csv",
    "NVIDIA": "nvidia_product_benchmark.csv",
    "Nvidia": "nvidia_product_benchmark.csv",
    "AMD": "amd_product_benchmark.csv",
    "Intel": "intel_product_benchmark.csv",
    "Tesla": "tesla_product_benchmark.csv",
}


def get_product_component_map() -> Dict[str, Dict[str, Any]]:
    return {
        "Apple": {
        "product": "iPhone 16 Pro",
        "components": [
            "Application Processor",
            "Display",
            "Camera Sensor",
            "Assembly",
        ],
    },
        "Samsung": {
        "product": "Galaxy S25 Ultra",
        "components": [
            "Application Processor",
            "Display",
            "Camera Sensor",
            "Assembly",
        ],
    },
    "NVIDIA": {
        "product": "GeForce RTX 5090",
        "components": [
            "GPU Die",
            "Memory (GDDR7)",
        ],
    },
    "AMD": {
        "product": "Ryzen 9 9950X",
        "components": [
            "CPU Die",
            "Packaging / Test",
        ],
    },
    "Intel": {
        "product": "Core Ultra 9 285K",
        "components": [
            "CPU Fabrication",
            "Packaging / Test",
        ],
    },
    "Tesla": {
        "product": "Model 3",
        "components": [
            "Battery Cells",
            "Electric Motor",
            "Battery Pack Assembly",
        ],
    },
}


PRODUCT_COMPONENT_MAP = get_product_component_map()
DEFAULT_COMPANIES = list(PRODUCT_COMPONENT_MAP.keys())
# Keep SLM opt-in: it requires a local Ollama service/model, so it should not
# be included in the default benchmark run, but it must be accepted by the CLI.
SUPPORTED_MODES = ["llm", "rag", "slm"]
DEFAULT_MODES = ["llm", "rag"]
DEFAULT_MAX_DEPTH = 3
DEFAULT_SKIP_NEWS = True

CSV_FIELDNAMES = [
    "company",
    "product",
    "component",
    "sample_id",
    "sample_label",
    "timestamp",
    "mode",
    "max_depth",
    "skip_news",
    "provider",
    "model",
    "model_invocation_status",
    "model_invoked",
    "candidate_source",
    "generated_candidate_count",
    "verified_generated_candidate_count",
    "primary_model_success",
    "fallback_used",
    "fallback_stages",
    "workflow_status",
    "warnings",
    "evaluation_status",
    "evaluation_note",
    "tier1_suppliers",
    "tier2_suppliers",
    "tier3_suppliers",
    "tier1_count",
    "tier2_count",
    "tier3_count",
    "supplier_count",
    "verified_supplier_count",
    "risk_count",
    "retrieved_context_chunks",
    "health_score",
    "health_status",
    "precision",
    "recall",
    "f1_score",
    "hallucination_rate",
    "coverage_score",
    "tier2_discovered_suppliers",
    "tier2_verified_suppliers",
    "tier2_verification_status",
    "tier2_confidence",
    "tier2_paths",
    "tier3_discovered_suppliers",
    "tier3_verified_suppliers",
    "tier3_verification_status",
    "tier3_confidence",
    "tier3_paths",
    "retrieval_grounding_score",
    "verification_success_rate",
    "average_confidence_score",
    "runtime_seconds",
    "token_usage",
    "estimated_api_cost",
    "estimated_energy_consumption",
    "errors",
]


def _canonical(value: str) -> str:
    return value.strip().lower()


def _canonical_supplier_name(value: str) -> str:
    return identity_resolver.resolve((value or "").strip())


def _reference_key(value: str) -> str:
    return _canonical_supplier_name(value).strip().lower()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _slugify_company(company: str) -> str:
    return company.lower()


def _split_suppliers(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _estimated_token_usage(state: Any) -> int:
    from benchmark import _estimated_token_usage as benchmark_estimated_token_usage

    return benchmark_estimated_token_usage(state)


def _estimated_api_cost(token_usage: Optional[int]) -> Optional[float]:
    if token_usage is None:
        return None
    return round((token_usage / 1000.0) * 0.00075, 4)


def _estimated_energy_consumption(runtime_seconds: float, token_usage: Optional[int]) -> Optional[float]:
    if token_usage is None:
        return None
    return round((runtime_seconds * 0.000015) + (token_usage * 0.000000004), 6)


def _is_quota_error_text(value: str) -> bool:
    text = (value or "").lower()
    return (
        "429" in text
        or "quota" in text
        or "resourceexhausted" in text
        or "too many requests" in text
    )


def _provenance_fields(state: Any | None) -> Dict[str, Any]:
    """Serialize provenance already captured by run_analysis for one row."""
    if state is None:
        return {
            "provider": "",
            "model": "",
            "model_invocation_status": "skipped_other",
            "model_invoked": False,
            "candidate_source": "",
            "generated_candidate_count": 0,
            "verified_generated_candidate_count": 0,
            "primary_model_success": "",
            "fallback_used": "",
            "fallback_stages": "",
            "workflow_status": "",
            "warnings": "",
        }

    metadata = getattr(state, "run_metadata", {}) or {}
    record = metadata.get("benchmark_record") or {}

    def recorded(name: str, default: Any = "") -> Any:
        if name in record:
            return record[name]
        if name in metadata:
            return metadata[name]
        return default

    primary_model_success = recorded("primary_model_success")
    fallback_used = recorded("fallback_used")
    fallback_stages = recorded("fallback_stages")
    warnings = recorded("warnings")
    return {
        "provider": recorded("provider", getattr(state, "provider", "")),
        "model": recorded("model", getattr(state, "model", "")),
        "model_invocation_status": recorded("model_invocation_status", "skipped_other"),
        "model_invoked": bool(recorded("model_invoked", False)),
        "candidate_source": recorded("candidate_source", ""),
        "generated_candidate_count": int(recorded("generated_candidate_count", 0) or 0),
        "verified_generated_candidate_count": int(
            recorded("verified_generated_candidate_count", 0) or 0
        ),
        "primary_model_success": primary_model_success,
        "fallback_used": fallback_used,
        "fallback_stages": json.dumps(fallback_stages, sort_keys=True)
        if fallback_stages not in (None, "")
        else "",
        "workflow_status": recorded("workflow_status"),
        "warnings": json.dumps(warnings, sort_keys=True)
        if warnings not in (None, "")
        else "",
    }


def _retrieval_grounding_score(state: Any) -> float:
    from benchmark import _retrieval_grounding_score as benchmark_retrieval_grounding_score

    return benchmark_retrieval_grounding_score(state)


def _supplier_confidence_values(state: Any) -> List[float]:
    from benchmark import _supplier_confidence_values as benchmark_supplier_confidence_values

    return benchmark_supplier_confidence_values(state)


def _verified_supplier_count(state: Any) -> int:
    from benchmark import _verified_supplier_count as benchmark_verified_supplier_count

    return benchmark_verified_supplier_count(state)


def _run_analysis(*args: Any, **kwargs: Any) -> Any:
    from main import run_analysis as benchmark_run_analysis

    return benchmark_run_analysis(*args, **kwargs)


def _benchmark_target_query(company: str, product: str, component: str) -> str:
    return " ".join(part for part in [company, product, component] if part).strip()


def _load_reference_dataset() -> List[Dict[str, Any]]:
    if not REFERENCE_DATASET_PATH.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with REFERENCE_DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = {
                key: (row.get(key) or "").strip()
                for key in row.keys()
            }
            company = normalized.get("company", "")
            product = normalized.get("product", "")
            component = normalized.get("component", "")
            tier_raw = normalized.get("tier", "")
            if not company or not product or not component:
                continue
            try:
                tier = int(tier_raw)
            except ValueError:
                continue
            normalized["tier"] = str(tier)
            rows.append(normalized)
    return rows


def _reference_suppliers_for_component(
    reference_rows: Sequence[Dict[str, Any]],
    company: str,
    product: str,
    component: str,
) -> Dict[int, List[str]]:
    tiered: Dict[int, List[str]] = {1: [], 2: [], 3: []}
    for row in reference_rows:
        if (
            row.get("company") != company
            or row.get("product") != product
            or row.get("component") != component
        ):
            continue
        if row.get("verification_status") != "verified":
            continue
        try:
            tier = int(row.get("tier") or 0)
        except ValueError:
            continue
        if tier not in tiered:
            continue
        supplier_name = row.get("canonical_supplier_name") or row.get("reference_supplier") or ""
        if supplier_name:
            tiered[tier].append(supplier_name)
    return tiered


def _reference_supplier_union(tiered_reference: Dict[int, List[str]]) -> List[str]:
    discovered: List[str] = []
    seen = set()
    for tier in (1, 2, 3):
        for supplier in tiered_reference.get(tier, []):
            key = _canonical(supplier)
            if key in seen:
                continue
            seen.add(key)
            discovered.append(supplier)
    return discovered


def _reference_suppliers_by_tier(tiered_reference: Dict[int, List[str]]) -> Dict[int, List[str]]:
    by_tier: Dict[int, List[str]] = {1: [], 2: [], 3: []}
    for tier in (1, 2, 3):
        suppliers = []
        seen = set()
        for supplier in tiered_reference.get(tier, []):
            key = _reference_key(supplier)
            if key in seen:
                continue
            seen.add(key)
            suppliers.append(supplier)
        by_tier[tier] = suppliers
    return by_tier


def _unique_supplier_names(suppliers: Sequence[Any]) -> List[str]:
    names: List[str] = []
    seen = set()
    for supplier in suppliers:
        name = getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")
        name = str(name).strip()
        if not name:
            continue
        key = _canonical(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _unique_canonical_supplier_names(suppliers: Sequence[Any]) -> List[str]:
    names: List[str] = []
    seen = set()
    for supplier in suppliers:
        name = getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")
        name = _canonical_supplier_name(str(name).strip())
        if not name:
            continue
        key = _reference_key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def extract_suppliers_by_tier(state: Any) -> Dict[str, Any]:
    suppliers = list(getattr(state, "suppliers", []) or [])
    if not suppliers:
        return {
            "tier1_suppliers": "",
            "tier2_suppliers": "",
            "tier3_suppliers": "",
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
            "supplier_count": 0,
            "verified_supplier_count": 0,
            "risk_count": 0,
            "retrieved_context_chunks": 0,
            "health_score": None,
            "health_status": "",
            "average_confidence_score": None,
        }

    tier1 = _unique_supplier_names([supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) == 1])
    tier2 = _unique_supplier_names([supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) == 2])
    tier3 = _unique_supplier_names([supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) >= 3])
    verified_count = _verified_supplier_count(state)
    health = getattr(state, "supply_chain_health", None)
    confidence_values = _supplier_confidence_values(state)

    return {
        "tier1_suppliers": "; ".join(tier1),
        "tier2_suppliers": "; ".join(tier2),
        "tier3_suppliers": "; ".join(tier3),
        "tier1_count": len(tier1),
        "tier2_count": len(tier2),
        "tier3_count": len(tier3),
        "supplier_count": len(_unique_supplier_names(suppliers)),
        "verified_supplier_count": verified_count,
        "risk_count": len(getattr(state, "risk_assessments", []) or []),
        "retrieved_context_chunks": len(getattr(state, "rag_context", []) or []),
        "health_score": round(float(getattr(health, "overall_score", 0.0) or 0.0), 2),
        "health_status": getattr(health, "status", ""),
        "average_confidence_score": round(mean(confidence_values) * 100.0, 2) if confidence_values else None,
    }


def _discovered_supplier_set(state: Any) -> List[str]:
    return _unique_supplier_names(getattr(state, "suppliers", []) or [])


def _discovered_supplier_set_by_tier(state: Any) -> Dict[int, List[str]]:
    suppliers = list(getattr(state, "suppliers", []) or [])
    return {
        1: _unique_canonical_supplier_names(
            [supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) == 1]
        ),
        2: _unique_canonical_supplier_names(
            [supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) == 2]
        ),
        3: _unique_canonical_supplier_names(
            [supplier for supplier in suppliers if int(getattr(supplier, "tier", 0) or 0) >= 3]
        ),
    }


def _tier_qualitative_details(state: Any, tier: int) -> Dict[str, Any]:
    suppliers = [
        supplier
        for supplier in getattr(state, "suppliers", []) or []
        if int(getattr(supplier, "tier", 0) or 0) == tier
    ]
    verification_map = {
        _reference_key(getattr(result, "supplier_name", "")): result
        for result in getattr(state, "verification_results", []) or []
    }
    confidence_map = {
        _reference_key(getattr(score, "supplier_name", "")): score
        for score in getattr(state, "supplier_confidence_scores", []) or []
    }

    discovered: List[str] = []
    verified: List[str] = []
    confidence_values: List[float] = []
    paths: List[str] = []

    for supplier in suppliers:
        canonical_name = _canonical_supplier_name(
            str(getattr(supplier, "canonical_name", None) or getattr(supplier, "name", ""))
        )
        discovered.append(canonical_name)
        key = _reference_key(canonical_name)
        verification = verification_map.get(key)
        if verification and getattr(verification, "verified", False):
            verified.append(canonical_name)
        confidence = confidence_map.get(key)
        if confidence is not None:
            confidence_values.append(float(getattr(confidence, "final_confidence", 0.0) or 0.0))
        else:
            confidence_values.append(float(getattr(supplier, "discovery_confidence", 0.0) or 0.0))
        relationship_path = getattr(supplier, "relationship_path", []) or []
        if relationship_path:
            paths.append(" -> ".join(str(part) for part in relationship_path if part))

    verification_status = "not_available"
    if discovered:
        verification_status = "verified" if verified else "unverified"
        if verified and len(verified) < len(discovered):
            verification_status = "partially_verified"

    confidence = (
        round(mean(confidence_values) * 100.0, 2)
        if confidence_values
        else "not_available"
    )

    prefix = f"tier{tier}"
    return {
        f"{prefix}_discovered_suppliers": "; ".join(discovered) if discovered else "not_available",
        f"{prefix}_verified_suppliers": "; ".join(verified) if verified else "not_available",
        f"{prefix}_verification_status": verification_status,
        f"{prefix}_confidence": confidence,
        f"{prefix}_paths": "; ".join(paths) if paths else "not_available",
    }


def _reference_metrics(
    discovered: Sequence[str],
    reference: Sequence[str],
) -> Dict[str, Any]:
    discovered_set = {_reference_key(name) for name in discovered if name}
    reference_set = {_reference_key(name) for name in reference if name}

    if not reference_set:
        return {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "precision": "not_available",
            "recall": "not_available",
            "f1_score": "not_available",
            "hallucination_rate": "not_available",
            "coverage_score": "not_available",
        }

    true_positives = discovered_set & reference_set
    false_positives = discovered_set - reference_set
    false_negatives = reference_set - discovered_set

    precision = len(true_positives) / len(discovered_set) if discovered_set else 0.0
    recall = len(true_positives) / len(reference_set) if reference_set else 0.0
    f1_score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    hallucination_rate = len(false_positives) / len(discovered_set) if discovered_set else 0.0

    return {
        "true_positives": len(true_positives),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "precision": round(precision * 100.0, 2),
        "recall": round(recall * 100.0, 2),
        "f1_score": round(f1_score * 100.0, 2),
        "hallucination_rate": round(hallucination_rate * 100.0, 2),
        "coverage_score": round(recall * 100.0, 2),
    }


def _tier1_reference_metrics(
    discovered: Sequence[str],
    reference: Sequence[str],
) -> Dict[str, Any]:
    return _reference_metrics(discovered, reference)


def _evaluation_note(
    *,
    state: Any | None,
    error: Optional[str],
    reference_suppliers: Sequence[str],
    quota_exhausted: bool = False,
) -> str:
    if quota_exhausted:
        return "Quota exhausted during analysis; partial results captured."
    if error:
        return f"Pipeline failed due to: {error}"
    if not reference_suppliers:
        return "Completed successfully; reference data unavailable for this component."
    if state is not None and not getattr(state, "suppliers", []):
        return "Completed successfully; no suppliers were discovered."
    return "Completed successfully."


def calculate_component_metrics(
    *,
    company: str,
    product: str,
    component: str,
    sample_id: int,
    sample_label: str,
    timestamp: str,
    mode: str,
    max_depth: int,
    skip_news: bool,
    state: Any | None,
    runtime_seconds: float,
    error: Optional[str],
    reference_suppliers: Sequence[str],
    quota_exhausted: bool = False,
) -> Dict[str, Any]:
    supplier_data = extract_suppliers_by_tier(state) if state is not None else {
        "tier1_suppliers": "",
        "tier2_suppliers": "",
        "tier3_suppliers": "",
        "tier1_count": 0,
        "tier2_count": 0,
        "tier3_count": 0,
        "supplier_count": 0,
        "verified_supplier_count": 0,
        "risk_count": 0,
        "retrieved_context_chunks": 0,
        "health_score": None,
        "health_status": "",
        "average_confidence_score": None,
    }

    discovered_suppliers = _discovered_supplier_set(state) if state is not None else []
    reference_metrics = _tier1_reference_metrics(discovered_suppliers, reference_suppliers)
    component_evidence_missing = bool(
        component
        and state is not None
        and not getattr(state, "suppliers", [])
        and not error
    )
    evaluation_status = EVALUATION_STATUS_SUCCESS
    if quota_exhausted:
        evaluation_status = EVALUATION_STATUS_QUOTA_EXHAUSTED
    elif component_evidence_missing:
        evaluation_status = EVALUATION_STATUS_INSUFFICIENT_COMPONENT_SUPPLIER_EVIDENCE
    elif error:
        evaluation_status = EVALUATION_STATUS_FAILURE

    token_usage = _estimated_token_usage(state) if state is not None else None
    retrieval_grounding_score = _retrieval_grounding_score(state) if state is not None else None
    verification_success_rate = (
        round((supplier_data["verified_supplier_count"] / supplier_data["supplier_count"]) * 100.0, 2)
        if state is not None and supplier_data["supplier_count"]
        else (0.0 if state is not None else None)
    )

    evaluation_note = _evaluation_note(
        state=state,
        error=error,
        reference_suppliers=reference_suppliers,
        quota_exhausted=quota_exhausted,
    )
    provenance = _provenance_fields(state)
    if component_evidence_missing and not quota_exhausted:
        evaluation_note = "No component-specific supplier evidence found."
        supplier_data = {
            **supplier_data,
            "tier1_suppliers": "not_available",
            "tier2_suppliers": "not_available",
            "tier3_suppliers": "not_available",
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
        }

    tier2_details = _tier_qualitative_details(state, 2) if state is not None else {
        "tier2_discovered_suppliers": "not_available",
        "tier2_verified_suppliers": "not_available",
        "tier2_verification_status": "not_available",
        "tier2_confidence": "not_available",
        "tier2_paths": "not_available",
    }
    tier3_details = _tier_qualitative_details(state, 3) if state is not None else {
        "tier3_discovered_suppliers": "not_available",
        "tier3_verified_suppliers": "not_available",
        "tier3_verification_status": "not_available",
        "tier3_confidence": "not_available",
        "tier3_paths": "not_available",
    }

    return {
        "company": company,
        "product": product,
        "component": component,
        "sample_id": sample_id,
        "sample_label": sample_label,
        "timestamp": timestamp,
        "mode": mode,
        "max_depth": max_depth,
        "skip_news": skip_news,
        **provenance,
        "evaluation_status": evaluation_status,
        "evaluation_note": evaluation_note,
        "tier1_suppliers": supplier_data["tier1_suppliers"],
        "tier2_suppliers": supplier_data["tier2_suppliers"],
        "tier3_suppliers": supplier_data["tier3_suppliers"],
        "tier1_count": supplier_data["tier1_count"],
        "tier2_count": supplier_data["tier2_count"],
        "tier3_count": supplier_data["tier3_count"],
        "supplier_count": supplier_data["supplier_count"],
        "verified_supplier_count": supplier_data["verified_supplier_count"],
        "risk_count": supplier_data["risk_count"],
        "retrieved_context_chunks": supplier_data["retrieved_context_chunks"],
        "health_score": supplier_data["health_score"],
        "health_status": supplier_data["health_status"],
        "precision": reference_metrics["precision"],
        "recall": reference_metrics["recall"],
        "f1_score": reference_metrics["f1_score"],
        "hallucination_rate": reference_metrics["hallucination_rate"],
        "coverage_score": reference_metrics["coverage_score"],
        **tier2_details,
        **tier3_details,
        "retrieval_grounding_score": retrieval_grounding_score,
        "verification_success_rate": verification_success_rate,
        "average_confidence_score": supplier_data["average_confidence_score"],
        "runtime_seconds": round(runtime_seconds, 2),
        "token_usage": token_usage,
        "estimated_api_cost": _estimated_api_cost(token_usage) if token_usage is not None else None,
        "estimated_energy_consumption": _estimated_energy_consumption(runtime_seconds, token_usage)
        if token_usage is not None
        else None,
        "errors": (
            (error or "; ".join(getattr(state, "errors", []) or []))
            if state is not None
            else (error or "")
        ),
    }


def _run_single(
    *,
    company: str,
    product: str,
    component: str,
    sample_id: int,
    sample_label: str,
    mode: str,
    max_depth: int,
    skip_news: bool,
    reference_suppliers: Sequence[str],
    fast_benchmark: bool = False,
) -> Dict[str, Any]:
    started = time.perf_counter()
    state = None
    error_message = ""
    quota_exhausted = False
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        state = _run_analysis(
            company,
            product=product,
            component=component,
            benchmark_target_query=_benchmark_target_query(company, product, component),
            max_depth=max_depth,
            skip_news=skip_news,
            fast_benchmark=fast_benchmark,
            execution_mode=mode,
        )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        quota_exhausted = _is_quota_error_text(error_message)
        state = None
    runtime_seconds = time.perf_counter() - started
    if state is not None:
        quota_exhausted = quota_exhausted or bool(getattr(state, "quota_exhausted", False))
    return calculate_component_metrics(
        company=company,
        product=product,
        component=component,
        sample_id=sample_id,
        sample_label=sample_label,
        timestamp=timestamp,
        mode=mode,
        max_depth=max_depth,
        skip_news=skip_news,
        state=state,
        runtime_seconds=runtime_seconds,
        error=error_message or None,
        reference_suppliers=reference_suppliers,
        quota_exhausted=quota_exhausted,
    )


def _selected_products(
    companies: Sequence[str],
    components_filter: Optional[Sequence[str]] = None,
) -> List[Tuple[str, str, List[str]]]:
    selected: List[Tuple[str, str, List[str]]] = []
    normalized_filter = {
        _canonical(component) for component in components_filter or [] if component
    }
    for company in companies:
        product_info = PRODUCT_COMPONENT_MAP.get(company)
        if not product_info:
            continue
        components = list(product_info["components"])
        if normalized_filter:
            components = [
                component
                for component in components
                if _canonical(component) in normalized_filter
            ]
        selected.append((company, product_info["product"], components))
    return selected


def _sample_output_dir_name(sample_id: int, sample_label: str) -> str:
    return f"sample_{sample_id}_{_slugify(sample_label)}"


def get_sample_output_dir(sample_id: int, sample_label: str) -> Path:
    return OUTPUT_DIR / _sample_output_dir_name(sample_id, sample_label)


def _normalized_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for field in CSV_FIELDNAMES:
        value = row.get(field)
        normalized[field] = "" if value is None else value
    return normalized


def write_company_csv(output_dir: Path, company: str, rows: Sequence[Dict[str, Any]]) -> Path:
    file_name = COMPANY_FILE_MAP.get(company, f"{_slugify_company(company)}_product_benchmark.csv")
    path = output_dir / file_name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalized_row(row))
    return path


def write_master_csv(output_dir: Path, rows: Sequence[Dict[str, Any]]) -> Path:
    path = output_dir / "master_results.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalized_row(row))
    return path


def _rows_by_company(rows: Sequence[Dict[str, Any]], company: str) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("company") == company]


def _supplier_list_key(value: Any) -> str:
    if value in (None, "", "not_available"):
        return "not_available"
    if isinstance(value, str):
        return "; ".join(part.strip() for part in value.split(";") if part.strip())
    return str(value)


def _component_supplier_uniformity_warning(company_rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    if len(company_rows) <= 1:
        return None

    counts: Dict[str, int] = {}
    total = 0
    for row in company_rows:
        key = _supplier_list_key(row.get("tier1_suppliers"))
        counts[key] = counts.get(key, 0) + 1
        total += 1

    if not total:
        return None

    most_common = max(counts.values()) if counts else 0
    if most_common / total > 0.8:
        return (
            "WARNING: Component outputs appear identical. "
            "Component context may not be influencing discovery."
        )
    return None


def _mean_or_none(values: Iterable[Any], digits: int = 2) -> Optional[float]:
    numeric_values = [float(value) for value in values if value not in (None, "", "not_available")]
    if not numeric_values:
        return None
    return round(mean(numeric_values), digits)


def write_sample_summary(
    output_dir: Path,
    rows: Sequence[Dict[str, Any]],
    *,
    sample_id: int,
    sample_label: str,
    companies: Sequence[str],
    modes: Sequence[str],
    max_depth: int,
    skip_news: bool,
    fast_benchmark: bool,
) -> Path:
    successful_rows = [row for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_SUCCESS]
    failed_rows = [row for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_FAILURE]
    quota_rows = [row for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_QUOTA_EXHAUSTED]
    tier2_rows = [row for row in rows if row.get("tier2_discovered_suppliers") not in ("", "not_available")]
    tier3_rows = [row for row in rows if row.get("tier3_discovered_suppliers") not in ("", "not_available")]
    lines = [
        "# Product Benchmark Sample Summary",
        "",
        f"- Sample ID: {sample_id}",
        f"- Sample Label: {sample_label}",
        f"- Output Folder: {output_dir}",
        f"- Companies: {len(companies)}",
        f"- Modes: {', '.join(modes)}",
        f"- Max Depth: {max_depth}",
        f"- Skip News: {skip_news}",
        f"- Fast Benchmark: {fast_benchmark}",
        f"- Total rows: {len(rows)}",
        f"- Successful rows: {len(successful_rows)}",
        f"- Failed rows: {len(failed_rows)}",
        f"- Quota-exhausted rows: {len(quota_rows)}",
        "",
        "Quantitative evaluation was performed only for Tier 1 supplier relationships because reliable public ground-truth data is available primarily at Tier 1. Tier 2 and Tier 3 supplier relationships were evaluated qualitatively through discovered supply-chain paths, verification status, and confidence scores.",
        "",
        "## Per-Company Rows",
    ]
    for company in companies:
        company_rows = _rows_by_company(rows, company)
        lines.append(f"- {company}: {len(company_rows)} rows")

    if failed_rows:
        lines.extend(["", "## Failures"])
        for row in failed_rows:
            lines.append(
                f"- {row['company']} / {row['component']} / {row['mode']}: {row.get('errors', '') or 'Unknown error'}"
            )

    if quota_rows:
        lines.extend(["", "## Quota Exhausted"])
        for row in quota_rows:
            lines.append(
                f"- {row['company']} / {row['component']} / {row['mode']}: {row.get('errors', '') or 'Quota exhausted'}"
            )

    lines.extend(["", "## Tier 2 and Tier 3 Discovery Statistics"])
    lines.append(f"- Tier 2 rows with discovery output: {len(tier2_rows)}")
    lines.append(f"- Tier 3 rows with discovery output: {len(tier3_rows)}")
    if tier2_rows:
        lines.append("- Tier 2 output includes discovered suppliers, verified suppliers, confidence, and paths.")
    if tier3_rows:
        lines.append("- Tier 3 output includes discovered suppliers, verified suppliers, confidence, and paths.")

    warnings = [
        _component_supplier_uniformity_warning(_rows_by_company(rows, company))
        for company in companies
    ]
    warnings = [warning for warning in warnings if warning]
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)

    path = output_dir / "sample_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _sample_sort_key(path: Path) -> Tuple[int, str]:
    match = re.match(r"sample_(\d+)_(.+)$", path.name)
    if not match:
        return (10**9, path.name)
    return (int(match.group(1)), match.group(2))


def rebuild_all_samples_master() -> Path:
    _ensure_output_dir()
    combined_rows: List[Dict[str, Any]] = []
    for sample_dir in sorted(
        [path for path in OUTPUT_DIR.iterdir() if path.is_dir() and path.name.startswith("sample_")],
        key=_sample_sort_key,
    ):
        master_path = sample_dir / "master_results.csv"
        if not master_path.exists():
            continue
        with master_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row = dict(row)
                if not row.get("sample_id"):
                    match = re.match(r"sample_(\d+)_(.+)$", sample_dir.name)
                    if match:
                        row["sample_id"] = match.group(1)
                if not row.get("sample_label"):
                    match = re.match(r"sample_(\d+)_(.+)$", sample_dir.name)
                    if match:
                        row["sample_label"] = match.group(2)
                combined_rows.append(row)

    combined_rows.sort(
        key=lambda row: (
            int(row.get("sample_id") or 0),
            str(row.get("sample_label") or ""),
            str(row.get("company") or ""),
            str(row.get("component") or ""),
            str(row.get("mode") or ""),
            str(row.get("timestamp") or ""),
        )
    )

    with GLOBAL_MASTER_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in combined_rows:
            writer.writerow(_normalized_row(row))

    return GLOBAL_MASTER_CSV_PATH


def _run_sample_benchmark(
    *,
    sample_id: int,
    sample_label: str,
    companies: Sequence[str],
    components: Optional[Sequence[str]] = None,
    modes: Sequence[str],
    max_depth: int,
    skip_news: bool,
    overwrite: bool,
    fast_benchmark: bool = False,
) -> Tuple[List[Dict[str, Any]], Path]:
    sample_dir = get_sample_output_dir(sample_id, sample_label)
    if sample_dir.exists() and not overwrite:
        raise FileExistsError(
            f"Sample output folder already exists: {sample_dir}. Use --overwrite to replace it."
        )

    sample_dir.mkdir(parents=True, exist_ok=True)
    reference_rows = _load_reference_dataset()
    rows: List[Dict[str, Any]] = []
    previous_env = {key: os.environ.get(key) for key in FAST_FAIL_ENV}
    os.environ.update(FAST_FAIL_ENV)
    try:
        for company, product, components in _selected_products(companies, components):
            for component in components:
                tiered_reference = _reference_suppliers_for_component(
                    reference_rows, company, product, component
                )
                reference_suppliers = list(tiered_reference.get(1, []))
                for mode in modes:
                    rows.append(
                        _run_single(
                            company=company,
                            product=product,
                            component=component,
                            sample_id=sample_id,
                            sample_label=sample_label,
                            mode=mode,
                            max_depth=max_depth,
                            skip_news=skip_news,
                            fast_benchmark=fast_benchmark,
                            reference_suppliers=reference_suppliers,
                        )
                    )
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return rows, sample_dir


def generate_reference_dataset_audit(
    reference_rows: Sequence[Dict[str, Any]] | None = None,
) -> str:
    rows = list(reference_rows if reference_rows is not None else _load_reference_dataset())
    total_rows = len(rows)
    verified_rows = [row for row in rows if row.get("verification_status") == "verified"]
    partially_verified_rows = [row for row in rows if row.get("verification_status") == "partially_verified"]
    insufficient_rows = [
        row for row in rows if row.get("verification_status") == "insufficient_public_evidence"
    ]

    def _count_by(field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in rows:
            key = row.get(field) or "not_available"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[0]))

    duplicate_keys: Dict[Tuple[str, str, str, str], int] = {}
    for row in rows:
        key = (
            row.get("company", ""),
            row.get("product", ""),
            row.get("component", ""),
            row.get("tier", ""),
        )
        duplicate_keys[key] = duplicate_keys.get(key, 0) + 1

    duplicate_relationships = [
        f"{company} | {product} | {component} | tier {tier} ({count} rows)"
        for (company, product, component, tier), count in sorted(duplicate_keys.items())
        if count > 1
    ]

    missing_source_urls = [
        row
        for row in verified_rows
        if not row.get("source_url") or row.get("source_url") == "not_available"
    ]
    missing_parent_rows = [
        row
        for row in rows
        if row.get("tier") in {"2", "3"}
        and (not row.get("parent_supplier") or row.get("parent_supplier") == "not_available")
    ]
    incomplete_paths = [
        row
        for row in rows
        if row.get("tier") in {"2", "3"}
        and (not row.get("relationship_path") or row.get("relationship_path") == "not_available")
    ]
    warnings = [
        row
        for row in verified_rows
        if row.get("verification_status") == "verified"
        and row.get("relationship_type") == "supplier"
        and row.get("source_type") != "official_product_page"
    ]

    lines = [
        "# Product Reference Dataset Audit",
        "",
        f"- Total reference rows: {total_rows}",
        f"- Verified rows: {len(verified_rows)}",
        f"- Partially verified rows: {len(partially_verified_rows)}",
        f"- Insufficient-evidence rows: {len(insufficient_rows)}",
        "",
        "## Rows Per Company",
    ]
    for company, count in _count_by("company").items():
        lines.append(f"- {company}: {count}")
    lines.extend(["", "## Rows Per Product"])
    for product, count in _count_by("product").items():
        lines.append(f"- {product}: {count}")
    lines.extend(["", "## Rows Per Component"])
    for component, count in _count_by("component").items():
        lines.append(f"- {component}: {count}")
    lines.extend(["", "## Rows Per Tier"])
    for tier, count in _count_by("tier").items():
        lines.append(f"- Tier {tier}: {count}")

    source_summary: Dict[Tuple[str, str], int] = {}
    source_details: List[str] = []
    for row in verified_rows:
        key = (row.get("source_title", "not_available"), row.get("source_url", "not_available"))
        source_summary[key] = source_summary.get(key, 0) + 1
    lines.extend(["", "## Sources Used"])
    for (title, url), count in sorted(source_summary.items(), key=lambda item: (item[0][0], item[0][1])):
        lines.append(f"- {title} | {url} | {count} rows")
        source_details.append(url)

    lines.extend(["", "## Data Quality"])
    lines.append(f"- Duplicate relationships: {len(duplicate_relationships)}")
    lines.append(f"- Missing source URLs: {len(missing_source_urls)}")
    lines.append(f"- Missing parent relationships: {len(missing_parent_rows)}")
    lines.append(f"- Tier 2/3 rows with incomplete paths: {len(incomplete_paths)}")

    if duplicate_relationships:
        lines.extend(["", "## Duplicate Relationships"])
        lines.extend(f"- {item}" for item in duplicate_relationships)

    if missing_source_urls:
        lines.extend(["", "## Missing Source URLs"])
        for row in missing_source_urls:
            lines.append(
                f"- {row.get('company')} / {row.get('product')} / {row.get('component')} / tier {row.get('tier')}"
            )

    if missing_parent_rows:
        lines.extend(["", "## Missing Parent Relationships"])
        for row in missing_parent_rows:
            lines.append(
                f"- {row.get('company')} / {row.get('product')} / {row.get('component')} / tier {row.get('tier')}"
            )

    if incomplete_paths:
        lines.extend(["", "## Incomplete Tier Paths"])
        for row in incomplete_paths:
            lines.append(
                f"- {row.get('company')} / {row.get('product')} / {row.get('component')} / tier {row.get('tier')}"
            )

    lines.extend(["", "## Warning"])
    if warnings:
        for row in warnings:
            lines.append(
                f"- Manual review: {row.get('company')} / {row.get('product')} / {row.get('component')} relies on {row.get('source_type')} evidence from {row.get('source_title')}."
            )
    else:
        lines.append("- No specific rows flagged for manual review.")

    return "\n".join(lines)


def run_product_benchmark(
    *,
    sample_id: int,
    sample_label: str,
    companies: Sequence[str],
    components: Optional[Sequence[str]] = None,
    modes: Sequence[str],
    max_depth: int,
    skip_news: bool,
    overwrite: bool,
    fast_benchmark: bool = False,
) -> Tuple[List[Dict[str, Any]], Path, Path, Path, List[Path]]:
    rows, sample_dir = _run_sample_benchmark(
        sample_id=sample_id,
        sample_label=sample_label,
        companies=companies,
        components=components,
        modes=modes,
        max_depth=max_depth,
        skip_news=skip_news,
        fast_benchmark=fast_benchmark,
        overwrite=overwrite,
    )

    company_csv_paths: List[Path] = []
    for company in companies:
        company_rows = _rows_by_company(rows, company)
        company_csv_paths.append(write_company_csv(sample_dir, company, company_rows))

    master_csv_path = write_master_csv(sample_dir, rows)
    summary_path = write_sample_summary(
        sample_dir,
        rows,
        sample_id=sample_id,
        sample_label=sample_label,
        companies=companies,
        modes=modes,
        max_depth=max_depth,
        skip_news=skip_news,
        fast_benchmark=fast_benchmark,
    )
    global_master_csv_path = rebuild_all_samples_master()

    return rows, sample_dir, master_csv_path, global_master_csv_path, company_csv_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Product-level supply chain benchmark")
    parser.add_argument("--sample-id", type=int, required=True, help="Timed sample identifier.")
    parser.add_argument("--sample-label", required=True, help="Timed sample label.")
    parser.add_argument(
        "--companies",
        nargs="*",
        choices=DEFAULT_COMPANIES,
        default=DEFAULT_COMPANIES,
        help="Subset of companies to benchmark.",
    )
    parser.add_argument(
        "--components",
        default=None,
        help="Comma-separated subset of components to benchmark for each selected company.",
    )
    parser.add_argument(
        "--modes",
        nargs="*",
        choices=SUPPORTED_MODES,
        default=DEFAULT_MODES,
        help="Execution modes to run (llm, rag, or slm via Ollama).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Maximum recursive supplier discovery depth.",
    )
    skip_group = parser.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-news",
        dest="skip_news",
        action="store_true",
        help="Disable live news and financial risk providers.",
    )
    skip_group.add_argument(
        "--no-skip-news",
        dest="skip_news",
        action="store_false",
        help="Enable live news and financial risk providers.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing sample folder for the same sample ID and label.",
    )
    parser.add_argument(
        "--fast-benchmark",
        action="store_true",
        help="Prefer cache and heuristic paths, and stop on quota errors without retry loops.",
    )
    parser.set_defaults(skip_news=DEFAULT_SKIP_NEWS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    companies = [company for company in args.companies if company in PRODUCT_COMPONENT_MAP]
    components = (
        [component.strip() for component in args.components.split(",") if component.strip()]
        if args.components
        else None
    )
    try:
        _, sample_dir, master_csv_path, global_csv_path, company_csv_paths = run_product_benchmark(
            sample_id=args.sample_id,
            sample_label=args.sample_label,
            companies=companies,
            components=components,
            modes=args.modes,
            max_depth=args.max_depth,
            skip_news=args.skip_news,
            fast_benchmark=args.fast_benchmark,
            overwrite=args.overwrite,
        )
    except FileExistsError as exc:
        print(str(exc))
        return 1

    print("Sample benchmark completed.")
    print(f"Sample ID: {args.sample_id}")
    print(f"Sample Label: {args.sample_label}")
    print(f"Output folder: {sample_dir}")
    print(
        "Company CSV files generated: "
        + ", ".join(str(path) for path in company_csv_paths)
    )
    print(f"Master CSV: {master_csv_path}")
    print(f"Global combined CSV: {global_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
