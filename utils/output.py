import argparse
import logging
import os
from collections import defaultdict
from datetime import datetime
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


def _display_label(value: Optional[str]) -> str:
    if not value:
        return "N/A"
    labels = {
        "supplier": "Supplier",
        "upstream_supplier": "Upstream Supplier",
        "verified": "Verified",
        "failed": "Failed",
        "not verified": "Not Verified",
        "not scored": "Not Scored",
    }
    normalized = str(value).strip()
    return labels.get(normalized.lower(), normalized.replace("_", " ").title())


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


def _lookup_value(mapping: dict, *names: Optional[str]):
    for name in names:
        for key in _name_keys(name):
            if key in mapping:
                return mapping[key]
    return None


def _supplier_lookup(state: AgentState) -> dict:
    suppliers = {}
    for supplier in state.suppliers:
        for key in _name_keys(supplier.name) | _name_keys(supplier.canonical_name):
            suppliers[key] = supplier
    return suppliers


def _relationship_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    rel_map = {}
    for result in state.relationship_results:
        for key in _name_keys(result.candidate_company):
            rel_map[key] = result.relationship_type

    relationship = _lookup_value(rel_map, supplier.name, supplier.canonical_name)
    if relationship == "supplier" and supplier.tier > 1:
        return "upstream_supplier"
    if relationship:
        return relationship
    return "upstream_supplier" if supplier.tier > 1 else "supplier"


def _confidence_value_for_supplier(state: AgentState, supplier: SupplierInfo) -> Optional[float]:
    confidence_map = {}
    for score in state.supplier_confidence_scores:
        for key in _name_keys(score.supplier_name):
            confidence_map[key] = score.final_confidence

    confidence = _lookup_value(confidence_map, supplier.name, supplier.canonical_name)
    if confidence is not None:
        return confidence
    if supplier.propagated_confidence is not None:
        return supplier.propagated_confidence
    if supplier.discovery_confidence is not None:
        return supplier.discovery_confidence
    return None


def _confidence_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    confidence = _confidence_value_for_supplier(state, supplier)
    return f"{confidence:.2f}" if confidence is not None else "Not Scored"


def _verification_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    verification_map = {}
    for result in state.verification_results:
        for key in _name_keys(result.supplier_name):
            verification_map[key] = result

    result = _lookup_value(verification_map, supplier.name, supplier.canonical_name)
    if not result:
        return "Not Verified"
    status = "verified" if result.verified else "failed"
    return f"{_display_label(status)} ({result.confidence_score:.2f})"


def _path_for_supplier(supplier: SupplierInfo) -> str:
    path = supplier.relationship_path or []
    if not path:
        return "N/A"
    if len(path) == 1 and " -> " in path[0]:
        return path[0]
    return " -> ".join(path)


def _field_line(label: str, value: str) -> str:
    return f"   {label:<12} : {value}"


def render_supplier_tier_lines(state: AgentState) -> List[str]:
    lines = []
    suppliers_by_tier = defaultdict(list)
    for supplier in state.suppliers:
        suppliers_by_tier[supplier.tier].append(supplier)

    max_tier = max([3, *suppliers_by_tier.keys()]) if state.suppliers else 3
    for tier in range(1, max_tier + 1):
        if tier <= 3:
            lines.append(f"4.{tier} Tier {tier} Suppliers")
        lines.append(f"TIER {tier} SUPPLIERS")
        if tier == 1:
            lines.append(f"Direct suppliers to {state.target_company or 'the target company'}")
        else:
            lines.append(f"Upstream suppliers connected through Tier {tier - 1} suppliers")
        lines.append("")
        tier_suppliers = sorted(
            suppliers_by_tier.get(tier, []),
            key=lambda supplier: supplier.name,
        )
        if not tier_suppliers:
            lines.append("None identified")
            if tier != max_tier:
                lines.append("")
            continue

        for index, supplier in enumerate(tier_suppliers, start=1):
            lines.append(f"{index}. {supplier.name}")
            if tier > 1:
                lines.append(_field_line("Parent", supplier.parent_company or "N/A"))
                lines.append(_field_line("Path", _path_for_supplier(supplier)))
            lines.append(
                _field_line(
                    "Relationship",
                    _display_label(_relationship_for_supplier(state, supplier)),
                )
            )
            lines.append(_field_line("Confidence", _confidence_for_supplier(state, supplier)))
            lines.append(_field_line("Verification", _verification_for_supplier(state, supplier)))
            if index != len(tier_suppliers):
                lines.append("")
        if tier != max_tier:
            lines.append("")

    return lines


