import argparse
import logging
import os
from collections import defaultdict
from enum import Enum
from typing import Iterable, List, Optional

from models.state import AgentState, RiskAnalysis, SupplierInfo
from utils.identity_resolution import resolver
from utils.supply_chain_metrics import (
    calculate_discovery_coverage,
    calculate_verification_quality,
)


class OutputMode(str, Enum):
    QUIET = "QUIET"
    NORMAL = "NORMAL"
    DEBUG = "DEBUG"


_mode = OutputMode.QUIET


def parse_output_mode(value: Optional[str]) -> OutputMode:
    normalized = (value or "").strip().upper()
    if normalized in {"DEBUG", "TRUE", "1"}:
        return OutputMode.DEBUG
    if normalized in {"NORMAL", "INFO"}:
        return OutputMode.NORMAL
    return OutputMode.QUIET


def configure_output(mode: OutputMode) -> None:
    global _mode
    _mode = mode

    logging_level = logging.DEBUG if mode == OutputMode.DEBUG else logging.CRITICAL
    logging.basicConfig(
        level=logging_level,
        format="%(levelname)s:%(name)s:%(message)s",
        force=True,
    )

    if mode != OutputMode.DEBUG:
        for logger_name in ("httpx", "httpcore", "urllib3", "requests", "langchain"):
            logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_output_mode() -> OutputMode:
    return _mode


def is_debug() -> bool:
    return _mode == OutputMode.DEBUG


def is_normal_or_debug() -> bool:
    return _mode in {OutputMode.NORMAL, OutputMode.DEBUG}


def emit(message: str = "", min_mode: OutputMode = OutputMode.QUIET) -> None:
    order = {
        OutputMode.QUIET: 0,
        OutputMode.NORMAL: 1,
        OutputMode.DEBUG: 2,
    }
    if order[_mode] >= order[min_mode]:
        print(message)


def progress(step: int, total: int, label: str) -> None:
    emit(f"[{step}/{total}] {label}", OutputMode.NORMAL)


def agent_event(message: str) -> None:
    emit(message, OutputMode.NORMAL)


def debug_log(logger: logging.Logger, message: str, *args) -> None:
    logger.debug(message, *args)


def add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--normal",
        action="store_true",
        help="Show concise agent progress and accepted findings.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show full diagnostic output.",
    )
    parser.add_argument(
        "--log-level",
        choices=["QUIET", "NORMAL", "DEBUG"],
        help="Output mode. Defaults to LOG_LEVEL or QUIET.",
    )


def mode_from_args(args: argparse.Namespace) -> OutputMode:
    if getattr(args, "debug", False):
        return OutputMode.DEBUG
    if getattr(args, "normal", False):
        return OutputMode.NORMAL
    return parse_output_mode(getattr(args, "log_level", None) or os.getenv("LOG_LEVEL"))


def execution_mode_label(state: AgentState) -> str:
    return "RAG" if getattr(state, "execution_mode", "llm") == "rag" else "LLM-only"


def risk_level_from_health(score: Optional[float]) -> str:
    if score is None:
        return "Unknown"
    if score >= 85:
        return "Low"
    if score >= 70:
        return "Moderate"
    if score >= 50:
        return "Elevated"
    return "High"


def coverage_label_from_ratio(ratio: float) -> str:
    if ratio >= 0.8:
        return "High"
    if ratio >= 0.5:
        return "Medium"
    if ratio > 0:
        return "Low"
    return "Insufficient Data"


def risk_sort_key(risk: RiskAnalysis) -> int:
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(risk.severity, 0)


DATA_QUALITY_RISK_PHRASES = (
    "failed verification",
    "no verification data",
    "low verification confidence",
    "legitimacy cannot be confirmed",
    "relationship verification",
)

