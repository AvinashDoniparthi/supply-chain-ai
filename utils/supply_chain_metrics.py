from typing import Any, Dict, Set

from models.state import AgentState
from scraping.supplier_discovery import expected_tier1_suppliers
from utils.identity_resolution import resolver


LABEL_ORDER = {
    "Insufficient Data": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Unassessed": 3,
}


def canonical_supplier_name(value: str) -> str:
    return resolver.resolve(value)


def label_from_ratio(ratio: float) -> str:
    if ratio >= 0.8:
        return "High"
    if ratio >= 0.5:
        return "Medium"
    if ratio > 0:
        return "Low"
    return "Insufficient Data"


def lower_label(*labels: str) -> str:
    return min(labels, key=lambda label: LABEL_ORDER.get(label, 0))


def uses_expected_supplier_evaluation(state: AgentState) -> bool:
    metadata = state.company.metadata if state.company else {}
    return bool(
        metadata.get("evaluation_mode")
        or metadata.get("source") == "curated benchmark"
    )


def calculate_discovery_coverage(state: AgentState) -> Dict[str, Any]:
    target = state.company.name if state.company else state.target_company or ""
    use_expected = uses_expected_supplier_evaluation(state)
    expected_suppliers = expected_tier1_suppliers(target) if use_expected else set()
    expected = {canonical_supplier_name(name) for name in expected_suppliers}

    tier1_supplier_list = [
        canonical_supplier_name(supplier.canonical_name or supplier.name)
        for supplier in state.suppliers
        if supplier.tier == 1
    ]
    tier1_suppliers = set(tier1_supplier_list)
    canonical_uniqueness_ratio = (
        len(tier1_suppliers) / len(tier1_supplier_list)
        if tier1_supplier_list
        else 0.0
    )

    if expected:
        expected_count = len(expected)
        matched = tier1_suppliers & expected
        false_positives = tier1_suppliers - expected
        coverage_basis = "expected_suppliers"
    else:
        expected_count = len(tier1_suppliers)
        matched = set(tier1_suppliers)
        false_positives = set()
        coverage_basis = "discovered_suppliers"

    coverage_ratio = min(1.0, len(matched) / expected_count) if expected_count else 0.0
    precision = (
        len(matched) / len(tier1_suppliers)
        if tier1_suppliers and expected
        else (1.0 if tier1_suppliers else 0.0)
    )
    false_positive_rate = (
        len(false_positives) / len(tier1_suppliers)
        if tier1_suppliers and expected
        else 0.0
    )

    coverage_label = label_from_ratio(coverage_ratio)
    precision_label = label_from_ratio(precision)
    uniqueness_label = label_from_ratio(canonical_uniqueness_ratio)
    verification_quality = calculate_verification_quality(state)
    if verification_quality["label"] == "Unassessed":
        label = lower_label(coverage_label, precision_label, uniqueness_label)
    else:
        label = lower_label(
            coverage_label,
            precision_label,
            uniqueness_label,
            verification_quality["label"],
        )
    if verification_quality["label"] == "Unassessed":
        verification_adjusted_label = label
        verification_adjusted_ratio = coverage_ratio * precision * canonical_uniqueness_ratio
    else:
        verification_adjusted_label = lower_label(label, verification_quality["label"])
        verification_adjusted_ratio = (
            coverage_ratio
            * precision
            * canonical_uniqueness_ratio
            * verification_quality["quality_factor"]
        )

    return {
        "target": target,
        "coverage_basis": coverage_basis,
        "tier1_supplier_count": len(tier1_supplier_list),
        "canonical_tier1_supplier_count": len(tier1_suppliers),
        "expected_count": expected_count,
        "matched_expected_count": len(matched),
        "coverage_ratio": round(coverage_ratio, 4),
        "precision": round(precision, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "canonical_uniqueness_ratio": round(canonical_uniqueness_ratio, 4),
        "label": label,
        "raw_coverage_label": coverage_label,
        "verification_adjusted_ratio": round(verification_adjusted_ratio, 4),
        "verification_adjusted_label": verification_adjusted_label,
        "matched_suppliers": sorted(matched),
        "missing_expected_suppliers": sorted(expected - matched) if expected else [],
        "false_positive_suppliers": sorted(false_positives),
    }


def calculate_verification_quality(state: AgentState) -> Dict[str, Any]:
    """Return verification quality metrics without treating failures as risks."""
    suppliers = list(state.suppliers)
    if not suppliers:
        return {
            "verified_count": 0,
            "failed_count": 0,
            "missing_count": 0,
            "total_count": 0,
            "quality_ratio": 0.0,
            "quality_factor": 1.0,
            "label": "Insufficient Data",
        }

    # If verification never ran, avoid punishing isolated unit-test fixtures or
    # deliberately skipped verification runs.
    if not state.verification_results:
        return {
            "verified_count": 0,
            "failed_count": 0,
            "missing_count": 0,
            "total_count": len(suppliers),
            "quality_ratio": 1.0,
            "quality_factor": 1.0,
            "label": "Unassessed",
        }

    verification_map = {}
    for result in state.verification_results:
        verification_map[canonical_supplier_name(result.supplier_name)] = result

    verified_count = 0
    failed_count = 0
    missing_count = 0

    for supplier in suppliers:
        key = canonical_supplier_name(supplier.canonical_name or supplier.name)
        result = verification_map.get(key)
        if not result:
            missing_count += 1
        elif result.verified:
            verified_count += 1
        else:
            failed_count += 1

    total_count = len(suppliers)
    quality_ratio = verified_count / total_count if total_count else 0.0
    issue_count = failed_count + missing_count
    quality_factor = quality_ratio if issue_count >= 2 else max(0.8, quality_ratio)
    if quality_ratio >= 0.8:
        label = "High"
    elif quality_ratio >= 0.5:
        label = "Medium"
    elif quality_ratio > 0:
        label = "Low"
    else:
        label = "Insufficient Data"

    return {
        "verified_count": verified_count,
        "failed_count": failed_count,
        "missing_count": missing_count,
        "total_count": total_count,
        "quality_ratio": round(quality_ratio, 4),
        "quality_factor": round(quality_factor, 4),
        "label": label,
    }


def coverage_confidence_cap(coverage_ratio: float) -> float:
    if coverage_ratio >= 0.8:
        return 1.0
    if coverage_ratio >= 0.5:
        return 0.78
    if coverage_ratio >= 0.3:
        return 0.6
    if coverage_ratio > 0:
        return 0.45
    return 0.25
