import csv
from pathlib import Path
import unittest


SLM_DIR = (
    Path(__file__).resolve().parents[1]
    / "database/benchmarks/product_level/sample_20260804_final_slm_ollama_gemma3_4b"
)


class FinalSlmProvenanceTest(unittest.TestCase):
    def test_insufficient_reference_rows_are_not_marked_as_model_successes(self):
        csv_paths = sorted(SLM_DIR.glob("*.csv"))
        self.assertEqual(len(csv_paths), 7)
        rows_by_file = {}
        for path in csv_paths:
            with path.open(newline="") as stream:
                rows_by_file[path.name] = list(csv.DictReader(stream))
        rows = rows_by_file["master_results.csv"]

        counts = {value: sum(row["primary_model_success"].lower() == value for row in rows)
                  for value in ("true", "false", "not_applicable")}
        self.assertEqual(counts, {"true": 4, "false": 0, "not_applicable": 13})

        required = {
            "provider", "model", "primary_model_success", "fallback_used",
            "fallback_stages", "workflow_status", "warnings", "errors",
        }
        for file_rows in rows_by_file.values():
            self.assertTrue(required.issubset(file_rows[0]))
            for row in file_rows:
                self.assertEqual(row["fallback_used"].lower(), "false")
                self.assertEqual(row["workflow_status"], "completed")
                if row["evaluation_status"] == "insufficient_component_supplier_evidence":
                    self.assertEqual(row["primary_model_success"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