EXTERNAL_RISK_TYPES = {"geopolitical", "news", "financial", "environmental"}
EXTERNAL_RISK_PHRASES = (
    "bankruptcy",
    "capacity shortage",
    "conflict",
    "debt",
    "default",
    "disruption",
    "earthquake",
    "export restriction",
    "financial distress",
    "fire",
    "flood",
    "geopolitical",
    "insolvency",
    "labor strike",
    "natural disaster",
    "plant closure",
    "revenue collapse",
    "sanction",
    "shortage",
    "shutdown",
    "strike",
    "trade restriction",
    "war",
)


def is_data_quality_risk(risk: RiskAnalysis) -> bool:
    text = f"{risk.risk_type} {risk.reasoning}".lower()
    return any(phrase in text for phrase in DATA_QUALITY_RISK_PHRASES)


def is_external_risk(risk: RiskAnalysis) -> bool:
    if is_data_quality_risk(risk):
        return False
    text = f"{risk.risk_type} {risk.reasoning}".lower()
    if risk.risk_type.lower() in EXTERNAL_RISK_TYPES:
        return True
    return any(phrase in text for phrase in EXTERNAL_RISK_PHRASES)


def unique_risks(risks: Iterable[RiskAnalysis]) -> List[RiskAnalysis]:
    seen = set()
    unique = []
    for risk in sorted(risks, key=risk_sort_key, reverse=True):
        description = risk.reasoning.strip() or risk.risk_type
        key = (risk.severity.lower(), risk.risk_type.lower(), description)
        if key in seen:
            continue
        seen.add(key)
        unique.append(risk)
    return unique


def _risk_label(risk: RiskAnalysis) -> str:
    text = risk.reasoning.strip() or f"{risk.risk_type} risk"
    if len(text) > 240:
        text = text[:237].rstrip() + "..."
    return text


def _critical_suppliers(state: AgentState, limit: int = 5) -> List[str]:
    criticality = {
        c.supplier_name: c for c in state.supplier_criticality_scores
    }
    ranked = sorted(
        state.suppliers,
        key=lambda s: criticality.get(s.name).criticality_score
        if criticality.get(s.name)
        else 0,
        reverse=True,
    )
    critical = [
        s.name
        for s in ranked
        if criticality.get(s.name)
        and criticality[s.name].criticality_level in {"Critical", "High"}
    ]
    if not critical:
        critical = [s.name for s in ranked[:2]]
    return critical[:limit]


def _name_keys(name: Optional[str]) -> set[str]:
    if not name:
        return set()
    canonical = resolver.resolve(name)
    keys = {name, name.lower(), canonical, canonical.lower()}
    keys.update(resolver.aliases_for(canonical))
    keys.update(alias.lower() for alias in resolver.aliases_for(canonical))
    return {key for key in keys if key}


def _relationship_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    rel_map = {}
    for result in state.relationship_results:
        for key in _name_keys(result.candidate_company):
            rel_map[key] = result.relationship_type

    relationship = (
        rel_map.get(supplier.name)
        or rel_map.get(supplier.name.lower())
        or rel_map.get(supplier.canonical_name or "")
        or rel_map.get((supplier.canonical_name or "").lower())
    )
    if relationship == "supplier" and supplier.tier > 1:
        return "upstream_supplier"
    if relationship:
        return relationship
    return "upstream_supplier" if supplier.tier > 1 else "supplier"


def _confidence_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    confidence_map = {}
    for score in state.supplier_confidence_scores:
        for key in _name_keys(score.supplier_name):
            confidence_map[key] = score.final_confidence

    confidence = (
        confidence_map.get(supplier.name)
        or confidence_map.get(supplier.name.lower())
        or confidence_map.get(supplier.canonical_name or "")
        or confidence_map.get((supplier.canonical_name or "").lower())
        or supplier.propagated_confidence
        or supplier.discovery_confidence
    )
    return f"{confidence:.2f}" if confidence else "not scored"


