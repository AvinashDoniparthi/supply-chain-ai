import unittest
import sys
import os
import json
import shutil
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.state import AgentState, SupplierInfo, RiskAnalysis, SupplyChainHealth, ExecutiveReport, HistoricalRun
from agents.history_agent import HistoryAgent, history_agent

class TestHistoryAgent(unittest.TestCase):
    def setUp(self):
        self.test_history_dir = "database/test_history"
        self.agent = HistoryAgent(history_dir=self.test_history_dir)
        self.company_name = "TestCorp"
        self.state = AgentState(target_company=self.company_name)
        self.state.supply_chain_health = SupplyChainHealth(
            overall_score=75.0,
            status="Good",
            supplier_count=2,
            critical_suppliers=1,
            high_risk_suppliers=0,
            summary="..."
        )
        self.state.executive_report = ExecutiveReport(
            company_name=self.company_name,
            overall_health_score=75.0,
            health_status="Good",
            executive_summary="...",
            key_suppliers=["S1"],
            major_risks=[],
            recommendations=[]
        )
        self.state.suppliers = [SupplierInfo(name="S1", location="L1"), SupplierInfo(name="S2", location="L2")]
        self.state.risk_assessments = [RiskAnalysis(supplier_name="S1", risk_type="R1", severity="Low", confidence=1.0, reasoning="...")]

    def tearDown(self):
        if os.path.exists(self.test_history_dir):
            shutil.rmtree(self.test_history_dir)

    def test_new_file_creation(self):
        """Test that a new history file is created for a company."""
        updated_state = self.agent.process_history(self.state)
        history_file = os.path.join(self.test_history_dir, f"{self.company_name.lower()}.json")
        
        self.assertTrue(os.path.exists(history_file))
        with open(history_file, "r") as f:
            data = json.load(f)
            self.assertEqual(data["company"], self.company_name)
            self.assertEqual(len(data["runs"]), 1)
            self.assertEqual(data["runs"][0]["health_score"], 75.0)

    def test_existing_file_append(self):
        """Test that a new run is appended to an existing history file."""
        # First run
        self.agent.process_history(self.state)
        
        # Second run with different score
        self.state.supply_chain_health.overall_score = 80.0
        updated_state = self.agent.process_history(self.state)
        
        history_file = os.path.join(self.test_history_dir, f"{self.company_name.lower()}.json")
        with open(history_file, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["runs"]), 2)
            self.assertEqual(data["runs"][1]["health_score"], 80.0)

    def test_delta_calculations(self):
        """Test trend detection (deltas) between runs."""
        # First run (Health 75, Suppliers 2, Risks 1)
        self.agent.process_history(self.state)
        
        # Second run (Health 80, Suppliers 3, Risks 0)
        self.state.supply_chain_health.overall_score = 80.0
        self.state.suppliers.append(SupplierInfo(name="S3", location="L3"))
        self.state.risk_assessments = []
        
        updated_state = self.agent.process_history(self.state)
        
        trends = updated_state.history[-1]["trends"]
        self.assertEqual(trends["health_delta"], 5.0)
        self.assertEqual(trends["supplier_delta"], 1)
        self.assertEqual(trends["risk_delta"], -1)

    def test_empty_history_scenario(self):
        """Test deltas are 0 when no previous history exists."""
        updated_state = self.agent.process_history(self.state)
        trends = updated_state.history[-1]["trends"]
        
        self.assertEqual(trends["health_delta"], 0.0)
        self.assertEqual(trends["supplier_delta"], 0)
        self.assertEqual(trends["risk_delta"], 0)

if __name__ == '__main__':
    unittest.main()
