import hashlib
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

try:
    from langchain_chroma import Chroma
except ImportError:  # pragma: no cover - current requirements use community package
    from langchain_community.vectorstores import Chroma

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

CHROMA_DB_DIR = "database/vector_store"
COLLECTION_NAME = "supply_chain_knowledge"
_DEFAULT_CHROMA_CACHE = Path("database/chroma_cache")
_LOCAL_EMBEDDING_DIMENSIONS = 384
SOURCE_ANALYSIS_STATE = "analysis_state"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"


class LocalHashEmbeddings(Embeddings):
    """Small offline embedding fallback for deterministic local retrieval."""

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * _LOCAL_EMBEDDING_DIMENSIONS
        tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % _LOCAL_EMBEDDING_DIMENSIONS
            vector[index] += 1.0

        norm = sum(value * value for value in vector) ** 0.5
        if norm:
            return [value / norm for value in vector]
        return vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


def _valid_key(value: Optional[str]) -> bool:
    return bool(value and value not in {"mock-openai-key", "mock-google-key", "mock-key"})


def get_embeddings(provider: Optional[str] = None):
    """Return the requested embedding model, defaulting to a local offline model."""
    selected_provider = (provider or "").lower().strip()

    if selected_provider in {"", "local"}:
        return LocalHashEmbeddings()

    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if selected_provider in {"", "openai"} and _valid_key(openai_key):
        return OpenAIEmbeddings(openai_api_key=openai_key)

    if selected_provider in {"", "google", "gemini"} and _valid_key(google_key):
        return GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=google_key,
        )

    if selected_provider in {"openai", "google", "gemini"}:
        logger.warning(
            "Requested embedding provider %s has no valid API key; using local embeddings.",
            selected_provider,
        )

    return LocalHashEmbeddings()


def _vector_store(provider: Optional[str] = None) -> Chroma:
    Path(CHROMA_DB_DIR).mkdir(parents=True, exist_ok=True)
    _DEFAULT_CHROMA_CACHE.mkdir(parents=True, exist_ok=True)

    # Chroma's default embedding function uses this path when no API key exists.
    # Keep it inside the writable project tree.
    try:
        from chromadb.utils import embedding_functions

        embedding_functions.ONNXMiniLM_L6_V2.DOWNLOAD_PATH = (
            _DEFAULT_CHROMA_CACHE / "all-MiniLM-L6-v2"
        )
    except Exception:
        logger.debug("Unable to override Chroma default embedding cache.", exc_info=True)

    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DB_DIR,
        embedding_function=get_embeddings(provider=provider),
    )


def _company_name(state: Any) -> str:
    company = getattr(state, "company", None)
    return (
        getattr(company, "name", None)
        or getattr(state, "target_company", None)
        or "Unknown Company"
    )


def _company_key(company: str) -> str:
    return (company or "").lower().strip()


def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in metadata.items() if value is not None}


