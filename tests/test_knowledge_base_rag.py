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
from retrieval.vector_store import (
    SOURCE_KNOWLEDGE_REPORT,
    index_analysis_state,
    retrieve_context,
    retrieve_context_documents,
)


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
    (apple_dir / "apple_supply_chain_report.md").write_text(
        "# Apple\n\n## Report Metadata\n- Generated Timestamp: 2026-07-05T00:00:00+00:00\n- Mode: llm\n- Max Depth: 3\n",
        encoding="utf-8",
    )
    (apple_dir / "apple_supplier_notes.md").write_text(
        "# Apple Supplier Notes\nKnown supplier evidence:\nTODO\n",
        encoding="utf-8",
    )

    documents = load_knowledge_base_documents(base_dir=str(base_dir))

    assert len(documents) == 2
    assert all(doc.metadata["source_type"] == SOURCE_KNOWLEDGE_REPORT for doc in documents)
    assert all(doc.metadata["company"] == "Apple" for doc in documents)
    assert all(doc.metadata["company_key"] == "apple" for doc in documents)
    assert {doc.metadata["file_name"] for doc in documents} == {
        "apple_supply_chain_report.md",
        "apple_supplier_notes.md",
    }
    report = next(doc for doc in documents if doc.metadata["doc_type"] == "knowledge_report")
    assert report.metadata["generated_timestamp"] == "2026-07-05T00:00:00+00:00"
    assert report.metadata["mode"] == "llm"
    assert report.metadata["max_depth"] == "3"
    required = {"company", "product", "component", "tier", "supplier", "source", "publisher", "confidence", "date"}
    assert all(required <= set(doc.metadata) for doc in documents)


def test_indexing_and_retrieval_prefers_knowledge_report(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supply_chain_report.md").write_text(
        "# Apple\n\n## Executive Summary\nApple depends on TSMC.\n\n## Report Metadata\n- Generated Timestamp: 2026-07-05T00:00:00+00:00\n- Mode: rag\n- Max Depth: 3\n",
        encoding="utf-8",
    )

    state = _create_sample_state()
    index_knowledge_base(base_dir=str(base_dir))
    index_analysis_state(state)

    docs = retrieve_context_documents("TSMC supplier note", "Apple", k=4)
    assert len(docs) > 0
    assert docs[0].metadata["source_type"] == SOURCE_KNOWLEDGE_REPORT

    chunks = retrieve_context("TSMC supplier note", "Apple", k=4)
    assert len(chunks) > 0
    assert "Apple depends on TSMC" in chunks[0]


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
    (apple_dir / "apple_supply_chain_report.md").write_text(
        "# Apple\n\n## Executive Summary\nApple depends on TSMC.\n\n## Report Metadata\n- Generated Timestamp: 2026-07-05T00:00:00+00:00\n- Mode: rag\n- Max Depth: 3\n",
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
    assert state.run_metadata["knowledge_report_chunks"] > 0
    assert state.run_metadata["knowledge_base_chunks"] > 0
    assert state.run_metadata["analysis_state_chunks"] > 0
    assert state.run_metadata["retrieval_chunks_attached"] > 0
    assert state.run_metadata["retrieval_source_mix"]["knowledge_report"] > 0
    assert state.run_metadata["retrieval_source_mix"]["analysis_state"] > 0
    assert state.run_metadata["retrieval_status"] == "success"


def test_company_retrieval_never_crosses_company_boundaries(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    for company, text in {
        "Apple": "Apple depends on TSMC for processors.",
        "Tesla": "Tesla depends on Panasonic for batteries.",
        "Samsung": "Samsung sources optics components.",
        "Nvidia": "NVIDIA depends on advanced packaging.",
    }.items():
        company_dir = base_dir / company
        company_dir.mkdir(parents=True)
        (company_dir / f"{company.lower()}_supply_chain_report.md").write_text(
            f"# {company}\n\n{text}\n", encoding="utf-8"
        )
    index_knowledge_base(base_dir=str(base_dir))

    apple = retrieve_context_documents("batteries packaging optics", "Apple", k=10)
    tesla = retrieve_context_documents("processors TSMC", "Tesla", k=10)
    assert apple and all(doc.metadata["company_key"] == "apple" for doc in apple)
    assert tesla and all(doc.metadata["company_key"] == "tesla" for doc in tesla)


def test_missing_company_context_returns_empty(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supply_chain_report.md").write_text("# Apple\nTSMC supplier", encoding="utf-8")
    index_knowledge_base(base_dir=str(base_dir))
    assert retrieve_context_documents("supplier", "Missing Company", k=4) == []
    assert retrieve_context("supplier", "Missing Company", k=4) == []


def test_same_company_fallback_supplements_across_source_types(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    base_dir = tmp_path / "knowledge_base"
    apple_dir = base_dir / "Apple"
    apple_dir.mkdir(parents=True)
    (apple_dir / "apple_supply_chain_report.md").write_text("# Apple\nTSMC supplier", encoding="utf-8")
    index_knowledge_base(base_dir=str(base_dir))
    index_analysis_state(_create_sample_state())
    docs = retrieve_context_documents("Apple supplier health", "Apple", k=6)
    sources = {doc.metadata["source_type"] for doc in docs}
    assert SOURCE_KNOWLEDGE_REPORT in sources
    assert vector_store.SOURCE_ANALYSIS_STATE in sources
    assert all(doc.metadata["company_key"] == "apple" for doc in docs)


def test_product_and_component_filters_are_strict(tmp_path, monkeypatch):
    _configure_vector_store(monkeypatch, tmp_path)
    processor_state = _create_sample_state()
    processor_state.product_name = "iPhone 16 Pro"
    processor_state.component_name = "Application Processor"
    processor_state.supply_chain_health.summary = "PROCESSOR_CONTEXT_ONLY"
    display_state = _create_sample_state()
    display_state.product_name = "iPhone 16 Pro"
    display_state.component_name = "Display"
    display_state.supply_chain_health.summary = "DISPLAY_CONTEXT_ONLY"
    other_product_state = _create_sample_state()
    other_product_state.product_name = "iPhone 15 Pro"
    other_product_state.component_name = "Display"
    other_product_state.supply_chain_health.summary = "OTHER_PRODUCT_CONTEXT_ONLY"

    for state in (processor_state, display_state, other_product_state):
        index_analysis_state(state)

    docs = retrieve_context_documents(
        "Apple supply chain health",
        "Apple",
        k=20,
        product="iPhone 16 Pro",
        component="Display",
    )
    assert docs
    assert all(doc.metadata["company_key"] == "apple" for doc in docs)
    assert all(doc.metadata["product_key"] == "iphone 16 pro" for doc in docs)
    assert all(doc.metadata["component_key"] == "display" for doc in docs)
    text = "\n".join(doc.page_content for doc in docs)
    assert "DISPLAY_CONTEXT_ONLY" in text
    assert "PROCESSOR_CONTEXT_ONLY" not in text
    assert "OTHER_PRODUCT_CONTEXT_ONLY" not in text

    assert retrieve_context_documents(
        "supplier",
        "Apple",
        product="Missing Product",
        component="Display",
    ) == []
