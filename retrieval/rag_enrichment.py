import logging
import re
from typing import Any, Dict, Iterable, List

from models.state import AgentState, SupplierInfo
from retrieval.vector_store import index_analysis, search_analysis

logger = logging.getLogger(__name__)


def rag_enabled(state: AgentState) -> bool:
    return getattr(state, "execution_mode", "llm") == "rag"


def _evidence_key(evidence: Dict[str, str]) -> tuple[str, str]:
    return (evidence.get("link", ""), evidence.get("snippet", ""))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "chunk"


def _document_to_evidence(document: Any, supplier_name: str) -> Dict[str, str]:
    metadata = getattr(document, "metadata", {}) or {}
    page_content = getattr(document, "page_content", "") or ""
    title = metadata.get("name") or metadata.get("supplier") or metadata.get("company")
    if not title:
        title = f"Retrieved evidence for {supplier_name}"
    return {
        "title": f"RAG: {title}",
        "link": f"rag://chroma/{_slug(str(title))}",
        "snippet": page_content[:1000],
    }


def _extend_supplier_evidence(
    supplier: SupplierInfo, retrieved_evidence: Iterable[Dict[str, str]]
) -> int:
    existing = {_evidence_key(evidence) for evidence in supplier.evidence}
    added = 0
    for evidence in retrieved_evidence:
        key = _evidence_key(evidence)
        if key in existing:
            continue
        supplier.evidence.append(evidence)
        existing.add(key)
        added += 1
    return added


def enrich_supplier_evidence_with_rag(
    state: AgentState, stage: str, max_chunks_per_supplier: int = 3
) -> AgentState:
    if not rag_enabled(state) or not state.suppliers:
        return state

    try:
        index_analysis(state)
    except Exception as exc:
        logger.warning("RAG indexing skipped during %s: %s", stage, exc)
        state.history.append(
            {
                "agent": "rag_enrichment",
                "action": "index_analysis",
                "stage": stage,
                "mode": state.execution_mode,
                "status": "skipped",
                "reason": str(exc),
            }
        )
        return state

    total_added = 0
    retrieved_by_supplier: Dict[str, List[Dict[str, str]]] = {}
    for supplier in state.suppliers:
        query_parts = [
            state.target_company or "",
            supplier.parent_company or "",
            supplier.canonical_name or supplier.name,
            supplier.name,
            "supplier relationship evidence",
        ]
        query = " ".join(part for part in query_parts if part).strip()
        if not query:
            continue

        try:
            documents = search_analysis(query)[:max_chunks_per_supplier]
        except Exception as exc:
            logger.warning("RAG retrieval skipped for %s during %s: %s", supplier.name, stage, exc)
            continue

        evidence = [_document_to_evidence(document, supplier.name) for document in documents]
        added = _extend_supplier_evidence(supplier, evidence)
        if added:
            total_added += added
            retrieved_by_supplier[supplier.canonical_name or supplier.name] = evidence[:added]

    state.retrieved_evidence.update(retrieved_by_supplier)
    state.run_metadata["mode"] = state.execution_mode
    state.run_metadata["retrieval_chunks_attached"] = (
        int(state.run_metadata.get("retrieval_chunks_attached", 0)) + total_added
    )
    state.history.append(
        {
            "agent": "rag_enrichment",
            "action": "retrieve_evidence",
            "stage": stage,
            "mode": state.execution_mode,
            "chunks_attached": total_added,
            "status": "success",
        }
    )
    return state