def _verification_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    verification_map = {}
    for result in state.verification_results:
        for key in _name_keys(result.supplier_name):
            verification_map[key] = result

    result = (
        verification_map.get(supplier.name)
        or verification_map.get(supplier.name.lower())
        or verification_map.get(supplier.canonical_name or "")
        or verification_map.get((supplier.canonical_name or "").lower())
    )
    if not result:
        return "not verified"
    status = "verified" if result.verified else "failed"
    return f"{status} ({result.confidence_score:.2f})"


def _path_for_supplier(supplier: SupplierInfo) -> str:
    path = supplier.relationship_path or []
    if not path:
        return "N/A"
    if len(path) == 1 and " -> " in path[0]:
        return path[0]
    return " -> ".join(path)


def render_supplier_tier_lines(state: AgentState) -> List[str]:
    lines = []
    suppliers_by_tier = defaultdict(list)
    for supplier in state.suppliers:
        suppliers_by_tier[supplier.tier].append(supplier)

    max_tier = max([3, *suppliers_by_tier.keys()]) if state.suppliers else 3
    for tier in range(1, max_tier + 1):
        lines.append(f"TIER {tier} SUPPLIERS")
        tier_suppliers = sorted(
            suppliers_by_tier.get(tier, []),
            key=lambda supplier: supplier.name,
        )
        if not tier_suppliers:
            lines.append("Insufficient Data" if tier == 1 else "None identified")
            if tier != max_tier:
                lines.append("")
            continue

        for supplier in tier_suppliers:
            lines.append(f"- {supplier.name}")
            if tier > 1:
                lines.append(f"  Parent: {supplier.parent_company or 'N/A'}")
                lines.append(f"  Path: {_path_for_supplier(supplier)}")
            lines.append(f"  Confidence: {_confidence_for_supplier(state, supplier)}")
            lines.append(
                f"  Relationship: {_relationship_for_supplier(state, supplier)}"
            )
            lines.append(f"  Verification: {_verification_for_supplier(state, supplier)}")
        if tier != max_tier:
            lines.append("")

    return lines


def data_quality_warning_lines(state: AgentState) -> List[str]:
    verification_map = {}
    for result in state.verification_results:
        for key in _name_keys(result.supplier_name):
            verification_map[key] = result

    lines = []
    for supplier in sorted(state.suppliers, key=lambda item: item.name):
        result = (
            verification_map.get(supplier.name)
            or verification_map.get(supplier.name.lower())
            or verification_map.get(supplier.canonical_name or "")
            or verification_map.get((supplier.canonical_name or "").lower())
        )
        if not state.verification_results:
            continue
        if not result:
            lines.extend(
                [
                    f"- Supplier missing verification: {supplier.name}",
                    "  Reason: No verification result was produced for this supplier.",
                    "  Confidence: 0.00",
                ]
            )
        elif not result.verified:
            lines.extend(
                [
                    f"- Supplier failed verification: {supplier.name}",
                    f"  Reason: {result.reasoning}",
                    f"  Confidence: {result.confidence_score:.2f}",
                ]
            )
        elif result.confidence_score < 0.8:
            lines.extend(
                [
                    f"- Low verification confidence: {supplier.name}",
                    f"  Reason: {result.reasoning}",
                    f"  Confidence: {result.confidence_score:.2f}",
                ]
            )

    return lines


def render_risk_summary(risks: Iterable[RiskAnalysis]) -> List[str]:
    grouped = defaultdict(list)
    for risk in unique_risks(risk for risk in risks if is_external_risk(risk)):
        grouped[risk.severity.capitalize()].append(_risk_label(risk))

    lines = ["RISK SUMMARY"]
    emitted_any = False
    for severity in ("Critical", "High", "Medium", "Low"):
        entries = grouped.get(severity, [])
        if not entries:
            continue
        emitted_any = True
        lines.append("")
        lines.append(f"{severity}:")
        lines.extend(f"- {entry}" for entry in entries)

    return lines if emitted_any else []


