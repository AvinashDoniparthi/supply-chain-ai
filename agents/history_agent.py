import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from models.state import AgentState, HistoricalRun
from utils.output import agent_event, debug_log

logger = logging.getLogger(__name__)

class HistoryAgent:
    """
    Manages persistent historical storage and trend detection for supply chain analysis.
    """

    def __init__(self, history_dir: str = "database/history"):
        self.history_dir = history_dir
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

    def process_history(self, state: AgentState) -> AgentState:
        agent_event("History agent started")

        if not state.executive_report or not state.supply_chain_health:
            debug_log(logger, "Executive report or health data missing. History processing skipped.")
            return state

        company_name = state.target_company or "Unknown"
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        history_file = os.path.join(self.history_dir, f"{safe_name}.json")

        # 1. Load existing company history file
        history_data = self._load_history(history_file, company_name)
        previous_run = history_data["runs"][-1] if history_data["runs"] else None

        # 2. Create current run snapshot
        current_run = HistoricalRun(
            timestamp=datetime.now().isoformat(),
            health_score=state.supply_chain_health.overall_score,
            health_status=state.supply_chain_health.status,
            supplier_count=len(state.suppliers),
            risk_count=len(state.risk_assessments),
            suppliers=[s.name for s in state.suppliers]
        )

        # 3. Detect Trends
        trends = self._detect_trends(current_run, previous_run)

        # 4. Append current run and save
        history_data["runs"].append(current_run.dict())
        self._save_history(history_file, history_data)

        # Update state with historical runs for the current session if needed
        state.historical_runs = [HistoricalRun(**r) for r in history_data["runs"]]

        # 5. Logging
        debug_log(logger, "Previous Runs: %s", len(history_data["runs"]) - 1)
        debug_log(logger, "Current Health: %s", current_run.health_score)
        debug_log(logger, "Previous Health: %s", previous_run["health_score"] if previous_run else "N/A")

        debug_log(logger, "Health Delta: %s", trends["health_delta"])
        debug_log(logger, "Supplier Delta: %s", trends["supplier_delta"])
        debug_log(logger, "Risk Delta: %s", trends["risk_delta"])

        debug_log(logger, "History Saved: %s", history_file)

        state.current_task = "History processing completed"
        state.history.append({
            "agent": "history_agent",
            "action": "processed_history",
            "trends": trends,
            "status": "success"
        })

        agent_event("History agent completed")

        return state

    def _load_history(self, file_path: str, company_name: str) -> Dict[str, Any]:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load history from {file_path}: {e}")
        
        return {
            "company": company_name,
            "runs": []
        }

    def _save_history(self, file_path: str, data: Dict[str, Any]):
        try:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history to {file_path}: {e}")

    def _detect_trends(self, current: HistoricalRun, previous: Optional[Dict[str, Any]]) -> Dict[str, float]:
        if not previous:
            return {
                "health_delta": 0.0,
                "supplier_delta": 0,
                "risk_delta": 0
            }

        return {
            "health_delta": round(current.health_score - previous["health_score"], 2),
            "supplier_delta": current.supplier_count - previous["supplier_count"],
            "risk_delta": current.risk_count - previous["risk_count"]
        }

def history_agent(state: AgentState) -> AgentState:
    agent = HistoryAgent()
    return agent.process_history(state)
