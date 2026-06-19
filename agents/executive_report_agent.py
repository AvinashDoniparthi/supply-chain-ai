import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, ExecutiveReport, RiskAnalysis, SupplierCriticality, SupplierConfidence

logger = logging.getLogger(__name__)

class ExecutiveReportAgent:
    """
    Generates a concise, business-ready executive report of the supply chain analysis.
    """

    def generate_report(self, state: AgentState) -> AgentState:
        print("\n--- EXECUTIVE REPORT AGENT ---")

        if not state.supply_chain_health:
            print("Supply chain health data missing. Report generation skipped.")
            return state

        company_name = state.target_company or "Unknown Company"
        health = state.supply_chain_health

        # 1. Key Suppliers Section (Top 5 by criticality DESC, then confidence DESC)
        key_suppliers = self._get_key_suppliers(state)

        # 2. Major Risks Section (Top 5 by severity)
        major_risks = self._get_major_risks(state)

        # 3. Recommendations Engine
        recommendations = self._generate_recommendations(state)

        # 4. Executive Summary Logic
        summary = self._generate_executive_summary(company_name, health, key_suppliers, major_risks)

        report = ExecutiveReport(
            company_name=company_name,
            overall_health_score=health.overall_score,
            health_status=health.status,
            executive_summary=summary,
            key_suppliers=key_suppliers,
            major_risks=major_risks,
            recommendations=recommendations
        )

        # Logging
        print(f"\nHealth Score: {report.overall_health_score}")
        print(f"Health Status: {report.health_status}")
        
        print("\nKey Suppliers:")
        for s in report.key_suppliers:
            print(f"- {s}")
            
        print("\nMajor Risks:")
        for r in report.major_risks:
            print(f"- {r}")
            
        print("\nRecommendations:")
        for rec in report.recommendations:
            print(f"- {rec}")

        state.executive_report = report
        state.current_task = "Executive report generated"
        
        state.history.append({
            "agent": "executive_report_agent",
            "action": "generated_executive_report",
            "status": "success"
        })

        return state

    def _get_key_suppliers(self, state: AgentState) -> List[str]:
        crit_map = {c.supplier_name: c.criticality_score for c in state.supplier_criticality_scores}
        conf_map = {c.supplier_name: c.final_confidence for c in state.supplier_confidence_scores}
        
        suppliers_sorted = sorted(
            state.suppliers,
            key=lambda s: (crit_map.get(s.name, 0), conf_map.get(s.name, 0)),
            reverse=True
        )
        
        return [s.name for s in suppliers_sorted[:5]]

    def _get_major_risks(self, state: AgentState) -> List[str]:
        severity_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        
        risks_sorted = sorted(
            state.risk_assessments,
            key=lambda r: severity_order.get(r.severity, 0),
            reverse=True
        )
        
        # Deduplicate and format
        seen_risks = set()
        formatted_risks = []
        for r in risks_sorted:
            risk_desc = f"{r.risk_type} risk: {r.reasoning.split(':')[0]}"
            if risk_desc not in seen_risks:
                formatted_risks.append(risk_desc)
                seen_risks.add(risk_desc)
            if len(formatted_risks) >= 5:
                break
                
        return formatted_risks

    def _generate_recommendations(self, state: AgentState) -> List[str]:
        recommendations = []
        
        # Check for geopolitical risk
        has_geopolitical = any(r.risk_type == "Geopolitical" for r in state.risk_assessments)
        if has_geopolitical:
            recommendations.append("Develop alternate sourcing strategies in lower-risk regions to mitigate geopolitical exposure.")
            
        # Check for critical supplier concentration
        critical_suppliers = [c for c in state.supplier_criticality_scores if c.criticality_level == "Critical"]
        if len(critical_suppliers) > 0:
            recommendations.append(f"Reduce dependence on single-source critical suppliers (e.g., {critical_suppliers[0].supplier_name}).")
            
        # Check for low verification confidence
        low_conf = any(c.final_confidence < 0.7 for c in state.supplier_confidence_scores)
        if low_conf:
            recommendations.append("Conduct deeper supplier verification and due diligence for low-confidence entities.")
            
        # Check for overall health
        if state.supply_chain_health.overall_score < 60:
            recommendations.append("Initiate a comprehensive supply chain resilience review to address systemic weaknesses.")
        elif not recommendations:
            recommendations.append("Monitor high-criticality suppliers for emerging operational risks.")

        # Limit to 3-5
        if len(recommendations) < 3:
            recommendations.append("Maintain buffer stocks for key components to protect against short-term disruptions.")
            recommendations.append("Establish real-time monitoring of global news and trade policy changes.")

        return recommendations[:5]

    def _generate_executive_summary(self, company_name, health, key_suppliers, major_risks) -> str:
        from chains.executive_summary_chain import get_executive_summary_chain
        
        try:
            chain = get_executive_summary_chain(provider="openai")
            summary = chain.invoke({
                "health_score": f"{health.overall_score}/100 ({health.status})",
                "suppliers": ", ".join(key_suppliers) if key_suppliers else "None identified",
                "risks": ", ".join(major_risks) if major_risks else "No major risks identified"
            })
            return summary
        except Exception as e:
            logger.warning(f"LangChain executive summary generation failed: {e}. Using deterministic fallback.")
            summary_parts = []
            summary_parts.append(f"{company_name}'s supply chain health is {health.status} ({health.overall_score}/100).")
            
            if key_suppliers:
                summary_parts.append(f"The company relies heavily on {key_suppliers[0]} for critical production and operations.")
                
            if major_risks:
                summary_parts.append(f"{major_risks[0]} represents a primary risk factor needing immediate attention.")
                
            summary_parts.append("Supplier verification confidence remains strong overall." if health.overall_score > 70 else "Significant gaps in supplier verification and data quality were identified.")
            summary_parts.append("Supply chain diversification should be considered to reduce concentration risk.")
            
            return " ".join(summary_parts)

def executive_report_agent(state: AgentState) -> AgentState:
    agent = ExecutiveReportAgent()
    return agent.generate_report(state)
