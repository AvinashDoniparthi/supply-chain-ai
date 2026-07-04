from __future__ import annotations

from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import chains.rag_report_chain as rag_report_chain
import retrieval.vector_store as vector_store
from models.state import AgentState, CompanyInfo, SupplyChainHealth
from retrieval.knowledge_base_ingestion import (
    index_knowledge_base,
    load_knowledge_base_documents,
)
from retrieval.vector_store import index_analysis_state, retrieve_context, retrieve_context_documents


class DeterministicEmbeddings(Embeddings):
    vocabulary = [
        "apple",
        "samsung",
        "nvidia",
        "amd",
        "intel",
        "tesla",
        "tsmc",
        "supplier",
        "report",
        "notes",
        "health",
        "assembly",
    ]

    def _embed(self, text: str) -> list[float]:
        normalized = (text or "").lower()
        return [float(normalized.count(term)) for term in self.vocabulary]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _configure_vector_store(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vector_store, "CHROMA_DB_DIR", str(tmp_path / "vector_store"))
    monkeypatch.setattr(vector_store, "_DEFAULT_CHROMA_CACHE", tmp_path / "chroma_cache")
    monkeypatch.setattr(
        vector_store,
        "get_embeddings",
        lambda provider=None: DeterministicEmbeddings(),
    )


def _create_sample_state() -> AgentState:
    state = AgentState(target_company="Apple")
    state.company = CompanyInfo(name="Apple", industry="Consumer electronics")
    state.supply_chain_health = SupplyChainHealth(
        overall_score=72.0,
        status="Moderate",
        supplier_count=1,
        critical_suppliers=1,
        high_risk_suppliers=1,
        summary="Apple depends on TSMC for semiconductor manufacturing.",
    )
    return state


def test_load_knowledge_base_documents_reads_supported_files(tmp_path):
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supplier_notes.md").write_text(
        "# Apple Supplier Notes\nKnown supplier evidence:\nTODO\n",
        encoding="utf-8",
    )
    (apple_dir / "apple_sources.csv").write_text(
        "source,notes\nreport,placeholder row\n",
        encoding="utf-8",
    )

    documents = load_knowledge_base_documents(base_dir=str(base_dir))

    assert len(documents) == 2
    assert all(doc.metadata["source_type"] == "knowledge_base" for doc in documents)
    assert all(doc.metadata["company"] == "Apple" for doc in documents)
    assert all(doc.metadata["company_key"] == "apple" for doc in documents)
    assert {doc.metadata["file_name"] for doc in documents} == {
        "apple_supplier_notes.md",
        "apple_sources.csv",
    }


def test_indexing_and_retrieval_prefers_knowledge_base(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supplier_notes.md").write_text(
        "# Apple Supplier Notes\nKnown supplier evidence:\nTSMC placeholder note.\n",
        encoding="utf-8",
    )

    state = _create_sample_state()
    index_knowledge_base(base_dir=str(base_dir))
    index_analysis_state(state)

    docs = retrieve_context_documents("TSMC supplier note", "Apple", k=4)
    assert len(docs) > 0
    assert docs[0].metadata["source_type"] == "knowledge_base"

    chunks = retrieve_context("TSMC supplier note", "Apple", k=4)
    assert len(chunks) > 0
    assert "TSMC placeholder note" in chunks[0]


def test_retrieval_falls_back_to_analysis_state(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    state = _create_sample_state()
    index_analysis_state(state)

    results = retrieve_context("Apple supply chain health", "Apple", k=4)

    assert len(results) > 0
    assert any("Supply chain health for Apple" in chunk for chunk in results)


def test_rag_report_records_source_mix(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supplier_notes.md").write_text(
        "# Apple Supplier Notes\nKnown supplier evidence:\nTSMC placeholder note.\n",
        encoding="utf-8",
    )

    state = _create_sample_state()
    monkeypatch.setattr(
        rag_report_chain,
        "get_llm",
        lambda provider=None, model=None: RunnableLambda(
            lambda _: AIMessage(content="RAG EXECUTIVE SUMMARY\nPlaceholder report.")
        ),
    )

    index_knowledge_base(base_dir=str(base_dir))
    report, context = rag_report_chain.generate_rag_report("Apple", state=state)

    assert report
    assert len(context) > 0
    assert state.run_metadata["knowledge_base_chunks"] > 0
    assert state.run_metadata["analysis_state_chunks"] > 0
    assert state.run_metadata["retrieval_chunks_attached"] > 0
    assert state.run_metadata["retrieval_source_mix"]["knowledge_base"] > 0
    assert state.run_metadata["retrieval_source_mix"]["analysis_state"] > 0
