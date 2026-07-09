from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from models.state import AgentState
from utils.identity_resolution import resolver


KNOWLEDGE_BASE_DIR = Path("knowledge_base")


def _company_name(state: AgentState) -> str:
    company = getattr(state, "company", None)
    return (
        getattr(company, "name", None)
        or getattr(state, "target_company", None)
        or "Unknown Company"
    )


def _company_slug(company: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (company or "").lower()).strip("_")
    return slug or "unknown_company"


def _name_keys(*values: Optional[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        if not value:
            continue
        cleaned = value.strip()
        if not cleaned:
            continue
        canonical = resolver.resolve(cleaned)
        keys.update(
            {
                cleaned.lower(),
                canonical.lower(),
                cleaned,
                canonical,
            }
        )
        keys.update(alias.lower() for alias in resolver.aliases_for(canonical))
    return {key for key in keys if key}


def _first_matching(
    mapping: Dict[str, object],
    *names: Optional[str],
) -> Optional[object]:
    for name in names:
        for key in _name_keys(name):
            if key in mapping:
                return mapping[key]
    return None


def _verification_lookup(state: AgentState) -> Dict[str, object]:
    lookup: Dict[str, object] = {}
    for item in getattr(state, "verification_results", []) or []:
        for key in _name_keys(
            getattr(item, "supplier_name", None),
        ):
            lookup[key] = item
    return lookup


def _confidence_lookup(state: AgentState) -> Dict[str, object]:
    lookup: Dict[str, object] = {}
    for item in getattr(state, "supplier_confidence_scores", []) or []:
        for key in _name_keys(getattr(item, "supplier_name", None)):
            lookup[key] = item
    return lookup


def _criticality_lookup(state: AgentState) -> Dict[str, object]:
    lookup: Dict[str, object] = {}
    for item in getattr(state, "supplier_criticality_scores", []) or []:
        for key in _name_keys(getattr(item, "supplier_name", None)):
            lookup[key] = item
    return lookup


def _relationship_lookup(state: AgentState) -> Dict[str, object]:
    lookup: Dict[str, object] = {}
    for item in getattr(state, "relationship_results", []) or []:
        for key in _name_keys(
            getattr(item, "candidate_company", None),
            getattr(item, "supplier_name", None),
        ):
            lookup[key] = item
    return lookup


def _format_value(value: Optional[object], fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _bullet_block(value: str, fallback: str = "Not available.") -> List[str]:
    text = (value or "").strip() or fallback
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [f"- {line}" for line in lines] if lines else [f"- {fallback}"]


def _format_confidence(value: Optional[float]) -> str:
    if value is None:
        return "Not available"
    return f"{value:.2f}"


def _supplier_confidence(
    supplier_name: str,
    confidence_lookup: Dict[str, object],
    supplier: object,
) -> str:
    score = _first_matching(confidence_lookup, supplier_name)
    if score is not None:
        return _format_confidence(getattr(score, "final_confidence", None))

    discovery = getattr(supplier, "discovery_confidence", None)
    propagated = getattr(supplier, "propagated_confidence", None)
    if propagated is not None and propagated > 0:
        return _format_confidence(propagated)
    return _format_confidence(discovery)


def _verification_text(
    supplier_name: str,
    verification_lookup: Dict[str, object],
) -> str:
    result = _first_matching(verification_lookup, supplier_name)
    if result is None:
        return "Not verified"

    verified = bool(getattr(result, "verified", False))
    confidence = getattr(result, "confidence_score", None)
    label = "Verified" if verified else "Not verified"
    if confidence is None:
        return label
    return f"{label} ({confidence:.2f})"


def _verification_summary(state: AgentState) -> Tuple[int, int, int, List[str]]:
    verified = 0
    not_verified = 0
    suppliers: List[str] = []
    seen = set()
    for item in getattr(state, "verification_results", []) or []:
        name = getattr(item, "supplier_name", None) or ""
        canonical = resolver.resolve(name) if name else ""
        key = canonical.lower() or name.lower()
        if key in seen:
            continue
        seen.add(key)
        if getattr(item, "verified", False):
            verified += 1
            suppliers.append(name)
        else:
            not_verified += 1
    total = verified + not_verified
    return total, verified, not_verified, suppliers


def _supplier_entries_by_tier(
    state: AgentState,
    tier: int,
    *,
    verification_lookup: Dict[str, object],
    confidence_lookup: Dict[str, object],
    relationship_lookup: Dict[str, object],
) -> List[str]:
    company = _company_name(state)
    suppliers = sorted(
        [
            supplier
            for supplier in getattr(state, "suppliers", []) or []
            if int(getattr(supplier, "tier", 0) or 0) == tier
        ],
        key=lambda supplier: (
            (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).lower(),
        ),
    )

    if not suppliers:
        return ["- None verified"]

    lines: List[str] = []
    for supplier in suppliers:
        supplier_name = getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")
        relationship = _first_matching(
            relationship_lookup,
            supplier_name,
            getattr(supplier, "name", None),
        )
        relationship_type = (
            getattr(relationship, "relationship_type", None)
            if relationship is not None
            else ("supplier" if tier == 1 else "upstream_supplier")
        )
        path = [part.strip() for part in getattr(supplier, "relationship_path", []) or [] if part.strip()]
        if not path:
            parent = getattr(supplier, "parent_company", None) or company
            path = [company, parent, supplier_name] if tier > 1 else [company, supplier_name]

        lines.extend(
            [
                f"- Supplier: {supplier_name}",
                f"  - Parent: {_format_value(getattr(supplier, 'parent_company', None) or company)}",
                f"  - Relationship Path: {' -> '.join(path)}",
                f"  - Relationship: {_format_value(relationship_type)}",
                f"  - Confidence: {_supplier_confidence(supplier_name, confidence_lookup, supplier)}",
                f"  - Verification: {_verification_text(supplier_name, verification_lookup)}",
            ]
        )
    return lines


def _major_risk_lines(state: AgentState) -> List[str]:
    risks = sorted(
        getattr(state, "risk_assessments", []) or [],
        key=lambda risk: {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(
            getattr(risk, "severity", ""),
            0,
        ),
        reverse=True,
    )
    if not risks:
        return ["- None verified"]

    lines: List[str] = []
    for risk in risks:
        lines.extend(
            [
                f"- Risk Type: {_format_value(getattr(risk, 'risk_type', None))}",
                f"  - Affected Supplier: {_format_value(getattr(risk, 'supplier_name', None))}",
                f"  - Severity: {_format_value(getattr(risk, 'severity', None))}",
                f"  - Reason: {_format_value(getattr(risk, 'reasoning', None))}",
                f"  - Mitigation: {_format_value(getattr(risk, 'mitigation', None))}",
            ]
        )
    return lines


def _critical_supplier_lines(
    state: AgentState,
    criticality_lookup: Dict[str, object],
) -> List[str]:
    suppliers = sorted(
        getattr(state, "suppliers", []) or [],
        key=lambda supplier: (
            -float(
                getattr(
                    _first_matching(
                        criticality_lookup,
                        getattr(supplier, "canonical_name", None),
                        getattr(supplier, "name", None),
                    ),
                    "criticality_score",
                    0.0,
                )
                or 0.0
            ),
            (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).lower(),
        ),
    )
    lines: List[str] = []
    for supplier in suppliers:
        supplier_name = getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")
        criticality = _first_matching(
            criticality_lookup,
            supplier_name,
            getattr(supplier, "name", None),
        )
        if criticality is None:
            continue
        level = getattr(criticality, "criticality_level", None)
        score = getattr(criticality, "criticality_score", None)
        lines.append(
            f"- {supplier_name} ({_format_value(level)}, {_format_confidence(score)})"
        )
    return lines or ["- None verified"]


def _confidence_summary_lines(
    state: AgentState,
    confidence_lookup: Dict[str, object],
) -> List[str]:
    suppliers = sorted(
        getattr(state, "suppliers", []) or [],
        key=lambda supplier: (
            (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).lower(),
        ),
    )
    if not suppliers:
        return ["- None verified"]

    lines: List[str] = []
    for supplier in suppliers:
        supplier_name = getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")
        confidence = _first_matching(
            confidence_lookup,
            supplier_name,
            getattr(supplier, "name", None),
        )
        if confidence is None:
            continue
        lines.append(
            f"- {supplier_name}: {_format_confidence(getattr(confidence, 'final_confidence', None))}"
        )
    return lines or ["- None verified"]


def _verification_summary_lines(
    state: AgentState,
    verification_lookup: Dict[str, object],
) -> List[str]:
    total, verified_count, not_verified_count, verified_suppliers = _verification_summary(state)
    lines = [
        f"- Total Verifications: {total}",
        f"- Verified Supplier Count: {verified_count}",
        f"- Not Verified Count: {not_verified_count}",
    ]
    if verified_suppliers:
        unique = []
        seen = set()
        for name in verified_suppliers:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(name)
        lines.append(f"- Verified Suppliers: {', '.join(unique)}")
    else:
        lines.append("- Verified Suppliers: None")
    return lines


def _supply_chain_health_lines(state: AgentState) -> List[str]:
    health = getattr(state, "supply_chain_health", None)
    if not health:
        return [
            "- Health Score: Not available",
            "- Status: Not available",
            "- Supplier Count: 0",
            "- Verified Supplier Count: 0",
        ]

    verified_count = sum(1 for item in getattr(state, "verification_results", []) or [] if getattr(item, "verified", False))
    return [
        f"- Health Score: {_format_confidence(getattr(health, 'overall_score', None))}",
        f"- Status: {_format_value(getattr(health, 'status', None))}",
        f"- Supplier Count: {_format_value(getattr(health, 'supplier_count', None))}",
        f"- Verified Supplier Count: {verified_count}",
    ]


def generate_knowledge_report(state: AgentState) -> Path:
    company = _company_name(state)
    timestamp = datetime.now(timezone.utc).isoformat()
    mode = getattr(state, "execution_mode", "llm")
    max_depth = getattr(state, "max_depth", 3)

    verification_lookup = _verification_lookup(state)
    confidence_lookup = _confidence_lookup(state)
    criticality_lookup = _criticality_lookup(state)
    relationship_lookup = _relationship_lookup(state)

    executive_summary = getattr(getattr(state, "executive_report", None), "executive_summary", None)
    if not executive_summary:
        executive_summary = "Not available."

    lines: List[str] = [
        f"# {company}",
        "",
        "## Executive Summary",
        *_bullet_block(executive_summary, "Not available."),
        "",
        "## Supply Chain Health",
        *_supply_chain_health_lines(state),
        "",
        "## Tier 1 Suppliers",
        *_supplier_entries_by_tier(
            state,
            1,
            verification_lookup=verification_lookup,
            confidence_lookup=confidence_lookup,
            relationship_lookup=relationship_lookup,
        ),
        "",
        "## Tier 2 Suppliers",
        *_supplier_entries_by_tier(
            state,
            2,
            verification_lookup=verification_lookup,
            confidence_lookup=confidence_lookup,
            relationship_lookup=relationship_lookup,
        ),
        "",
        "## Tier 3 Suppliers",
        *_supplier_entries_by_tier(
            state,
            3,
            verification_lookup=verification_lookup,
            confidence_lookup=confidence_lookup,
            relationship_lookup=relationship_lookup,
        ),
        "",
        "## Major Risks",
        *_major_risk_lines(state),
        "",
        "## Critical Suppliers",
        *_critical_supplier_lines(state, criticality_lookup),
        "",
        "## Verification Summary",
        *_verification_summary_lines(state, verification_lookup),
        "",
        "## Confidence Summary",
        *_confidence_summary_lines(state, confidence_lookup),
        "",
        "## Report Metadata",
        f"- Generated Timestamp: {timestamp}",
        f"- Mode: {mode}",
        f"- Max Depth: {max_depth}",
    ]

    output_dir = KNOWLEDGE_BASE_DIR / company
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_company_slug(company)}_supply_chain_report.md"
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path