def data_quality_warning_lines(state: AgentState) -> List[str]:
    verification_map = {}
    for result in state.verification_results:
        for key in _name_keys(result.supplier_name):
            verification_map[key] = result

    grouped = {
        "Low Verification Confidence": [],
        "Failed Verification": [],
        "Missing Verification Result": [],
    }
    for supplier in sorted(state.suppliers, key=lambda item: item.name):
        if not state.verification_results:
            continue
        result = _lookup_value(verification_map, supplier.name, supplier.canonical_name)
        if not result:
            grouped["Missing Verification Result"].append(
                (
                    supplier.name,
                    "0.00",
                    "No verification result was produced for this supplier.",
                )
            )
        elif not result.verified:
            grouped["Failed Verification"].append(
                (supplier.name, f"{result.confidence_score:.2f}", result.reasoning)
            )
        elif result.confidence_score < 0.8:
            grouped["Low Verification Confidence"].append(
                (supplier.name, f"{result.confidence_score:.2f}", result.reasoning)
            )

    lines = []
    for group_name, entries in grouped.items():
        lines.append(group_name)
        if not entries:
            lines.append("None identified")
        else:
            for index, (name, confidence, reason) in enumerate(entries, start=1):
                lines.append(f"{index}. {name}")
                lines.append(f"   Confidence: {confidence}")
                lines.append(f"   Reason: {reason}")
                if index != len(entries):
                    lines.append("")
        if group_name != list(grouped.keys())[-1]:
            lines.append("")
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


def _generated_at(state: AgentState) -> str:
    generated_at = state.run_metadata.get("generated_at")
    if generated_at:
        return str(generated_at)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    state.run_metadata["generated_at"] = generated_at
    return generated_at


def _executive_summary_lines(state: AgentState) -> List[str]:
    report = state.executive_report
    health = state.supply_chain_health
    summary = ""
    summary_includes_recommendations = False
    if report and report.executive_summary:
        summary = report.executive_summary.strip()
        if "1. EXECUTIVE SUMMARY" in summary:
            summary = summary.split("1. EXECUTIVE SUMMARY", 1)[1]
            next_section = summary.find("\n2. DISCOVERY QUALITY")
            if next_section != -1:
                summary = summary[:next_section].strip()
            summary_includes_recommendations = "Recommendations" in summary
        elif summary.startswith("EXECUTIVE SUMMARY"):
            summary = summary.split("EXECUTIVE SUMMARY", 1)[1].strip()
    if not summary and health:
        summary = health.summary
    if not summary:
        summary = "None identified"

    lines = [summary]
    if report and report.recommendations and not summary_includes_recommendations:
        lines.extend(["", "Recommendations"])
        for index, recommendation in enumerate(report.recommendations, start=1):
            lines.append(f"{index}. {recommendation}")
    return lines


def _discovery_quality_lines(state: AgentState) -> List[str]:
    coverage = calculate_discovery_coverage(state)
    verification_quality = calculate_verification_quality(state)
    lines = []
    if coverage.get("coverage_basis") == "expected_suppliers":
        lines.append(
            f"Coverage: {coverage['label']} - {coverage['matched_expected_count']}/"
            f"{coverage['expected_count']} expected Tier-1 suppliers identified."
        )
    else:
        lines.append(
            f"Coverage: {coverage['label']} - "
            f"{coverage['tier1_supplier_count']} discovered Tier-1 suppliers identified."
        )
    if coverage.get("coverage_basis") == "expected_suppliers":
        missing = coverage["missing_expected_suppliers"]
        false_positive = coverage["false_positive_suppliers"]
        lines.append(
            "Missing expected suppliers: "
            + (", ".join(missing[:5]) if missing else "None identified")
        )
        lines.append(
            "Unexpected Tier-1 candidates: "
            + (", ".join(false_positive[:5]) if false_positive else "None identified")
        )
    if verification_quality["quality_factor"] < 1.0:
        lines.append(
            f"Verification-adjusted coverage: {coverage['verification_adjusted_label']} "
            f"({coverage['verification_adjusted_ratio']:.0%}; "
            f"{verification_quality['verified_count']}/{verification_quality['total_count']} suppliers verified)."
        )
    if getattr(state, "execution_mode", "llm") == "rag":
        lines.append(
            f"Retrieved evidence chunks: {state.run_metadata.get('retrieval_chunks_attached', 0)}"
        )
    return lines


def _health_lines(state: AgentState) -> List[str]:
    health = state.supply_chain_health
    if not health:
        return ["None identified"]
    if health.status == "Insufficient Data":
        lines = [f"Status: Insufficient Data - score capped at {health.overall_score}/100."]
    else:
        lines = [f"Status: {health.status} - {health.overall_score}/100."]
    lines.extend(
        [
            f"Supplier Count: {health.supplier_count}",
            f"Critical Suppliers: {health.critical_suppliers}",
            f"High-Risk Suppliers: {health.high_risk_suppliers}",
            f"Summary: {health.summary}",
        ]
    )
    return lines


def _risk_title(risk: RiskAnalysis) -> str:
    risk_type = _display_label(risk.risk_type)
    return f"{risk_type} risk involving {risk.supplier_name}"


