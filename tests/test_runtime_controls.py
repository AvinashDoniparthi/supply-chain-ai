import os
import sys
import time
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.state import AgentState
from utils.output import _timing_lines
from utils.runtime_controls import timed_stage


class TestRuntimeControls(unittest.TestCase):
    def test_timed_stage_records_duration_and_status(self):
        state = AgentState(target_company="AMD")

        with timed_stage(state, "unit_test_stage", status="cache_hit"):
            time.sleep(0.001)

        self.assertGreater(state.stage_durations["unit_test_stage"], 0)
        self.assertEqual(state.stage_statuses["unit_test_stage"], "cache_hit")

    def test_skipped_stage_displays_as_skipped(self):
        state = AgentState(target_company="AMD")
        state.stage_durations["risk_analysis"] = 0.001
        state.stage_statuses["risk_analysis"] = "skipped"

        output = "\n".join(_timing_lines(state))

        self.assertIn("Risk Analysis", output)
        self.assertIn("Skipped", output)

    def test_sub_tenth_second_live_stage_displays_less_than_point_one(self):
        state = AgentState(target_company="AMD")
        state.stage_durations["verification"] = 0.049

        output = "\n".join(_timing_lines(state))

        self.assertIn("Verification", output)
        self.assertIn("<0.1s", output)

    def test_report_generation_is_separate_from_post_processing_stages(self):
        state = AgentState(target_company="AMD")
        state.stage_durations = {
            "confidence_scoring": 1.0,
            "criticality_scoring": 2.0,
            "health_scoring": 3.0,
            "executive_report_generation": 0.2,
            "history_persistence": 4.0,
            "graph_export": 5.0,
            "report_generation": 99.0,
        }

        lines = _timing_lines(state)
        output = "\n".join(lines)
        report_line = next(line for line in lines if line.startswith("Report Generation"))

        self.assertIn("Confidence Scoring", output)
        self.assertIn("Criticality Scoring", output)
        self.assertIn("Health Scoring", output)
        self.assertIn("History Persistence", output)
        self.assertIn("Graph Export", output)
        self.assertIn("0.2s", report_line)
        self.assertNotIn("99.0s", report_line)


if __name__ == "__main__":
    unittest.main()
