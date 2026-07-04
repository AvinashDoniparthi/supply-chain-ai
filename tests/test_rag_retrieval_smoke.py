from langchain_core.embeddings import Embeddings

import retrieval.vector_store as vector_store
from models.state import (
    AgentState,
    CompanyInfo,
    ExecutiveReport,
    RiskAnalysis,
    SupplierInfo,
    SupplyChainHealth,
)
from retrieval.vector_store import index_analysis_state, retrieve_context


class DeterministicEmbeddings(Embeddings):
    vocabulary = ["apple", "tsmc", "supplier", "risk", "semiconductor", "manufacturing"]

    def _embed(self, text: str) -> list[float]:
        normalized = text.lower()
        return [float(normalized.count(term)) for term in self.vocabulary]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def test_rag_retrieval_returns_context_for_indexed_company(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_store, "CHROMA_DB_DIR", str(tmp_path / "vector_store"))
    monkeypatch.setattr(vector_store, "_DEFAULT_CHROMA_CACHE", tmp_path / "chroma_cache")
    monkeypatch.setattr(
        vector_store,
        "get_embeddings",
        lambda provider=None: DeterministicEmbeddings(),
    )

    state = AgentState(target_company="Apple")
    state.company = CompanyInfo(name="Apple", industry="Consumer electronics")
    state.suppliers = [
        SupplierInfo(
            name="TSMC",
            canonical_name="Taiwan Semiconductor Manufacturing Company",
            location="Taiwan",
            products=["Semiconductor manufacturing"],
            tier=1,
            criticality="High",
            discovery_confidence=0.9,
            propagated_confidence=0.9,
            evidence=[
                {
                    "title": "Supplier evidence",
                    "link": "curated://apple-tsmc",
                    "snippet": "TSMC is a semiconductor manufacturing supplier for Apple.",
                }
            ],
        )
    ]
    state.risk_assessments = [
        RiskAnalysis(
            supplier_name="TSMC",
            risk_type="Geopolitical",
            severity="High",
            confidence=0.8,
            reasoning="Apple has supplier concentration risk around TSMC manufacturing.",
            mitigation="Diversify semiconductor manufacturing capacity.",
        )
    ]
    state.supply_chain_health = SupplyChainHealth(
        overall_score=72.0,
        status="Moderate",
        supplier_count=1,
        critical_suppliers=1,
        high_risk_suppliers=1,
        summary="Apple depends on TSMC for semiconductor manufacturing.",
    )
    state.executive_report = ExecutiveReport(
        company_name="Apple",
        overall_health_score=72.0,
        health_status="Moderate",
        executive_summary="Apple has supplier risk tied to TSMC.",
        key_suppliers=["TSMC"],
        major_risks=["TSMC: Geopolitical risk"],
        recommendations=["Monitor TSMC concentration risk."],
    )

    index_analysis_state(state)
    results = retrieve_context("Apple TSMC supplier risk", "Apple")

    assert len(results) > 0
