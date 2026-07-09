from __future__ import annotations

import argparse
import csv
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EVALUATION_STATUS_SUCCESS = "success"
EVALUATION_STATUS_FAILURE = "system_failure"
EVALUATION_STATUS_INSUFFICIENT_COMPONENT_SUPPLIER_EVIDENCE = (
    "insufficient_component_supplier_evidence"
)

FAST_FAIL_ENV = {
    "LLM_MAX_RETRIES": "0",
    "LLM_TIMEOUT_SECONDS": "1",
}

REFERENCE_DATASET_PATH = Path("database/benchmarks/product_reference_dataset.csv")
OUTPUT_DIR = Path("database/benchmarks/product_level")
GLOBAL_MASTER_CSV_PATH = OUTPUT_DIR / "all_samples_master_results.csv"

COMPANY_FILE_MAP = {
    "Apple": "apple_product_benchmark.csv",
    "Samsung": "samsung_product_benchmark.csv",
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
                "Memory",
                "Storage",
                "Battery",
                "Wireless Chip",
                "RF Front-End",
                "Glass",
                "Assembly",
            ],
        },
        "Samsung": {
            "product": "Galaxy S25 Ultra",
            "components": [
                "Application Processor",
                "Display",
                "Camera System",
                "Memory",
                "Storage",
                "Battery",
                "Wireless/RF",
                "Glass",
                "PCB/Mainboard",
                "Assembly",
            ],
        },
        "Nvidia": {
            "product": "GeForce RTX 5090",
            "components": [
                "GPU Die",
                "Memory",
                "PCB",
                "Power Delivery",
                "Cooling System",
                "Display Interface",
                "Semiconductor Manufacturing",
                "Packaging",
                "Assembly",
            ],
        },
        "AMD": {
            "product": "Ryzen 9 9950X",
            "components": [
                "CPU Die",
                "I/O Die",
                "Packaging",
                "Wafer Fabrication",
                "Lithography Equipment",
                "Substrate",
                "Testing",
                "Assembly",
            ],
        },
        "Intel": {
            "product": "Core Ultra 9 285K",
            "components": [
                "CPU Tile",
                "GPU Tile",
                "SoC Tile",
                "Packaging",
                "Wafer Fabrication",
                "Lithography Equipment",
                "Substrate",
                "Testing",
                "Assembly",
            ],
        },
        "Tesla": {
            "product": "Model 3",
            "components": [
                "Battery Pack",
                "Battery Cells",
                "Electric Motor",
                "Power Electronics",
                "Autopilot/Compute Hardware",
                "Display System",
                "Body/Chassis",
                "Glass",
                "Tires",
                "Final Assembly",
            ],
        },
    }


PRODUCT_COMPONENT_MAP = get_product_component_map()
DEFAULT_COMPANIES = list(PRODUCT_COMPONENT_MAP.keys())
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


def _load_reference_dataset() -> Dict[Tuple[str, str, str, int], Dict[str, Any]]:
    if not REFERENCE_DATASET_PATH.exists():
        return {}

    rows: Dict[Tuple[str, str, str, int], Dict[str, Any]] = {}
    with REFERENCE_DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            company = (row.get("company") or "").strip()
            product = (row.get("product") or "").strip()
            component = (row.get("component") or "").strip()
            tier_raw = (row.get("tier") or "").strip()
            if not company or not product or not component:
                continue
            try:
                tier = int(tier_raw)
            except ValueError:
                continue
            rows[(company, product, component, tier)] = row
    return rows


def _reference_suppliers_for_component(
    reference_rows: Dict[Tuple[str, str, str, int], Dict[str, Any]],
    company: str,
    product: str,
    component: str,
) -> Dict[int, List[str]]:
    tiered: Dict[int, List[str]] = {1: [], 2: [], 3: []}
    for tier in (1, 2, 3):
        row = reference_rows.get((company, product, component, tier))
        if not row:
            continue
        tiered[tier] = _split_suppliers(row.get("reference_suppliers", "") or "")
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


def _reference_metrics(
    discovered: Sequence[str],
    reference: Sequence[str],
) -> Dict[str, Any]:
    discovered_set = {_canonical(name) for name in discovered if name}
    reference_set = {_canonical(name) for name in reference if name}

    if not reference_set:
        return {
            "precision": "not_available",
            "recall": "not_available",
            "f1_score": "not_available",
            "hallucination_rate": "not_available",
        }

    true_positives = discovered_set & reference_set
    false_positives = discovered_set - reference_set

    precision = len(true_positives) / len(discovered_set) if discovered_set else 0.0
    recall = len(true_positives) / len(reference_set) if reference_set else 0.0
    f1_score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    hallucination_rate = len(false_positives) / len(discovered_set) if discovered_set else 0.0

    return {
        "precision": round(precision * 100.0, 2),
        "recall": round(recall * 100.0, 2),
        "f1_score": round(f1_score * 100.0, 2),
        "hallucination_rate": round(hallucination_rate * 100.0, 2),
    }


def _evaluation_note(
    *,
    state: Any | None,
    error: Optional[str],
    reference_suppliers: Sequence[str],
) -> str:
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
    reference_metrics = _reference_metrics(discovered_suppliers, reference_suppliers)
    component_evidence_missing = bool(
        component
        and state is not None
        and not getattr(state, "suppliers", [])
        and not error
    )
    evaluation_status = (
        EVALUATION_STATUS_INSUFFICIENT_COMPONENT_SUPPLIER_EVIDENCE
        if component_evidence_missing
        else (EVALUATION_STATUS_FAILURE if error else EVALUATION_STATUS_SUCCESS)
    )

    token_usage = _estimated_token_usage(state) if state is not None else None
    retrieval_grounding_score = _retrieval_grounding_score(state) if state is not None else None
    verification_success_rate = (
        round((supplier_data["verified_supplier_count"] / supplier_data["supplier_count"]) * 100.0, 2)
        if state is not None and supplier_data["supplier_count"]
        else (0.0 if state is not None else None)
    )

    evaluation_note = _evaluation_note(
        state=state, error=error, reference_suppliers=reference_suppliers
    )
    if component_evidence_missing:
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
) -> Dict[str, Any]:
    started = time.perf_counter()
    state = None
    error_message = ""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        state = _run_analysis(
            company,
            product=product,
            component=component,
            benchmark_target_query=_benchmark_target_query(company, product, component),
            max_depth=max_depth,
            skip_news=skip_news,
            execution_mode=mode,
        )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
    runtime_seconds = time.perf_counter() - started
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
) -> Path:
    successful_rows = [row for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_SUCCESS]
    failed_rows = [row for row in rows if row.get("evaluation_status") == EVALUATION_STATUS_FAILURE]
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
        f"- Total rows: {len(rows)}",
        f"- Successful rows: {len(successful_rows)}",
        f"- Failed rows: {len(failed_rows)}",
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
                reference_suppliers = _reference_supplier_union(tiered_reference)
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
) -> Tuple[List[Dict[str, Any]], Path, Path, Path, List[Path]]:
    rows, sample_dir = _run_sample_benchmark(
        sample_id=sample_id,
        sample_label=sample_label,
        companies=companies,
        components=components,
        modes=modes,
        max_depth=max_depth,
        skip_news=skip_news,
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
        choices=DEFAULT_MODES,
        default=DEFAULT_MODES,
        help="Execution modes to run.",
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