def render_final_report(state: AgentState, include_header: bool = True) -> None:
    company = state.company.name if state.company else state.target_company or "N/A"
    risks = unique_risks(r for r in state.risk_assessments if is_external_risk(r))
    health = state.supply_chain_health
    report = state.executive_report
    critical_suppliers = _critical_suppliers(state)
    top_risks = risks[:3]
    coverage = calculate_discovery_coverage(state)
    verification_quality = calculate_verification_quality(state)
    warning_lines = data_quality_warning_lines(state)

    if include_header:
        emit("=" * 50)
        emit(f"SUPPLY CHAIN ANALYSIS: {company}")
        emit("=" * 50)
        emit("")

    emit(f"Mode: {execution_mode_label(state)}")
    if getattr(state, "execution_mode", "llm") == "rag":
        emit(
            f"Retrieved evidence chunks: {state.run_metadata.get('retrieval_chunks_attached', 0)}"
        )
    emit("")

    emit("DISCOVERY QUALITY")
    if coverage.get("coverage_basis") == "expected_suppliers":
        emit(
            f"Coverage: {coverage['label']} - {coverage['matched_expected_count']}/"
            f"{coverage['expected_count']} expected Tier-1 suppliers identified."
        )
    else:
        emit(
            f"Coverage: {coverage['label']} - "
            f"{coverage['tier1_supplier_count']} discovered Tier-1 suppliers identified."
        )
    if coverage.get("coverage_basis") == "expected_suppliers" and coverage["missing_expected_suppliers"]:
        emit("Missing expected suppliers: " + ", ".join(coverage["missing_expected_suppliers"][:5]))
    if verification_quality["quality_factor"] < 1.0:
        emit(
            f"Verification-adjusted coverage: {coverage['verification_adjusted_label']} "
            f"({coverage['verification_adjusted_ratio']:.0%}; "
            f"{verification_quality['verified_count']}/{verification_quality['total_count']} suppliers verified)."
        )

    emit("")
    emit("SUPPLY CHAIN HEALTH")
    if health:
        if health.status == "Insufficient Data":
            emit(f"Insufficient Data - score capped at {health.overall_score}/100.")
        else:
            emit(f"{health.status} - {health.overall_score}/100.")
    else:
        emit("Insufficient Data")

    emit("")
    for line in render_supplier_tier_lines(state):
        emit(line)

    if is_debug():
        emit("")
        emit("DEBUG FLAT SUPPLIER LIST", OutputMode.DEBUG)
        if state.suppliers:
            for supplier in state.suppliers:
                emit(f"- {supplier.name}", OutputMode.DEBUG)
        else:
            emit("Insufficient Data", OutputMode.DEBUG)

    emit("")
    emit("TOP RISKS")
    if top_risks:
        for risk in top_risks:
            emit(f"- [{risk.severity.upper()}] {_risk_label(risk)}")
    elif coverage["label"] in {"Low", "Insufficient Data"}:
        emit("Insufficient Data")
    else:
        emit("No supplier-specific risks detected")

    emit("")
    emit("DATA QUALITY WARNINGS")
    if warning_lines:
        for line in warning_lines:
            emit(line)
    else:
        emit("None")

    emit("")
    emit("CRITICAL SUPPLIERS")
    for supplier in critical_suppliers:
        emit(f"- {supplier}")

    emit("")
    emit("EXECUTIVE SUMMARY")
    if report:
        summary_lines = report.executive_summary.splitlines()
        in_summary = False
        for line in summary_lines:
            if line == "EXECUTIVE SUMMARY":
                in_summary = True
                continue
            if in_summary and line:
                emit(line)
    elif health:
        emit(health.summary)
    else:
        emit("Insufficient Data")

    emit("")
    emit("=" * 50)
    emit("ANALYSIS COMPLETE")
    emit("=" * 50)
