import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models.state import AgentState, SupplierInfo
import main
import product_benchmark


def _supplier(name: str, tier: int) -> SupplierInfo:
    return SupplierInfo(
        name=name,
        canonical_name=name,
        location="Test Location",
        products=["Test Product"],
        tier=tier,
        criticality="High",
        status="Active",
        discovery_confidence=0.95,
        propagated_confidence=0.95,
        parent_company="Apple",
        relationship_path=["Apple", name],
    )


def _state_for_component(component: str, suppliers: list[SupplierInfo]) -> AgentState:
    return AgentState(
        target_company="Apple",
        product_name="iPhone 16 Pro",
        component_name=component,
        benchmark_target_query=f"Apple iPhone 16 Pro {component}",
        suppliers=suppliers,
        run_metadata={"mode": "llm"},
    )


class ProductComponentBenchmarkTests(unittest.TestCase):
    def test_run_analysis_populates_component_state(self) -> None:
        captured = {}

        def fake_invoke(state: AgentState) -> AgentState:
            captured["state"] = state
            return state

        with patch("main.supply_chain_app.invoke", side_effect=fake_invoke), patch(
            "main.generate_knowledge_report", return_value=Path("/tmp/report.md")
        ), patch("main.index_knowledge_base"), patch("main.render_final_report"):
            state = main.run_analysis(
                "Apple",
                product="iPhone 16 Pro",
                component="Application Processor",
                benchmark_target_query="Apple iPhone 16 Pro Application Processor",
            )

        initial_state = captured["state"]
        self.assertEqual(initial_state.product_name, "iPhone 16 Pro")
        self.assertEqual(initial_state.component_name, "Application Processor")
        self.assertEqual(
            initial_state.benchmark_target_query,
            "Apple iPhone 16 Pro Application Processor",
        )
        self.assertEqual(state.component_name, "Application Processor")

    def test_run_single_uses_component_context_in_target_query(self) -> None:
        captured = {}

        def fake_run_analysis(company_name: str, **kwargs):
            captured["company_name"] = company_name
            captured["kwargs"] = kwargs
            return _state_for_component(
                kwargs["component"],
                [_supplier("TSMC", 1)],
            )

        with patch.object(product_benchmark, "_run_analysis", side_effect=fake_run_analysis):
            result = product_benchmark._run_single(
                company="Apple",
                product="iPhone 16 Pro",
                component="Application Processor",
                sample_id=99,
                sample_label="component_debug",
                mode="llm",
                max_depth=3,
                skip_news=True,
                reference_suppliers=[],
            )

        self.assertEqual(captured["company_name"], "Apple")
        self.assertEqual(captured["kwargs"]["product"], "iPhone 16 Pro")
        self.assertEqual(captured["kwargs"]["component"], "Application Processor")
        self.assertEqual(
            captured["kwargs"]["benchmark_target_query"],
            "Apple iPhone 16 Pro Application Processor",
        )
        self.assertEqual(result["tier1_suppliers"], "TSMC")
        self.assertEqual(result["component"], "Application Processor")

    def test_missing_component_evidence_returns_insufficient_status(self) -> None:
        state = _state_for_component("Assembly", [])
        result = product_benchmark.calculate_component_metrics(
            company="Apple",
            product="iPhone 16 Pro",
            component="Assembly",
            sample_id=99,
            sample_label="component_debug",
            timestamp="2026-07-09T00:00:00+00:00",
            mode="llm",
            max_depth=3,
            skip_news=True,
            state=state,
            runtime_seconds=1.23,
            error=None,
            reference_suppliers=[],
        )

        self.assertEqual(
            result["evaluation_status"],
            product_benchmark.EVALUATION_STATUS_INSUFFICIENT_COMPONENT_SUPPLIER_EVIDENCE,
        )
        self.assertEqual(result["tier1_suppliers"], "not_available")
        self.assertEqual(result["evaluation_note"], "No component-specific supplier evidence found.")

    def test_component_specific_runs_do_not_reuse_identical_suppliers(self) -> None:
        component_states = {
            "Application Processor": _state_for_component(
                "Application Processor",
                [_supplier("TSMC", 1), _supplier("ASML", 2)],
            ),
            "Display": _state_for_component(
                "Display",
                [_supplier("Samsung Display", 1), _supplier("LG Display", 1), _supplier("Corning", 2)],
            ),
            "Camera Sensor": _state_for_component(
                "Camera Sensor",
                [_supplier("Sony Semiconductor Solutions", 1), _supplier("ASML", 2)],
            ),
            "Assembly": _state_for_component(
                "Assembly",
                [_supplier("Foxconn", 1), _supplier("Pegatron", 1), _supplier("Luxshare", 1)],
            ),
        }

        def fake_run_analysis(company_name: str, **kwargs):
            return component_states[kwargs["component"]]

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            product_benchmark, "OUTPUT_DIR", Path(tmpdir)
        ), patch.object(
            product_benchmark, "GLOBAL_MASTER_CSV_PATH", Path(tmpdir) / "all_samples_master_results.csv"
        ), patch.object(
            product_benchmark, "REFERENCE_DATASET_PATH", Path(tmpdir) / "missing_reference.csv"
        ), patch.object(
            product_benchmark, "_run_analysis", side_effect=fake_run_analysis
        ), patch.object(
            product_benchmark, "PRODUCT_COMPONENT_MAP",
            {"Apple": {"product": "iPhone 16 Pro", "components": list(component_states.keys())}},
        ):
            rows, sample_dir, master_csv_path, global_csv_path, company_csv_paths = (
                product_benchmark.run_product_benchmark(
                    sample_id=99,
                    sample_label="component_debug",
                    companies=["Apple"],
                    modes=["llm"],
                    max_depth=3,
                    skip_news=True,
                    overwrite=True,
                )
            )

            company_rows = [row for row in rows if row["company"] == "Apple"]
            tier1_lists = {row["component"]: row["tier1_suppliers"] for row in company_rows}
            self.assertGreater(len(set(tier1_lists.values())), 1)
            self.assertEqual(
                tier1_lists["Application Processor"],
                "TSMC",
            )
            self.assertEqual(
                tier1_lists["Display"],
                "Samsung Display; LG Display",
            )
            self.assertEqual(
                tier1_lists["Camera Sensor"],
                "Sony Semiconductor Solutions",
            )
            self.assertEqual(
                tier1_lists["Assembly"],
                "Foxconn; Pegatron; Luxshare",
            )

            csv_text = company_csv_paths[0].read_text(encoding="utf-8")
            self.assertIn("TSMC", csv_text)
            self.assertIn("Samsung Display; LG Display", csv_text)
            self.assertIn("Sony Semiconductor Solutions", csv_text)
            self.assertIn("Foxconn; Pegatron; Luxshare", csv_text)

            summary_text = (sample_dir / "sample_summary.md").read_text(encoding="utf-8")
            self.assertNotIn(
                "WARNING: Component outputs appear identical. Component context may not be influencing discovery.",
                summary_text,
            )
            self.assertTrue(master_csv_path.exists())
            self.assertTrue(global_csv_path.exists())


if __name__ == "__main__":
    unittest.main()
