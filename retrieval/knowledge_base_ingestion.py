from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from retrieval.vector_store import (
    SOURCE_KNOWLEDGE_REPORT,
    _company_key,
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


def _is_knowledge_report(path: Path) -> bool:
    return path.name.endswith("_supply_chain_report.md")


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

        if not _is_knowledge_report(path):
            continue

        content = _read_file(path).strip()
        if not content:
            continue

        report_metadata = _extract_report_metadata(content)

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source_type": SOURCE_KNOWLEDGE_REPORT,
                    "company": company,
                    "company_key": _company_key(company),
                    "file_name": path.name,
                    "path": str(path),
                    "generated_timestamp": report_metadata.get("generated_timestamp"),
                    "mode": report_metadata.get("mode"),
                    "max_depth": report_metadata.get("max_depth"),
                    "doc_type": "knowledge_report",
                },
            )
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
        ids = [
            f"kb-{chunk.metadata.get('company_key', '')}-{chunk.metadata.get('file_name', '')}-{chunk.metadata.get('chunk_index', 0)}"
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
