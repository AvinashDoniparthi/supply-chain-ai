import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, SupplyChainHealth, RiskAnalysis

logger = logging.getLogger(__name__)

class SupplyChainHealthAgent:
    """
    Generates an overall health score and executive summary for the supply chain.
    """

    def generate_health_report(self, state: AgentState) -> AgentState:
        print("\n--- SUPPLY CHAIN HEALTH AGENT ---")

        if not state.suppliers:
            print("No suppliers found. Health assessment skipped.")
            return state

        # Maps for quick lookup
        confidence_map = {c.supplier_name: c for c in state.supplier_confidence_scores}
        criticality_map = {c.supplier_name: c for c in state.supplier_criticality_scores}
        
        # Group risks by supplier
        risk_map = {}
        for risk in state.risk_assessments:
            if risk.supplier_name not in risk_map:
                risk_map[risk.supplier_name] = []
            risk_map[risk.supplier_name].append(risk)

        supplier_contributions = []
        critical_count = 0
        high_risk_count = 0

        risk_mapping = {
            "No Risk": 1.0,
            "Low": 0.8,
            "Medium": 0.6,
            "High": 0.3,
            "Critical": 0.1
        }

        for supplier in state.suppliers:
            # 1. Confidence Score (0.0 to 1.0)
            conf_obj = confidence_map.get(supplier.name)
            conf_score = conf_obj.final_confidence if conf_obj else 0.5

            # 2. Criticality Score (0.0 to 1.0)
            crit_obj = criticality_map.get(supplier.name)
            crit_score = crit_obj.criticality_score if crit_obj else 0.5
            if crit_obj and crit_obj.criticality_level == "Critical":
                critical_count += 1

            # 3. Risk Score (0.0 to 1.0)
            supplier_risks = risk_map.get(supplier.name, [])
            if not supplier_risks:
                risk_val = risk_mapping["No Risk"]
            else:
                # Find most severe risk
                severity_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                most_severe = sorted(supplier_risks, key=lambda x: severity_order.get(x.severity, 0), reverse=True)[0]
                risk_val = risk_mapping.get(most_severe.severity, 0.6)
                
                if most_severe.severity in ["High", "Critical"]:
                    high_risk_count += 1

            # Weighted Contribution
            contribution = (
                conf_score * 0.30 +
                crit_score * 0.30 +
                risk_val * 0.40
            )
            supplier_contributions.append(contribution)

        # Overall Score (Average)
        overall_score = (sum(supplier_contributions) / len(supplier_contributions)) * 100
        overall_score = round(overall_score, 1)

        # Status Bands
        if overall_score >= 90:
            status = "Excellent"
        elif overall_score >= 75:
            status = "Good"
        elif overall_score >= 60:
            status = "Moderate"
        elif overall_score >= 40:
            status = "Weak"
        else:
            status = "Critical"

        # Generate Summary
        summary = self._generate_summary(state.target_company, status, critical_count, high_risk_count, state.risk_assessments)

        health_report = SupplyChainHealth(
            overall_score=overall_score,
            status=status,
            supplier_count=len(state.suppliers),
            critical_suppliers=critical_count,
            high_risk_suppliers=high_risk_count,
            summary=summary
        )

        # Logging
        print(f"Overall Score: {overall_score}")
        print(f"Status: {status}")
        print(f"\nCritical Suppliers: {critical_count}")
        print(f"High Risk Suppliers: {high_risk_count}")
        print(f"\nSummary:\n{summary}")

        state.supply_chain_health = health_report
        state.current_task = "Supply chain health assessment completed"
        
        state.history.append({
            "agent": "health_agent",
            "action": "generated_health_report",
            "overall_score": overall_score,
            "status": status,
            "status": "success"
        })

        return state

    def _generate_summary(self, target, status, critical, high_risk, risks) -> str:
        summary_parts = [f"{target}'s supply chain appears {status.lower()} overall."]
        
        if critical > 0:
            # Try to find a critical supplier name
            summary_parts.append(f"{critical} critical supplier(s) identified.")
        
        if high_risk > 0:
            summary_parts.append(f"{high_risk} supplier(s) face high or critical risk exposure.")
        else:
            summary_parts.append("No major operational disruptions were detected.")

        return " ".join(summary_parts)

def health_agent(state: AgentState) -> AgentState:
    agent = SupplyChainHealthAgent()
    return agent.generate_health_report(state)