def _risk_lines(state: AgentState) -> List[str]:
    supplier_lookup = _supplier_lookup(state)
    grouped = defaultdict(list)
    for risk in unique_risks(r for r in state.risk_assessments if is_external_risk(r)):
        grouped[_display_label(risk.severity)].append(risk)

    lines = []
    severities = ["Critical", "High", "Medium", "Low"]
    emitted_any = False
    for severity in severities:
        entries = grouped.get(severity, [])
        if not entries and severity == "Critical":
            continue
        lines.append(severity)
        if not entries:
            lines.append("None identified")
        else:
            emitted_any = True
            for index, risk in enumerate(entries, start=1):
                lines.append(f"{index}. {_risk_title(risk)}")
                supplier = _lookup_value(supplier_lookup, risk.supplier_name)
                if supplier:
                    path = _path_for_supplier(supplier)
                    if path != "N/A":
                        lines.append(f"   Affected Path: {path}")
                lines.append(f"   Reason: {_risk_label(risk)}")
                lines.append(f"   Confidence: {risk.confidence:.2f}")
                if risk.mitigation:
                    lines.append(f"   Mitigation: {risk.mitigation}")
                if index != len(entries):
                    lines.append("")
        if severity != severities[-1]:
            lines.append("")
    if not emitted_any:
        lines.extend(["", "No supplier-specific risks detected"])
    return lines


def _critical_supplier_lines(state: AgentState) -> List[str]:
    criticality_map = {}
    for criticality in state.supplier_criticality_scores:
        for key in _name_keys(criticality.supplier_name):
            criticality_map[key] = criticality

    entries = []
    for supplier in state.suppliers:
        criticality = _lookup_value(criticality_map, supplier.name, supplier.canonical_name)
        if not criticality:
            continue
        if criticality.criticality_level in {"Critical", "High"} or criticality.criticality_score >= 0.75:
            entries.append((supplier, criticality))

    entries.sort(key=lambda item: item[1].criticality_score, reverse=True)
    if not entries:
        return ["None identified"]

    lines = []
    for index, (supplier, criticality) in enumerate(entries[:5], start=1):
        lines.append(f"{index}. {supplier.name}")
        lines.append(_field_line("Tier", str(supplier.tier)))
        lines.append(_field_line("Confidence", _confidence_for_supplier(state, supplier)))
        lines.append(_field_line("Reason", criticality.reasoning))
        if index != min(len(entries), 5):
            lines.append("")
    return lines


def _timing_lines(state: AgentState) -> List[str]:
    from utils.runtime_controls import STAGE_ORDER, finish_all_stages, stage_elapsed

    finish_all_stages(state)
    lines = []
    total = 0.0
    for stage_key, label in STAGE_ORDER:
        elapsed = stage_elapsed(state, stage_key)
        total += elapsed
        lines.append(f"{label:<29}: {elapsed:.1f}s")
    lines.extend(["", f"{'Total Runtime':<29}: {total:.1f}s"])
    return lines


def format_report_lines(
    state: AgentState,
    *,
    include_header: bool = True,
    include_timings: bool = True,
    include_footer: bool = True,
) -> List[str]:
    company = state.company.name if state.company else state.target_company or "N/A"
    lines = []

    if include_header:
        lines.extend(
            [
                "=" * 50,
                "SUPPLY CHAIN INTELLIGENCE REPORT",
                "=" * 50,
                "",
            ]
        )

    lines.extend(
        [
            f"Company: {company}",
            f"Mode: {execution_mode_label(state)}",
            f"Generated At: {_generated_at(state)}",
            "",
            "1. EXECUTIVE SUMMARY",
        ]
    )
    lines.extend(_executive_summary_lines(state))

    lines.extend(["", "2. DISCOVERY QUALITY"])
    lines.extend(_discovery_quality_lines(state))

    lines.extend(["", "3. SUPPLY CHAIN HEALTH"])
    lines.extend(_health_lines(state))

    lines.extend(["", "4. SUPPLIER NETWORK"])
    lines.extend(render_supplier_tier_lines(state))

    lines.extend(["", "5. TOP RISKS"])
    lines.extend(_risk_lines(state))

    lines.extend(["", "6. DATA QUALITY WARNINGS"])
    lines.extend(data_quality_warning_lines(state) or ["None identified"])

    lines.extend(["", "7. CRITICAL SUPPLIERS"])
    lines.extend(_critical_supplier_lines(state))

    if include_timings:
        lines.extend(["", "8. PERFORMANCE TIMINGS"])
        lines.extend(_timing_lines(state))

    if include_footer:
        lines.extend(
            [
                "",
                "=" * 50,
                "ANALYSIS COMPLETE",
                "=" * 50,
            ]
        )
    return lines


def render_final_report(state: AgentState, include_header: bool = True) -> None:
    for line in format_report_lines(state, include_header=include_header):
        emit(line)
    if is_debug():
        emit("", OutputMode.DEBUG)
        emit("DEBUG FLAT SUPPLIER LIST", OutputMode.DEBUG)
        if state.suppliers:
            for supplier in state.suppliers:
                emit(f"- {supplier.name}", OutputMode.DEBUG)
        else:
            emit("None identified", OutputMode.DEBUG)
