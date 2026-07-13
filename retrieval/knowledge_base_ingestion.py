from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from retrieval.vector_store import (
    SOURCE_KNOWLEDGE_REPORT,
    _company_key,
    _context_key,
    _vector_store,
)

logger = logging.getLogger(__name__)

SUPPORTED_TEXT_EXTENSIONS = {".md"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md"}:
        return _read_text_file(path)
    return ""


def _company_from_path(base_dir: Path, path: Path) -> Optional[str]:
    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None
    return relative.parts[0]


def _document_type(path: Path) -> str:
    if path.name.endswith("_supply_chain_report.md"):
        return "knowledge_report"
    return "knowledge_note"


def _extract_report_metadata(content: str) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    in_metadata = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line == "## Report Metadata":
            in_metadata = True
            continue
        if in_metadata and line.startswith("## "):
            break
        if not in_metadata or not line.startswith("- "):
            continue
        key_value = line[2:]
        if ":" not in key_value:
            continue
        key, value = key_value.split(":", 1)
        normalized_key = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
        if normalized_key:
            metadata[normalized_key] = value.strip()
    return metadata


def _confidence_value(value: Optional[str]) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return {"high": 0.9, "medium": 0.7, "low": 0.4}.get(
            str(value or "").strip().lower(), 0.0
        )


def _supplier_note_rows(
    content: str, *, company: str, path: Path
) -> List[Document]:
    documents: List[Document] = []
    for record_index, line in enumerate(content.splitlines(), start=1):
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0].lower() == "supplier":
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        supplier, component, tier_raw, summary, title, source_url, confidence = cells[:7]
        try:
            tier = int(tier_raw)
        except ValueError:
            continue
        publisher = urlparse(source_url).netloc or company
        documents.append(
            Document(
                page_content=(
                    f"Company: {company}\nSupplier: {supplier}\nTier: {tier}\n"
                    f"Product/component: {component}\nRelationship: {summary}\n"
                    f"Public reference: {title} | {source_url}"
                ),
                metadata={
                    "source_type": SOURCE_KNOWLEDGE_REPORT,
                    "company": company,
                    "company_key": _company_key(company),
                    "file_name": path.name,
                    "path": str(path),
                    "record_index": record_index,
                    "generated_timestamp": "not_available",
                    "mode": "not_available",
                    "max_depth": "not_available",
                    "doc_type": "supplier_evidence",
                    "product": "not_available",
                    "product_key": "not_available",
                    "component": component or "not_available",
                    "component_key": _context_key(component) or "not_available",
                    "tier": tier,
                    "supplier": supplier,
                    "source": source_url or str(path),
                    "publisher": publisher,
                    "confidence": _confidence_value(confidence),
                    "date": "not_available",
                },
            )
        )
    return documents


def load_knowledge_base_documents(base_dir: str = "knowledge_base") -> List[Document]:
    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    documents: List[Document] = []
    for path in sorted(base_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
            continue

        company = _company_from_path(base_path, path)
        if not company:
            continue

        content = _read_file(path).strip()
        if not content:
            continue

        report_metadata = _extract_report_metadata(content)
        product = report_metadata.get("product") or "not_available"
        component = report_metadata.get("component") or "not_available"
        generated_timestamp = report_metadata.get("generated_timestamp") or "not_available"
        source_date = generated_timestamp.split("T", 1)[0] if generated_timestamp != "not_available" else "not_available"

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source_type": SOURCE_KNOWLEDGE_REPORT,
                    "company": company,
                    "company_key": _company_key(company),
                    "file_name": path.name,
                    "path": str(path),
                    "generated_timestamp": generated_timestamp,
                    "mode": report_metadata.get("mode") or "not_available",
                    "max_depth": report_metadata.get("max_depth") or "not_available",
                    "doc_type": _document_type(path),
                    "product": product,
                    "product_key": _context_key(product) or "not_available",
                    "component": component,
                    "component_key": _context_key(component) or "not_available",
                    "tier": 0,
                    "supplier": "not_available",
                    "source": str(path),
                    "publisher": report_metadata.get("publisher") or company,
                    "confidence": _confidence_value(report_metadata.get("confidence")),
                    "date": source_date,
                },
            )
        )
        if _document_type(path) == "knowledge_note":
            documents.extend(
                _supplier_note_rows(content, company=company, path=path)
            )

    return documents


def index_knowledge_base(base_dir: str = "knowledge_base", provider: Optional[str] = None):
    base_path = Path(base_dir)
    documents = load_knowledge_base_documents(base_dir=base_dir)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
    vector_store = _vector_store(provider=provider)

    chunked_documents: List[Document] = []
    for document in documents:
        chunks = splitter.split_documents([document])
        for index, chunk in enumerate(chunks):
            metadata: Dict[str, Any] = dict(document.metadata)
            metadata["chunk_index"] = index
            metadata["chunk_count"] = len(chunks)
            chunked_documents.append(
                Document(page_content=chunk.page_content, metadata=metadata)
            )

    if chunked_documents:
        collection = getattr(vector_store, "_collection", None)
        if collection is not None:
            # A full KB index is a deterministic replacement of prior KB chunks;
            # removing the old source type prevents stale chunks surviving when a
            # report becomes shorter or is deleted.
            try:
                collection.delete(where={"source_type": SOURCE_KNOWLEDGE_REPORT})
            except Exception:
                logger.warning("Unable to remove stale knowledge-base chunks before indexing.", exc_info=True)
        ids = [
            f"kb-{chunk.metadata.get('company_key', '')}-{chunk.metadata.get('file_name', '')}-{chunk.metadata.get('record_index', 'document')}-{chunk.metadata.get('chunk_index', 0)}"
            for chunk in chunked_documents
        ]
        vector_store.add_documents(chunked_documents, ids=ids)
        persist = getattr(vector_store, "persist", None)
        if callable(persist):
            persist()

    collection = getattr(vector_store, "_collection", None)
    collection_count = None
    if collection is not None:
        try:
            collection_count = collection.count()
        except Exception:
            logger.debug("Unable to count Chroma collection after KB indexing.", exc_info=True)

    print(f"Knowledge base files loaded: {len(documents)}")
    print(f"Knowledge base chunks created: {len(chunked_documents)}")
    print(
        "Chroma collection count after indexing: "
        + (str(collection_count) if collection_count is not None else "unavailable")
    )
    return vector_store


def reindex_knowledge_base(base_dir: str = "knowledge_base", provider: Optional[str] = None):
    return index_knowledge_base(base_dir=base_dir, provider=provider)
