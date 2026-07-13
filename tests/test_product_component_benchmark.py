import csv
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
    def test_reference_dataset_has_one_supplier_per_row_and_verified_rows_have_sources(self) -> None:
        with product_benchmark.REFERENCE_DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(row=row):
                self.assertNotIn(";", row["reference_supplier"])
                self.assertNotIn(";", row["canonical_supplier_name"])
                if row["verification_status"] == "verified":
                    self.assertNotEqual(row["source_url"], "not_available")
                    self.assertNotEqual(row["source_title"], "not_available")
                    self.assertNotEqual(row["source_publisher"], "not_available")

    def test_tier_rows_with_verified_data_have_required_paths(self) -> None:
        with product_benchmark.REFERENCE_DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            if row["verification_status"] != "verified":
                continue
            with self.subTest(row=row):
                if row["tier"] == "2":
                    self.assertNotEqual(row["parent_supplier"], "not_available")
                    self.assertNotEqual(row["relationship_path"], "not_available")
                if row["tier"] == "3":
                    self.assertNotEqual(row["parent_supplier"], "not_available")
                    self.assertNotEqual(row["relationship_path"], "not_available")

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

    def test_missing_reference_returns_not_evaluable_status(self) -> None:
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
            product_benchmark.EVALUATION_STATUS_NOT_EVALUABLE_MISSING_REFERENCE,
        )
        self.assertEqual(result["tier1_suppliers"], "not_available")
        self.assertEqual(
            result["evaluation_note"],
            "Tier-1 metrics are not evaluable because no verified reference is available.",
        )

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

            for row in company_rows:
                self.assertIn("tier2_discovered_suppliers", row)
                self.assertIn("tier3_discovered_suppliers", row)
                self.assertNotIn("tier2_precision", row)
                self.assertNotIn("tier3_precision", row)
                self.assertIn("tier2_verification_status", row)
                self.assertIn("tier3_verification_status", row)

            csv_text = company_csv_paths[0].read_text(encoding="utf-8")
            self.assertIn("TSMC", csv_text)
            self.assertIn("Samsung Display; LG Display", csv_text)
            self.assertIn("Sony Semiconductor Solutions", csv_text)
            self.assertIn("Foxconn; Pegatron; Luxshare", csv_text)
            self.assertIn("tier2_discovered_suppliers", csv_text)
            self.assertIn("tier3_discovered_suppliers", csv_text)

            summary_text = (sample_dir / "sample_summary.md").read_text(encoding="utf-8")
            self.assertIn("Quantitative evaluation was performed only for Tier 1 supplier relationships", summary_text)
            self.assertIn("Tier 2 and Tier 3 supplier relationships were evaluated qualitatively", summary_text)
            self.assertNotIn(
                "WARNING: Component outputs appear identical. Component context may not be influencing discovery.",
                summary_text,
            )
            self.assertTrue(master_csv_path.exists())
            self.assertTrue(global_csv_path.exists())

    def test_quota_exhausted_rows_are_marked(self) -> None:
        with patch.object(
            product_benchmark, "_run_analysis", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        ):
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
                fast_benchmark=True,
            )

        self.assertEqual(result["evaluation_status"], product_benchmark.EVALUATION_STATUS_QUOTA_EXHAUSTED)
        self.assertEqual(result["evaluation_note"], "Quota exhausted during analysis; partial results captured.")

    def test_placeholder_rows_are_excluded_from_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_path = Path(tmpdir) / "reference.csv"
            with ref_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "company",
                        "product",
                        "component",
                        "tier",
                        "reference_supplier",
                        "canonical_supplier_name",
                        "parent_supplier",
                        "relationship_path",
                        "relationship_type",
                        "source_title",
                        "source_url",
                        "source_publisher",
                        "source_date",
                        "source_type",
                        "evidence_summary",
                        "confidence_level",
                        "verification_status",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "company": "Apple",
                        "product": "iPhone 16 Pro",
                        "component": "Application Processor",
                        "tier": "1",
                        "reference_supplier": "TSMC",
                        "canonical_supplier_name": "Taiwan Semiconductor Manufacturing Company",
                        "parent_supplier": "Apple",
                        "relationship_path": "Apple -> Taiwan Semiconductor Manufacturing Company",
                        "relationship_type": "supplier",
                        "source_title": "Example source",
                        "source_url": "https://example.com/source",
                        "source_publisher": "Example",
                        "source_date": "2024-09-10",
                        "source_type": "reputable_news",
                        "evidence_summary": "Verified row.",
                        "confidence_level": "high",
                        "verification_status": "verified",
                        "notes": "Verified row.",
                    }
                )
                writer.writerow(
                    {
                        "company": "Apple",
                        "product": "iPhone 16 Pro",
                        "component": "Application Processor",
                        "tier": "1",
                        "reference_supplier": "not_available",
                        "canonical_supplier_name": "not_available",
                        "parent_supplier": "not_available",
                        "relationship_path": "not_available",
                        "relationship_type": "not_available",
                        "source_title": "not_available",
                        "source_url": "not_available",
                        "source_publisher": "not_available",
                        "source_date": "not_available",
                        "source_type": "not_available",
                        "evidence_summary": "No sufficiently reliable public evidence found.",
                        "confidence_level": "medium",
                        "verification_status": "insufficient_public_evidence",
                        "notes": "No sufficiently reliable public evidence found.",
                    }
                )

            with patch.object(product_benchmark, "REFERENCE_DATASET_PATH", ref_path):
                reference_rows = product_benchmark._load_reference_dataset()
                tiered = product_benchmark._reference_suppliers_for_component(
                    reference_rows, "Apple", "iPhone 16 Pro", "Application Processor"
                )
                self.assertEqual(tiered[1], ["Taiwan Semiconductor Manufacturing Company"])
                self.assertEqual(tiered[2], [])
                self.assertEqual(tiered[3], [])

                state = _state_for_component("Application Processor", [_supplier("TSMC", 1)])
                metrics = product_benchmark.calculate_component_metrics(
                    company="Apple",
                    product="iPhone 16 Pro",
                    component="Application Processor",
                    sample_id=99,
                    sample_label="component_debug",
                    timestamp="2026-07-09T00:00:00+00:00",
                    mode="llm",
                    max_depth=3,
                    skip_news=True,
                    state=state,
                    runtime_seconds=1.23,
                    error=None,
                    reference_suppliers=tiered[1],
                )
                self.assertEqual(metrics["precision"], 100.0)
                self.assertEqual(metrics["recall"], 100.0)
                self.assertEqual(metrics["f1_score"], 100.0)
                self.assertEqual(metrics["hallucination_rate"], 0.0)
                self.assertEqual(metrics["coverage_score"], 100.0)
                self.assertNotIn("tier2_precision", metrics)
                self.assertEqual(metrics["tier2_discovered_suppliers"], "not_available")
                self.assertEqual(metrics["tier3_discovered_suppliers"], "not_available")

    def test_reference_metrics_compute_tp_fp_fn_and_scores(self) -> None:
        metrics = product_benchmark._reference_metrics(
            discovered=["TSMC", "ASML"],
            reference=["Taiwan Semiconductor Manufacturing Company"],
        )

        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["false_positives"], 1)
        self.assertEqual(metrics["false_negatives"], 0)
        self.assertEqual(metrics["precision"], 50.0)
        self.assertEqual(metrics["recall"], 100.0)
        self.assertEqual(metrics["f1_score"], 66.67)
        self.assertEqual(metrics["hallucination_rate"], 50.0)
        self.assertEqual(metrics["coverage_score"], 100.0)

    def test_metrics_return_not_available_when_reference_data_is_missing(self) -> None:
        state = _state_for_component("Application Processor", [_supplier("TSMC", 1)])
        metrics = product_benchmark.calculate_component_metrics(
            company="Apple",
            product="iPhone 16 Pro",
            component="Application Processor",
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

        self.assertEqual(metrics["precision"], "not_available")
        self.assertEqual(metrics["recall"], "not_available")
        self.assertEqual(metrics["f1_score"], "not_available")
        self.assertEqual(metrics["hallucination_rate"], "not_available")
        self.assertEqual(metrics["coverage_score"], "not_available")
        self.assertEqual(metrics["tier2_discovered_suppliers"], "not_available")
        self.assertEqual(metrics["tier3_discovered_suppliers"], "not_available")

    def test_tier2_and_tier3_do_not_reduce_tier1_precision(self) -> None:
        state = _state_for_component(
            "Application Processor",
            [_supplier("TSMC", 1), _supplier("ASML", 2), _supplier("Zeiss", 3)],
        )
        metrics = product_benchmark.calculate_component_metrics(
            company="Apple", product="iPhone 16 Pro", component="Application Processor",
            sample_id=199, sample_label="test", timestamp="2026-07-13T00:00:00+00:00",
            mode="rag", max_depth=3, skip_news=True, state=state,
            runtime_seconds=1.0, error=None,
            reference_suppliers=["Taiwan Semiconductor Manufacturing Company"],
        )
        self.assertEqual(metrics["precision"], 100.0)
        self.assertEqual(metrics["recall"], 100.0)
        self.assertEqual(metrics["f1_score"], 100.0)
        self.assertEqual(metrics["hallucination_rate"], 0.0)
        self.assertEqual(
            metrics["evaluation_status"],
            product_benchmark.EVALUATION_STATUS_QUANTITATIVELY_EVALUATED,
        )

    def test_verified_reference_with_no_discovery_is_still_quantitatively_evaluated(self) -> None:
        metrics = product_benchmark.calculate_component_metrics(
            company="Samsung", product="Galaxy S25 Ultra", component="Application Processor",
            sample_id=199, sample_label="test", timestamp="x", mode="llm", max_depth=3,
            skip_news=True, state=_state_for_component("Application Processor", []),
            runtime_seconds=1.0, error=None, reference_suppliers=["Qualcomm"],
        )
        self.assertEqual(
            metrics["evaluation_status"],
            product_benchmark.EVALUATION_STATUS_QUANTITATIVELY_EVALUATED,
        )
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)

    def test_extra_tier1_supplier_is_false_positive(self) -> None:
        state = _state_for_component(
            "Application Processor", [_supplier("TSMC", 1), _supplier("Broadcom", 1)]
        )
        metrics = product_benchmark.calculate_component_metrics(
            company="Apple", product="iPhone 16 Pro", component="Application Processor",
            sample_id=199, sample_label="test", timestamp="x", mode="llm", max_depth=3,
            skip_news=True, state=state, runtime_seconds=1.0, error=None,
            reference_suppliers=["TSMC"],
        )
        self.assertEqual(metrics["precision"], 50.0)
        self.assertEqual(metrics["hallucination_rate"], 50.0)

    def test_missed_tier1_reference_is_false_negative(self) -> None:
        state = _state_for_component("Application Processor", [_supplier("TSMC", 1)])
        metrics = product_benchmark.calculate_component_metrics(
            company="Apple", product="iPhone 16 Pro", component="Application Processor",
            sample_id=199, sample_label="test", timestamp="x", mode="llm", max_depth=3,
            skip_news=True, state=state, runtime_seconds=1.0, error=None,
            reference_suppliers=["TSMC", "Broadcom"],
        )
        self.assertEqual(metrics["recall"], 50.0)
        self.assertEqual(metrics["coverage_score"], 50.0)

    def test_overwrite_removes_all_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            product_benchmark, "OUTPUT_DIR", Path(tmpdir)
        ), patch.object(
            product_benchmark, "GLOBAL_MASTER_CSV_PATH", Path(tmpdir) / "all_samples_master_results.csv"
        ), patch.object(product_benchmark, "REFERENCE_DATASET_PATH", Path(tmpdir) / "missing.csv"), patch.object(
            product_benchmark, "_run_analysis", return_value=_state_for_component("Application Processor", [_supplier("TSMC", 1)])
        ), patch.object(
            product_benchmark, "PRODUCT_COMPONENT_MAP",
            {"Apple": {"product": "iPhone 16 Pro", "components": ["Application Processor"]}},
        ):
            sample_dir = product_benchmark.get_sample_output_dir(199, "overwrite")
            sample_dir.mkdir(parents=True)
            for name in ("stale_company.csv", "master_results.csv", "sample_summary.md"):
                (sample_dir / name).write_text("stale", encoding="utf-8")
            product_benchmark.run_product_benchmark(
                sample_id=199, sample_label="overwrite", companies=["Apple"], modes=["llm"],
                max_depth=3, skip_news=True, overwrite=True,
            )
            self.assertFalse((sample_dir / "stale_company.csv").exists())
            self.assertNotEqual((sample_dir / "master_results.csv").read_text(), "stale")
            self.assertNotEqual((sample_dir / "sample_summary.md").read_text(), "stale")

    def test_non_overwrite_preserves_collision_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(product_benchmark, "OUTPUT_DIR", Path(tmpdir)):
            product_benchmark.get_sample_output_dir(199, "collision").mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                product_benchmark._run_sample_benchmark(
                    sample_id=199, sample_label="collision", companies=[], modes=[], max_depth=3,
                    skip_news=True, overwrite=False,
                )

    def test_overwrite_rejects_unsafe_deletion_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            unsafe = Path(tmpdir) / "outside"
            unsafe.mkdir()
            with patch.object(product_benchmark, "OUTPUT_DIR", Path(tmpdir) / "product_level"), patch.object(
                product_benchmark, "get_sample_output_dir", return_value=unsafe
            ):
                with self.assertRaises(ValueError):
                    product_benchmark._run_sample_benchmark(
                        sample_id=199, sample_label="unsafe", companies=[], modes=[], max_depth=3,
                        skip_news=True, overwrite=True,
                    )

    def test_persistence_failure_marks_partial_success(self) -> None:
        state = _state_for_component("Application Processor", [_supplier("TSMC", 1)])
        state.errors.append("Graph export failed")
        metrics = product_benchmark.calculate_component_metrics(
            company="Apple", product="iPhone 16 Pro", component="Application Processor",
            sample_id=199, sample_label="test", timestamp="x", mode="llm", max_depth=3,
            skip_news=True, state=state, runtime_seconds=1.0, error=None,
            reference_suppliers=["TSMC"],
        )
        self.assertEqual(metrics["evaluation_status"], product_benchmark.EVALUATION_STATUS_PARTIAL_SUCCESS)

    def test_schema_migration_cli_does_not_require_benchmark_arguments(self) -> None:
        report_path = Path("migration-report.md")
        with patch.object(
            product_benchmark,
            "migrate_product_benchmark_schema",
            return_value=report_path,
        ) as migrate, patch("sys.argv", ["product_benchmark.py", "--migrate-schema"]):
            self.assertEqual(product_benchmark.main(), 0)
        migrate.assert_called_once_with()

    def test_component_rows_remain_distinct_across_components(self) -> None:
        with product_benchmark.REFERENCE_DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        apple_rows = [row for row in rows if row["company"] == "Apple" and row["verification_status"] == "verified"]
        self.assertEqual({row["component"] for row in apple_rows}, {"Application Processor", "Assembly"})
        samsung_rows = [row for row in rows if row["company"] == "Samsung" and row["verification_status"] == "verified"]
        self.assertEqual({row["component"] for row in samsung_rows}, {"Application Processor"})


if __name__ == "__main__":
    unittest.main()
