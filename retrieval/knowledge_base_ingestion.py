from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from retrieval.vector_store import SOURCE_KNOWLEDGE_BASE, _company_key, _vector_store

logger = logging.getLogger(__name__)

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_csv_file(path: Path) -> str:
    rows: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(", ".join(cell.strip() for cell in row if cell.strip()))
    return "\n".join(line for line in rows if line)


def _read_pdf_file(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception:
            logger.debug("PDF ingestion skipped because no PDF reader is installed: %s", path)
            return ""

    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(part for part in pages if part.strip())
    except Exception as exc:
        logger.warning("Failed to read PDF %s: %s", path, exc)
        return ""


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return _read_text_file(path)
    if suffix == ".csv":
        return _read_csv_file(path)
    if suffix in SUPPORTED_PDF_EXTENSIONS:
        return _read_pdf_file(path)
    return ""


def _company_from_path(base_dir: Path, path: Path) -> Optional[str]:
    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None
    return relative.parts[0]


def load_knowledge_base_documents(base_dir: str = "knowledge_base") -> List[Document]:
    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    documents: List[Document] = []
    for path in sorted(base_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS:
            continue

        company = _company_from_path(base_path, path)
        if not company:
            continue

        content = _read_file(path).strip()
        if not content:
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source_type": SOURCE_KNOWLEDGE_BASE,
                    "company": company,
                    "company_key": _company_key(company),
                    "file_name": path.name,
                    "path": str(path),
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