def _document(
    company: str,
    doc_type: str,
    content: str,
    *,
    source_type: str,
    supplier: Optional[str] = None,
    tier: Optional[int] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Document]:
    text = (content or "").strip()
    if not text:
        return None

    metadata: Dict[str, Any] = {
        "company": company,
        "company_key": _company_key(company),
        "doc_type": doc_type,
        "source_type": source_type,
        "supplier": supplier,
        "tier": tier,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return Document(
        page_content=text,
        metadata=_clean_metadata(metadata),
    )


def _evidence_text(evidence: Iterable[Dict[str, Any]]) -> str:
    snippets = []
    for item in evidence or []:
        title = item.get("title")
        snippet = item.get("snippet")
        link = item.get("link")
        parts = [part for part in [title, snippet, link] if part]
        if parts:
            snippets.append(" | ".join(str(part) for part in parts))
    return "\n".join(snippets)


def _build_documents(state: Any) -> List[Document]:
    company = _company_name(state)
    documents: List[Document] = []

    company_info = getattr(state, "company", None)
    if company_info:
        documents.append(
            _document(
                company,
                "company_profile",
                "\n".join(
                    [
                        f"Company profile: {getattr(company_info, 'name', company)}",
                        f"Industry: {getattr(company_info, 'industry', None) or 'Not available'}",
                        f"Headquarters: {getattr(company_info, 'headquarters', None) or 'Not available'}",
                        f"Description: {getattr(company_info, 'description', None) or 'Not available'}",
                        f"Website: {getattr(company_info, 'website', None) or 'Not available'}",
                    ]
                ),
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for supplier in getattr(state, "suppliers", []) or []:
        path = " -> ".join(getattr(supplier, "relationship_path", []) or [])
        documents.append(
            _document(
                company,
                "supplier",
                "\n".join(
                    [
                        f"Supplier: {supplier.name}",
                        f"Canonical name: {supplier.canonical_name or supplier.name}",
                        f"Tier: {supplier.tier}",
                        f"Parent company: {supplier.parent_company or company}",
                        f"Relationship path: {path or company + ' -> ' + supplier.name}",
                        f"Location: {supplier.location}",
                        f"Products: {', '.join(supplier.products) or 'Not available'}",
                        f"Criticality label: {supplier.criticality}",
                        f"Discovery confidence: {supplier.discovery_confidence}",
                        f"Propagated confidence: {supplier.propagated_confidence}",
                        f"Evidence: {_evidence_text(supplier.evidence) or 'Not available'}",
                    ]
                ),
                supplier=supplier.name,
                tier=supplier.tier,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for relationship in getattr(state, "relationship_results", []) or []:
        documents.append(
            _document(
                company,
                "tier_path",
                "\n".join(
                    [
                        f"Tier path / relationship for {relationship.candidate_company}",
                        f"Target: {relationship.target_company}",
                        f"Candidate: {relationship.candidate_company}",
                        f"Relationship type: {relationship.relationship_type}",
                        f"Confidence: {relationship.confidence_score}",
                        f"Reasoning: {relationship.reasoning}",
                        f"Evidence: {relationship.evidence_text}",
                    ]
                ),
                supplier=relationship.candidate_company,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for verification in getattr(state, "verification_results", []) or []:
        documents.append(
            _document(
                company,
                "verification",
                "\n".join(
                    [
                        f"Verification result for {verification.supplier_name}",
                        f"Relationship type: {verification.relationship_type}",
                        f"Verified: {verification.verified}",
                        f"Company exists: {verification.company_exists}",
                        f"Relationship verified: {verification.relationship_verified}",
                        f"Evidence quality: {verification.evidence_quality}",
                        f"Source quality: {verification.source_quality}",
                        f"Confidence score: {verification.confidence_score}",
                        f"Website: {verification.website or 'Not available'}",
                        f"Headquarters: {verification.headquarters or 'Not available'}",
                        f"Evidence sources: {', '.join(verification.evidence_sources) or 'Not available'}",
                        f"Reasoning: {verification.reasoning}",
                    ]
                ),
                supplier=verification.supplier_name,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for risk in getattr(state, "risk_assessments", []) or []:
        documents.append(
            _document(
                company,
                "risk",
                "\n".join(
                    [
                        f"Risk for {risk.supplier_name}",
                        f"Risk type: {risk.risk_type}",
                        f"Severity: {risk.severity}",
                        f"Confidence: {risk.confidence}",
                        f"Reasoning: {risk.reasoning}",
                        f"Mitigation: {risk.mitigation or 'Not available'}",
                    ]
                ),
                supplier=risk.supplier_name,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for score in getattr(state, "supplier_confidence_scores", []) or []:
        documents.append(
            _document(
                company,
                "confidence",
                "\n".join(
                    [
                        f"Confidence score for {score.supplier_name}",
                        f"Discovery confidence: {score.discovery_confidence}",
                        f"Relationship confidence: {score.relationship_confidence}",
                        f"Verification confidence: {score.verification_confidence}",
                        f"Risk confidence: {score.risk_confidence}",
                        f"Final confidence: {score.final_confidence}",
                        f"Reasoning: {score.reasoning}",
                    ]
                ),
                supplier=score.supplier_name,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    for score in getattr(state, "supplier_criticality_scores", []) or []:
        documents.append(
            _document(
                company,
                "criticality",
                "\n".join(
                    [
                        f"Criticality score for {score.supplier_name}",
                        f"Criticality score: {score.criticality_score}",
                        f"Criticality level: {score.criticality_level}",
                        f"Reasoning: {score.reasoning}",
                    ]
                ),
                supplier=score.supplier_name,
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    health = getattr(state, "supply_chain_health", None)
    if health:
        documents.append(
            _document(
                company,
                "health",
                "\n".join(
                    [
                        f"Supply chain health for {company}",
                        f"Health score: {health.overall_score}",
                        f"Health status: {health.status}",
                        f"Overall score: {health.overall_score}",
                        f"Status: {health.status}",
                        f"Supplier count: {health.supplier_count}",
                        f"Critical suppliers: {health.critical_suppliers}",
                        f"High-risk suppliers: {health.high_risk_suppliers}",
                        f"Summary: {health.summary}",
                    ]
                ),
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    report = getattr(state, "executive_report", None)
    if report:
        documents.append(
            _document(
                company,
                "executive_report",
                "\n".join(
                    [
                        f"Executive report for {report.company_name}",
                        f"Overall health score: {report.overall_health_score}",
                        f"Health status: {report.health_status}",
                        f"Key suppliers: {', '.join(report.key_suppliers) or 'Not available'}",
                        f"Major risks: {'; '.join(report.major_risks) or 'Not available'}",
                        f"Recommendations: {'; '.join(report.recommendations) or 'Not available'}",
                        f"Executive summary: {report.executive_summary}",
                    ]
                ),
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    historical_runs = getattr(state, "historical_runs", []) or []
    if historical_runs:
        history_lines = [f"Historical trend summary for {company}"]
        for run in historical_runs:
            history_lines.append(
                (
                    f"{run.timestamp}: mode={run.mode}, health={run.health_score} "
                    f"({run.health_status}), suppliers={run.supplier_count}, risks={run.risk_count}, "
                    f"supplier names={', '.join(run.suppliers)}"
                )
            )
        documents.append(
            _document(
                company,
                "history",
                "\n".join(history_lines),
                source_type=SOURCE_ANALYSIS_STATE,
            )
        )

    return [document for document in documents if document is not None]


def _document_id(company: str, document: Document, index: int) -> str:
    raw = "|".join(
        [
            company,
            str(document.metadata.get("source_type", "")),
            str(document.metadata.get("doc_type", "")),
            str(document.metadata.get("supplier", "")),
            str(document.metadata.get("tier", "")),
            str(document.metadata.get("path", "")),
            str(document.metadata.get("file_name", "")),
            document.page_content,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] + f"-{index}"


def _search_documents(
    vector_store: Chroma,
    query: str,
    *,
    k: int,
    company_key: Optional[str] = None,
    source_type: Optional[str] = None,
) -> List[Document]:
    search_filters: List[Dict[str, Any]] = []
    primary_filter: Dict[str, Any] = {}
    if company_key:
        primary_filter["company_key"] = company_key
    if source_type:
        primary_filter["source_type"] = source_type
    if primary_filter:
        search_filters.append(primary_filter)

    fallback_filter: Dict[str, Any] = {}
    if source_type:
        fallback_filter["source_type"] = source_type
    if fallback_filter and fallback_filter not in search_filters:
        search_filters.append(fallback_filter)

    if {} not in search_filters:
        search_filters.append({})

    for search_filter in search_filters:
        kwargs: Dict[str, Any] = {"k": k}
        if search_filter:
            kwargs["filter"] = search_filter
        try:
            documents = vector_store.similarity_search(query, **kwargs)
        except Exception as exc:
            logger.debug(
                "Filtered retrieval failed for company_key=%s source_type=%s: %s",
                company_key,
                source_type,
                exc,
            )
            continue
        if documents:
            return documents
    return []


def _retrieve_documents(
    query: str,
    company: str,
    *,
    k: int = 8,
    source_priority: Optional[Sequence[str]] = None,
    provider: Optional[str] = None,
) -> List[Document]:
    vector_store = _vector_store(provider=provider)
    collection = getattr(vector_store, "_collection", None)
    collection_count: Optional[int] = None
    if collection is not None:
        try:
            collection_count = collection.count()
        except Exception:
            logger.debug("Unable to count Chroma collection before search.", exc_info=True)

    company_key = _company_key(company)
    logger.debug("RAG retrieval query: %s", query)
    logger.debug("RAG retrieval requested company filter: %s", company_key)
    logger.debug("RAG Chroma collection count before search: %s", collection_count)

    if collection_count == 0:
        logger.debug("RAG retrieval skipped because Chroma collection is empty.")
        return []

    sources = list(source_priority or [SOURCE_KNOWLEDGE_BASE, SOURCE_ANALYSIS_STATE])
    if SOURCE_KNOWLEDGE_BASE not in sources:
        sources.insert(0, SOURCE_KNOWLEDGE_BASE)
    if SOURCE_ANALYSIS_STATE not in sources:
        sources.append(SOURCE_ANALYSIS_STATE)

    documents: List[Document] = []
    seen = set()
    remaining = max(k, 0)
    for source_type in sources:
        if remaining <= 0:
            break
        source_documents = _search_documents(
            vector_store,
            query,
            k=remaining,
            company_key=company_key or None,
            source_type=source_type,
        )
        for document in source_documents:
            content = (document.page_content or "").strip()
            if not content:
                continue
            normalized = re.sub(r"\s+", " ", content).strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            documents.append(document)
            remaining -= 1
            if remaining <= 0:
                break

    return documents


def index_analysis_state(state: Any, provider: Optional[str] = None) -> Chroma:
    """Convert the completed AgentState into documents and persist them in ChromaDB."""
    vector_store = _vector_store(provider=provider)
    documents = _build_documents(state)
    company = _company_name(state)
    doc_types = sorted(
        {
            str(document.metadata.get("doc_type"))
            for document in documents
            if document.metadata.get("doc_type")
        }
    )

    logger.debug("RAG indexing company: %s", company)
    logger.debug("RAG indexing document count: %s", len(documents))
    logger.debug("RAG indexing document types: %s", doc_types)

    if not documents:
        logger.debug("No RAG documents produced for indexing.")
        return vector_store

    ids = [_document_id(company, document, index) for index, document in enumerate(documents)]
    vector_store.add_documents(documents, ids=ids)
    persist = getattr(vector_store, "persist", None)
    if callable(persist):
        persist()

    collection = getattr(vector_store, "_collection", None)
    if collection is not None:
        try:
            logger.debug("RAG Chroma collection count after insertion: %s", collection.count())
        except Exception:
            logger.debug("Unable to count RAG Chroma collection after insertion.", exc_info=True)

    logger.debug("Indexed %s RAG documents into Chroma.", len(documents))
    return vector_store


def retrieve_context(
    query: str,
    company: str,
    k: int = 8,
    source_priority: Optional[Sequence[str]] = None,
    provider: Optional[str] = None,
) -> List[str]:
    """Return top-k relevant text chunks for a company, or [] if retrieval is unavailable."""
    try:
        documents = _retrieve_documents(
            query,
            company,
            k=k,
            source_priority=source_priority,
            provider=provider,
        )
        logger.debug("RAG retrieval results: %s", len(documents))
    except Exception as exc:
        logger.warning("RAG retrieval unavailable: %s", exc)
        return []

    return [(document.page_content or "").strip() for document in documents if (document.page_content or "").strip()]


def retrieve_context_documents(
    query: str,
    company: str,
    k: int = 8,
    source_priority: Optional[Sequence[str]] = None,
    provider: Optional[str] = None,
) -> List[Document]:
    try:
        return _retrieve_documents(
            query,
            company,
            k=k,
            source_priority=source_priority,
            provider=provider,
        )
    except Exception as exc:
        logger.warning("RAG retrieval unavailable: %s", exc)
        return []


def index_analysis(state: Any, provider: Optional[str] = None):
    """Backward-compatible wrapper for older imports."""
    return index_analysis_state(state, provider=provider)


def search_analysis(
    query: str, provider: Optional[str] = None, company: Optional[str] = None
):
    """Backward-compatible search wrapper returning Document objects."""
    try:
        if company:
            return retrieve_context_documents(query, company, k=6, provider=provider)
        return retrieve_context_documents(query, "", k=6, provider=provider)
    except Exception as exc:
        logger.warning("RAG search unavailable: %s", exc)
        return []
