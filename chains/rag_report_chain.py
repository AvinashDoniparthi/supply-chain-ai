import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from providers.llm_provider import get_llm
from retrieval.vector_store import (
    SOURCE_ANALYSIS_STATE,
    SOURCE_KNOWLEDGE_BASE,
    index_analysis_state,
    retrieve_context,
    retrieve_context_documents,
)


logger = logging.getLogger(__name__)
MISSING_CONTEXT_MESSAGE = "Information not available in retrieved context."
CONTEXT_SECTION_LABELS = {
    "health": "HEALTH CONTEXT",
    "supplier": "SUPPLIER CONTEXT",
    "tier_paths": "TIER PATH CONTEXT",
    "risk": "RISK CONTEXT",
    "recommendation": "RECOMMENDATION CONTEXT",
}


rag_report_prompt = ChatPromptTemplate.from_messages(
    [
            (
                "system",
                (
                    "You are a supply chain intelligence analyst. Synthesize a clean report "
                    "using only the retrieved context provided by the user. Use retrieved "
                    "knowledge-base evidence when available. Use analysis-state evidence only "
                    "as supplementary context. Do not use prior knowledge. Do not infer "
                    "suppliers, risks, locations, products, or recommendations that are not "
                    "explicitly supported by the retrieved context. Do not copy raw retrieved "
                    "lines directly; consolidate and rewrite them into readable analyst "
                    "language. If requested information is missing, write exactly: "
                    f"{MISSING_CONTEXT_MESSAGE}"
                ),
            ),
        (
            "user",
            """Company: {company}

Retrieved context:
{context}

Generate a concise executive supply chain report in exactly this format:

RAG EXECUTIVE SUMMARY
2-4 clean sentences.

SUPPLY CHAIN HEALTH
- Score:
- Status:
- Interpretation:

KEY SUPPLIERS
- Supplier name (Tier, role if available)

TIER DEPENDENCIES
- Path format: Apple -> TSMC -> ASML

MAJOR RISKS
- Risk:
- Affected supplier/path:
- Severity:
- Reason:

RECOMMENDATIONS
- Actionable recommendation

DATA LIMITATIONS
- Mention missing retrieved sections only if not available.
""",
        ),
    ]
)


def _section_queries(company: str) -> Dict[str, str]:
    company_name = (company or "").strip() or "Company"
    return {
        "health": (
            f"{company_name} supply chain health overall score status supplier count "
            "high risk suppliers"
        ),
        "supplier": (
            f"{company_name} key suppliers tier 1 tier 2 tier 3 supplier network"
        ),
        "risk": (
            f"{company_name} major risks geopolitical financial operational supplier "
            "risks mitigation"
        ),
        "recommendation": (
            f"{company_name} recommendations mitigation supply chain diversification "
            "verification"
        ),
    }


def _normalize_chunk(chunk: str) -> str:
    return re.sub(r"\s+", " ", (chunk or "").strip()).lower()


