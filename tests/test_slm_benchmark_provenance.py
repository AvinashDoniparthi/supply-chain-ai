import unittest

from agents.supplier_agent import supplier_agent
from models.state import AgentState, SupplierInfo
from product_benchmark import CSV_FIELDNAMES
from scraping.supplier_discovery import SupplierDiscoveryScraper
from utils.benchmark_metrics import build_benchmark_record, record_primary_model_result


def _state(*, suppliers=None):
    return AgentState(
        target_company="Apple",
        product_name="iPhone 16 Pro",
        component_name="Application Processor",
        benchmark_target_query="Apple iPhone 16 Pro Application Processor",
        execution_mode="slm",
        provider="ollama",
        model="gemma3:4b",
        supplier_cache_enabled=True,
        suppliers=list(suppliers or []),
    )


def _supplier():
    return SupplierInfo(
        name="Example Supplier",
        canonical_name="Example Supplier",
        location="Unknown",
        tier=1,
        discovery_confidence=0.9,
    )


class SlmBenchmarkProvenanceTest(unittest.TestCase):
    def test_export_schema_contains_model_invocation_fields(self):
        self.assertIn("model_invocation_status", CSV_FIELDNAMES)
        self.assertIn("model_invoked", CSV_FIELDNAMES)

    def test_zero_candidates_are_explicitly_skipped(self):
        record = build_benchmark_record(_state(), "completed")
        self.assertEqual(record["model_invocation_status"], "skipped_no_candidates")
        self.assertIs(record["model_invoked"], False)
        self.assertEqual(record["primary_model_success"], "not_applicable")
        self.assertIs(record["fallback_used"], False)
        self.assertEqual(record["workflow_status"], "completed")

    def test_invoked_success_and_failure_have_distinct_provenance(self):
        success_state = _state(suppliers=[_supplier()])
        record_primary_model_result(
            success_state, stage="relationship_classification", success=True
        )
        success_record = build_benchmark_record(success_state, "completed")
        self.assertEqual(success_record["model_invocation_status"], "succeeded")
        self.assertIs(success_record["model_invoked"], True)
        self.assertIs(success_record["primary_model_success"], True)

        failure_state = _state(suppliers=[_supplier()])
        record_primary_model_result(
            failure_state,
            stage="relationship_classification",
            success=False,
            fallback=True,
        )
        failure_record = build_benchmark_record(failure_state, "completed")
        self.assertEqual(failure_record["model_invocation_status"], "failed")
        self.assertIs(failure_record["model_invoked"], True)
        self.assertIs(failure_record["primary_model_success"], False)

    def test_apple_application_processor_curated_discovery_retains_tsmc(self):
        state = _state()
        discovery = SupplierDiscoveryScraper(runtime_state=state, prefer_curated=True)
        curated = discovery.find_suppliers(state.benchmark_target_query)
        self.assertIn(
            "Taiwan Semiconductor Manufacturing Company",
            [item["name"] for item in curated],
        )

        state.mapping_queue = ["Apple"]
        updated = supplier_agent(state)
        self.assertIn(
            "Taiwan Semiconductor Manufacturing Company",
            [supplier.canonical_name for supplier in updated.suppliers],
        )


if __name__ == "__main__":
    unittest.main()
