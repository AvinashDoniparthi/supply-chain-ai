import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

# Keep local imports stable when pytest is launched without PYTHONPATH.
os.environ.setdefault("PYTHONPATH", root_str)


@pytest.fixture(autouse=True)
def isolate_runtime_writes(tmp_path, monkeypatch):
    """Keep workflow side effects out of tracked production artifact folders."""
    import agents.graph_export_agent as graph_module
    import agents.history_agent as history_module
    import product_benchmark
    import retrieval.knowledge_report_generator as report_generator
    import retrieval.vector_store as vector_store

    benchmark_dir = tmp_path / "product_level"
    monkeypatch.setattr(graph_module, "DEFAULT_GRAPH_EXPORT_DIR", str(tmp_path / "graphs"))
    monkeypatch.setattr(history_module, "DEFAULT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(report_generator, "KNOWLEDGE_BASE_DIR", tmp_path / "knowledge_base")
    monkeypatch.setattr(vector_store, "CHROMA_DB_DIR", str(tmp_path / "vector_store"))
    monkeypatch.setattr(vector_store, "_DEFAULT_CHROMA_CACHE", tmp_path / "chroma_cache")
    monkeypatch.setattr(product_benchmark, "OUTPUT_DIR", benchmark_dir)
    monkeypatch.setattr(
        product_benchmark,
        "GLOBAL_MASTER_CSV_PATH",
        benchmark_dir / "all_samples_master_results.csv",
    )
    monkeypatch.setattr(
        product_benchmark,
        "SCHEMA_MIGRATION_REPORT_PATH",
        benchmark_dir / "schema_migration_report.md",
    )