def _deduplicate_section_chunks(
    section_chunks: Dict[str, List[str]],
) -> Tuple[Dict[str, List[str]], List[str]]:
    seen = set()
    unique_by_section: Dict[str, List[str]] = {}
    all_unique: List[str] = []

    for section in CONTEXT_SECTION_LABELS:
        unique_by_section[section] = []
        for chunk in section_chunks.get(section, []):
            text = (chunk or "").strip()
            if not text:
                continue
            normalized = _normalize_chunk(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_by_section[section].append(text)
            all_unique.append(text)

    return unique_by_section, all_unique


def _clean_text_list(values: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", (value or "").strip())
        if text:
            cleaned.append(text)
    return cleaned


def _state_dependency_paths(state: Optional[Any], company: str, limit: int = 12) -> List[str]:
    paths: List[str] = []
    seen = set()

    suppliers = sorted(
        getattr(state, "suppliers", []) or [],
        key=lambda supplier: (-int(getattr(supplier, "tier", 0) or 0), getattr(supplier, "name", "")),
    )

    for supplier in suppliers:
        relationship_path = _clean_text_list(getattr(supplier, "relationship_path", []) or [])
        if relationship_path:
            path = " -> ".join(relationship_path)
        else:
            target = (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).strip()
            path = f"{company} -> {target}" if target else company

        normalized = _normalize_chunk(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(f"- {path}")
        if len(paths) >= limit:
            break

    return paths


def _state_sections(company: str, state: Optional[Any]) -> Dict[str, List[str]]:
    if state is None:
        return {}

    sections: Dict[str, List[str]] = {}

    health = getattr(state, "supply_chain_health", None)
    if health:
        sections["health"] = [
            "\n".join(
                [
                    f"Supply chain health for {company}",
                    f"Overall score: {health.overall_score}",
                    f"Status: {health.status}",
                    f"Supplier count: {health.supplier_count}",
                    f"Critical suppliers: {health.critical_suppliers}",
                    f"High-risk suppliers: {health.high_risk_suppliers}",
                    f"Summary: {health.summary}",
                ]
            )
        ]

    suppliers = []
    for supplier in getattr(state, "suppliers", []) or []:
        suppliers.append(
            "\n".join(
                [
                    f"Supplier: {supplier.name}",
                    f"Canonical name: {supplier.canonical_name or supplier.name}",
                    f"Tier: {supplier.tier}",
                    f"Parent company: {supplier.parent_company or company}",
                    f"Relationship path: {' -> '.join(_clean_text_list(getattr(supplier, 'relationship_path', []) or []) or [company, supplier.name])}",
                    f"Location: {supplier.location}",
                    f"Products: {', '.join(supplier.products) or 'Not available'}",
                    f"Criticality label: {supplier.criticality}",
                    f"Discovery confidence: {supplier.discovery_confidence}",
                    f"Propagated confidence: {supplier.propagated_confidence}",
                ]
            )
        )
    if suppliers:
        sections["supplier"] = suppliers

    tier_paths = _state_dependency_paths(state, company)
    if tier_paths:
        sections["tier_paths"] = tier_paths

    risks = []
    for risk in getattr(state, "risk_assessments", []) or []:
        risks.append(
            "\n".join(
                [
                    f"Risk for {risk.supplier_name}",
                    f"Risk type: {risk.risk_type}",
                    f"Severity: {risk.severity}",
                    f"Confidence: {risk.confidence}",
                    f"Reasoning: {risk.reasoning}",
                    f"Mitigation: {risk.mitigation or 'Not available'}",
                ]
            )
        )
    if risks:
        sections["risk"] = risks

    report = getattr(state, "executive_report", None)
    recommendations = getattr(report, "recommendations", []) if report else []
    if recommendations:
        sections["recommendation"] = [f"Recommendations: {'; '.join(recommendations)}"]
    else:
        recommendation_lines = []
        for risk in getattr(state, "risk_assessments", []) or []:
            mitigation = (getattr(risk, "mitigation", "") or "").strip()
            if mitigation:
                recommendation_lines.append(mitigation)
        if recommendation_lines:
            sections["recommendation"] = recommendation_lines

    return sections


def _merge_section_chunks(
    retrieved_sections: Dict[str, List[str]],
    state_sections: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for section in CONTEXT_SECTION_LABELS:
        merged[section] = [
            *retrieved_sections.get(section, []),
            *state_sections.get(section, []),
        ]
    return merged


def _source_mix(documents: Iterable[Any]) -> Dict[str, int]:
    mix = {SOURCE_KNOWLEDGE_BASE: 0, SOURCE_ANALYSIS_STATE: 0}
    for document in documents:
        metadata = getattr(document, "metadata", {}) or {}
        source_type = metadata.get("source_type")
        if source_type in mix:
            mix[source_type] += 1
    return mix


def _health_document_from_state(company: str, state: Optional[Any]) -> Optional[str]:
    health = getattr(state, "supply_chain_health", None) if state is not None else None
    if not health:
        return None

    return "\n".join(
        [
            f"Supply chain health for {company}",
            f"Overall score: {health.overall_score}",
            f"Status: {health.status}",
            f"Supplier count: {health.supplier_count}",
            f"Critical suppliers: {health.critical_suppliers}",
            f"High-risk suppliers: {health.high_risk_suppliers}",
            f"Summary: {health.summary}",
        ]
    )


def _ensure_health_context(
    company: str, state: Optional[Any], health_chunks: List[str]
) -> List[str]:
    health_document = _health_document_from_state(company, state)
    if not health_document:
        return health_chunks

    health = getattr(state, "supply_chain_health", None)
    score = str(getattr(health, "overall_score", ""))
    has_score = any(
        "overall score" in chunk.lower() or (score and score in chunk)
        for chunk in health_chunks
    )
    if has_score:
        return health_chunks

    logger.debug("RAG health score available in AgentState but absent from retrieved chunks.")
    return [health_document, *health_chunks]


def _format_structured_context(section_chunks: Dict[str, List[str]]) -> str:
    blocks = []
    for section, label in CONTEXT_SECTION_LABELS.items():
        chunks = [chunk.strip() for chunk in section_chunks.get(section, []) if chunk.strip()]
        body = (
            "\n\n".join(f"[{index}] {chunk}" for index, chunk in enumerate(chunks, start=1))
            if chunks
            else MISSING_CONTEXT_MESSAGE
        )
        blocks.append(f"{label}:\n{body}")

    return "\n\n".join(blocks)


def _unique_lines(context_chunks: List[str], pattern: str, limit: int = 8) -> List[str]:
    seen = set()
    matches: List[str] = []
    for chunk in context_chunks:
        for line in chunk.splitlines():
            normalized = line.strip()
            if not normalized or not re.search(pattern, normalized, flags=re.IGNORECASE):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            matches.append(normalized)
            if len(matches) >= limit:
                return matches
    return matches


def _field(chunk: str, label: str) -> Optional[str]:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", chunk, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value and value.lower() != "not available" else None


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _first_available(chunks: Iterable[str], label: str) -> Optional[str]:
    for chunk in chunks:
        value = _field(chunk, label)
        if value:
            return value
    return None


def _clean_supplier_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    name = re.sub(r"^(Supplier|Canonical name|Key suppliers):\s*", "", name).strip()
    return name or None


def _supplier_entries(chunks: List[str], limit: int = 8) -> List[str]:
    entries: List[str] = []
    seen = set()

    for chunk in chunks:
        supplier = _clean_supplier_name(_field(chunk, "Supplier") or _field(chunk, "Canonical name"))
        tier = _field(chunk, "Tier")
        products = _split_csv(_field(chunk, "Products"))
        role = products[0] if products else None

        if not supplier:
            for key_supplier in _split_csv(_field(chunk, "Key suppliers")):
                supplier = _clean_supplier_name(key_supplier)
                if supplier and supplier.lower() not in seen:
                    seen.add(supplier.lower())
                    entries.append(f"- {supplier}")
                    if len(entries) >= limit:
                        return entries
                supplier = None
            continue

        key = supplier.lower()
        if key in seen:
            continue
        seen.add(key)

        details = []
        if tier:
            details.append(f"Tier {tier}")
        if role:
            details.append(role)
        suffix = f" ({', '.join(details)})" if details else ""
        entries.append(f"- {supplier}{suffix}")
        if len(entries) >= limit:
            return entries

    return entries


def _tier_paths(chunks: List[str], limit: int = 8) -> List[str]:
    paths: List[str] = []
    seen = set()
    for chunk in chunks:
        path = _field(chunk, "Relationship path")
        if not path:
            path = _field(chunk, "Affected path")
        if not path or "->" not in path:
            continue
        normalized = _normalize_chunk(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(f"- {path}")
        if len(paths) >= limit:
            break
    return paths


def _risk_entries(chunks: List[str], limit: int = 6) -> List[str]:
    entries: List[str] = []
    seen = set()

    for chunk in chunks:
        risk_for = _field(chunk, "Risk for")
        risk_type = _field(chunk, "Risk type")
        severity = _field(chunk, "Severity")
        reasoning = _field(chunk, "Reasoning")

        if not risk_type and not risk_for:
            major = _field(chunk, "Major risks")
            if major:
                for raw_risk in re.split(r";\s*", major):
                    risk_name = raw_risk.split(":", 1)[0].strip()
                    affected_match = re.search(r"Affected path:\s*([^.;]+)", raw_risk)
                    reason_match = re.search(r"Reason:\s*([^.;]+(?:\.[^;]*)?)", raw_risk)
                    key = _normalize_chunk(raw_risk)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    entries.extend(
                        [
                            f"- Risk: {risk_name or 'Supply-chain risk'}",
                            (
                                "  Affected supplier/path: "
                                f"{affected_match.group(1).strip() if affected_match else MISSING_CONTEXT_MESSAGE}"
                            ),
                            "  Severity: Information not available in retrieved context.",
                            (
                                "  Reason: "
                                f"{reason_match.group(1).strip() if reason_match else MISSING_CONTEXT_MESSAGE}"
                            ),
                        ]
                    )
                    if len(entries) // 4 >= limit:
                        return entries
                continue

        if not risk_type and not reasoning:
            continue

        affected = risk_for or _field(chunk, "Supplier") or MISSING_CONTEXT_MESSAGE
        key = _normalize_chunk("|".join([risk_type or "", affected, severity or "", reasoning or ""]))
        if key in seen:
            continue
        seen.add(key)
        entries.extend(
            [
                f"- Risk: {risk_type or 'Supply-chain risk'}",
                f"  Affected supplier/path: {affected}",
                f"  Severity: {severity or MISSING_CONTEXT_MESSAGE}",
                f"  Reason: {reasoning or MISSING_CONTEXT_MESSAGE}",
            ]
        )
        if len(entries) // 4 >= limit:
            break

    return entries


def _recommendation_entries(chunks: List[str], limit: int = 6) -> List[str]:
    entries: List[str] = []
    seen = set()

    for chunk in chunks:
        candidates = []
        mitigation = _field(chunk, "Mitigation")
        if mitigation:
            candidates.append(mitigation)
        candidates.extend(_split_csv(_field(chunk, "Recommendations")))

        for candidate in candidates:
            normalized = _normalize_chunk(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            entries.append(f"- {candidate}")
            if len(entries) >= limit:
                return entries

    return entries


def _state_lookup_by_name(state: Optional[Any]) -> Dict[str, Any]:
    lookup: Dict[str, Any] = {}
    for supplier in getattr(state, "suppliers", []) or []:
        name = (getattr(supplier, "name", "") or "").strip().lower()
        canonical_name = (getattr(supplier, "canonical_name", "") or "").strip().lower()
        if name:
            lookup[name] = supplier
        if canonical_name:
            lookup[canonical_name] = supplier
    return lookup


def _state_supplier_entries(state: Optional[Any], limit: int = 8) -> List[str]:
    entries: List[str] = []
    seen = set()

    for supplier in getattr(state, "suppliers", []) or []:
        name = (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        details = [f"Tier {getattr(supplier, 'tier', 'N/A')}"]
        products = [p.strip() for p in getattr(supplier, "products", []) or [] if p.strip()]
        if products:
            details.append(products[0])
        elif getattr(supplier, "criticality", None):
            details.append(str(getattr(supplier, "criticality")))
        entries.append(f"- {name} ({', '.join(details)})")
        if len(entries) >= limit:
            break

    return entries


def _state_dependency_paths(state: Optional[Any], company: str, limit: int = 8) -> List[str]:
    paths: List[str] = []
    seen = set()
    for supplier in getattr(state, "suppliers", []) or []:
        relationship_path = [part.strip() for part in getattr(supplier, "relationship_path", []) or [] if part.strip()]
        if relationship_path:
            path = " -> ".join(relationship_path)
        else:
            target = (getattr(supplier, "canonical_name", None) or getattr(supplier, "name", "")).strip()
            path = f"{company} -> {target}" if target else company
        normalized = _normalize_chunk(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(f"- {path}")
        if len(paths) >= limit:
            break
    return paths


def _state_major_risks(state: Optional[Any], limit: int = 5) -> List[str]:
    severity_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    lookup = _state_lookup_by_name(state)
    risks = sorted(
        getattr(state, "risk_assessments", []) or [],
        key=lambda risk: severity_order.get(getattr(risk, "severity", ""), 0),
        reverse=True,
    )

    entries: List[str] = []
    seen = set()
    for risk in risks:
        supplier_name = getattr(risk, "supplier_name", "") or "Unknown supplier"
        supplier = lookup.get(supplier_name.lower())
        path = None
        if supplier is not None:
            relationship_path = [part.strip() for part in getattr(supplier, "relationship_path", []) or [] if part.strip()]
            if relationship_path:
                path = " -> ".join(relationship_path)
            elif getattr(supplier, "canonical_name", None) or getattr(supplier, "name", None):
                path = f"{company_name_or_state(state)} -> {getattr(supplier, 'canonical_name', None) or getattr(supplier, 'name', None)}"
        if not path:
            path = supplier_name

        reasoning = (getattr(risk, "reasoning", "") or "").strip()
        mitigation = (getattr(risk, "mitigation", "") or "").strip()
        key = _normalize_chunk("|".join([supplier_name, getattr(risk, "risk_type", ""), getattr(risk, "severity", ""), reasoning, mitigation]))
        if key in seen:
            continue
        seen.add(key)
        entries.extend(
            [
                f"- Risk: {getattr(risk, 'risk_type', 'Supply-chain risk')}",
                f"  Affected supplier/path: {path}",
                f"  Severity: {getattr(risk, 'severity', MISSING_CONTEXT_MESSAGE)}",
                f"  Reason: {reasoning or MISSING_CONTEXT_MESSAGE}",
            ]
        )
        if len(entries) // 4 >= limit:
            break

    return entries


def _state_recommendations(state: Optional[Any], limit: int = 6) -> List[str]:
    entries: List[str] = []
    seen = set()

    report = getattr(state, "executive_report", None)
    report_recommendations = getattr(report, "recommendations", []) or []
    if report_recommendations:
        source = report_recommendations
    else:
        source = []
        for risk in getattr(state, "risk_assessments", []) or []:
            mitigation = (getattr(risk, "mitigation", "") or "").strip()
            if mitigation:
                source.append(mitigation)
            else:
                source.append(
                    f"Investigate {getattr(risk, 'risk_type', 'risk').lower()} exposure for {getattr(risk, 'supplier_name', 'the supplier')}."
                )
        health = getattr(state, "supply_chain_health", None)
        if health and getattr(health, "supplier_count", 0) == 0:
            source.append("Complete supplier discovery before acting on the health score.")

    for item in source:
        normalized = _normalize_chunk(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        entries.append(f"- {item}")
        if len(entries) >= limit:
            break

    return entries


def company_name_or_state(state: Optional[Any], fallback: str = "Company") -> str:
    return (
        getattr(getattr(state, "company", None), "name", None)
        or getattr(state, "target_company", None)
        or fallback
    )


def _fallback_report(company: str, section_chunks: Dict[str, List[str]], state: Optional[Any] = None) -> str:
    health_chunks = section_chunks.get("health", [])
    supplier_chunks = section_chunks.get("supplier", [])
    risk_chunks = section_chunks.get("risk", [])
    recommendation_chunks = section_chunks.get("recommendation", [])

    health = getattr(state, "supply_chain_health", None)
    report = getattr(state, "executive_report", None)

    score = getattr(health, "overall_score", None) if health else _first_available(health_chunks, "Overall score")
    status = getattr(health, "status", None) if health else _first_available(health_chunks, "Status")
    health_summary = getattr(health, "summary", None) if health else _first_available(health_chunks, "Summary")

    supplier_entries = _state_supplier_entries(state) or _supplier_entries(supplier_chunks)
    path_entries = _state_dependency_paths(state, company) or _tier_paths(supplier_chunks + risk_chunks)
    risk_entries = _state_major_risks(state) or _risk_entries(risk_chunks)
    recommendation_entries = _state_recommendations(state) or _recommendation_entries(recommendation_chunks + risk_chunks)

    supplier_names = [entry[2:].split(" (", 1)[0] for entry in supplier_entries[:3]]
    if report and getattr(report, "major_risks", None):
        risk_labels = [str(item).split(":", 1)[0].strip() for item in report.major_risks[:2]]
    else:
        risk_labels = [
            entry.replace("- Risk: ", "")
            for entry in risk_entries
            if entry.startswith("- Risk:")
        ][:2]
    summary_sentences = []
    if score or status:
        summary_sentences.append(
            f"{company}'s retrieved supply-chain health is {status or 'not stated'}"
            f"{f' with a score of {score}/100' if score else ''}."
        )
    if supplier_names:
        summary_sentences.append(
            f"Key retrieved suppliers include {', '.join(supplier_names)}."
        )
    if risk_labels:
        summary_sentences.append(
            f"The main retrieved risk themes are {', '.join(risk_labels)}."
        )
    if not summary_sentences:
        summary_sentences.append(MISSING_CONTEXT_MESSAGE)

    limitations = []
    if not health_chunks:
        limitations.append("- Health context was not retrieved.")
    if not supplier_chunks:
        limitations.append("- Supplier context was not retrieved.")
    if not section_chunks.get("tier_paths"):
        limitations.append("- Tier path context was not retrieved.")
    if not risk_chunks:
        limitations.append("- Risk context was not retrieved.")
    if not recommendation_chunks:
        limitations.append("- Recommendation context was not retrieved.")
    if not limitations:
        limitations.append("- No missing retrieved sections identified.")

    return "\n".join(
        [
            "RAG EXECUTIVE SUMMARY",
            " ".join(summary_sentences[:4]),
            "",
            "SUPPLY CHAIN HEALTH",
            f"- Score: {score or MISSING_CONTEXT_MESSAGE}",
            f"- Status: {status or MISSING_CONTEXT_MESSAGE}",
            f"- Interpretation: {health_summary or MISSING_CONTEXT_MESSAGE}",
            "",
            "KEY SUPPLIERS",
            *(supplier_entries or [f"- {MISSING_CONTEXT_MESSAGE}"]),
            "",
            "TIER DEPENDENCIES",
            *(path_entries or [f"- {MISSING_CONTEXT_MESSAGE}"]),
            "",
            "MAJOR RISKS",
            *(risk_entries or [f"- {MISSING_CONTEXT_MESSAGE}"]),
            "",
            "RECOMMENDATIONS",
            *(recommendation_entries or [f"- {MISSING_CONTEXT_MESSAGE}"]),
            "",
            "DATA LIMITATIONS",
            *limitations,
        ]
    )


def generate_rag_report(
    company: str,
    *,
    state: Optional[Any] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    k: int = 4,
) -> Tuple[str, List[str]]:
    """
    Retrieve company-specific evidence from ChromaDB and generate a report from it.

    Returns the generated report text and the retrieved context chunks used to
    produce it. When no context is available, the report is the required explicit
    missing-context message.
    """
    if state is not None:
        try:
            index_analysis_state(state, provider=provider)
        except Exception as exc:
            logger.warning("RAG report indexing skipped: %s", exc)

    section_k = min(max(k, 3), 5)
    raw_section_chunks: Dict[str, List[str]] = {}
    retrieved_documents: List[Any] = []
    for section, query in _section_queries(company).items():
        raw_section_chunks[section] = retrieve_context(
            query=query,
            company=company,
            k=section_k,
            source_priority=[SOURCE_KNOWLEDGE_BASE, SOURCE_ANALYSIS_STATE],
            provider=provider,
        )
        documents = retrieve_context_documents(
            query=query,
            company=company,
            k=section_k,
            source_priority=[SOURCE_KNOWLEDGE_BASE, SOURCE_ANALYSIS_STATE],
            provider=provider,
        )
        retrieved_documents.extend(documents)

    raw_section_chunks["health"] = _ensure_health_context(
        company, state, raw_section_chunks.get("health", [])
    )
    state_sections = _state_sections(company, state)
    section_chunks, context_chunks = _deduplicate_section_chunks(
        _merge_section_chunks(raw_section_chunks, state_sections)
    )

    logger.debug("RAG health chunks count: %s", len(section_chunks.get("health", [])))
    logger.debug("RAG supplier chunks count: %s", len(section_chunks.get("supplier", [])))
    logger.debug("RAG tier path chunks count: %s", len(section_chunks.get("tier_paths", [])))
    logger.debug("RAG risk chunks count: %s", len(section_chunks.get("risk", [])))
    logger.debug(
        "RAG recommendation chunks count: %s",
        len(section_chunks.get("recommendation", [])),
    )
    logger.debug("RAG total unique chunks: %s", len(context_chunks))

    source_mix = _source_mix(retrieved_documents)
    if state is not None:
        state.run_metadata["knowledge_base_chunks"] = source_mix[SOURCE_KNOWLEDGE_BASE]
        state.run_metadata["analysis_state_chunks"] = source_mix[SOURCE_ANALYSIS_STATE]
        state.run_metadata["retrieval_chunks_attached"] = len(context_chunks)
        state.run_metadata["retrieval_source_mix"] = source_mix

    if not context_chunks:
        return MISSING_CONTEXT_MESSAGE, []

    try:
        llm = get_llm(provider=provider, model=model)
        chain = rag_report_prompt | llm | StrOutputParser()
        report = chain.invoke(
            {
                "company": company,
                "context": _format_structured_context(section_chunks),
            }
        )
    except Exception as exc:
        logger.warning("RAG report LLM generation skipped: %s", exc)
        return _fallback_report(company, section_chunks, state=state), context_chunks

    report_text = (report or "").strip()
    if state is not None and "TIER DEPENDENCIES" in report_text:
        path_entries = _state_dependency_paths(state, company)
        if path_entries and "MAJOR RISKS" in report_text:
            prefix, rest = report_text.split("TIER DEPENDENCIES", 1)
            _, suffix = rest.split("MAJOR RISKS", 1)
            report_text = (
                prefix
                + "TIER DEPENDENCIES\n"
                + "\n".join(path_entries)
                + "\n\nMAJOR RISKS"
                + suffix
            )
    return report_text or MISSING_CONTEXT_MESSAGE, context_chunks
