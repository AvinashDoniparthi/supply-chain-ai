import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, SupplyChainHealth, RiskAnalysis
from utils.supply_chain_metrics import (
    calculate_discovery_coverage,
    calculate_verification_quality,
    coverage_confidence_cap,
)
from utils.identity_resolution import resolver
from utils.output import agent_event, debug_log, is_external_risk

logger = logging.getLogger(__name__)

class SupplyChainHealthAgent:
    """
    Generates an overall health score and executive summary for the supply chain.
    """

    def generate_health_report(self, state: AgentState) -> AgentState:
        agent_event("Health agent started")

        if not state.suppliers:
            debug_log(logger, "No suppliers found. Health assessment skipped.")
            return state

        # Maps for quick lookup
        confidence_map = {}
        for confidence in state.supplier_confidence_scores:
            confidence_map[confidence.supplier_name] = confidence
            confidence_map[resolver.resolve(confidence.supplier_name)] = confidence
        criticality_map = {}
        for criticality in state.supplier_criticality_scores:
            criticality_map[criticality.supplier_name] = criticality
            criticality_map[resolver.resolve(criticality.supplier_name)] = criticality
        
        # Group risks by supplier
        risk_map = {}
        for risk in state.risk_assessments:
            if not is_external_risk(risk):
                continue
            for risk_key in {risk.supplier_name, resolver.resolve(risk.supplier_name)}:
                if risk_key not in risk_map:
                    risk_map[risk_key] = []
                risk_map[risk_key].append(risk)

        supplier_contributions = []
        critical_count = 0
        high_risk_count = 0
        coverage = calculate_discovery_coverage(state)
        verification_quality = calculate_verification_quality(state)

        risk_mapping = {
            "No Risk": 1.0,
            "Low": 0.8,
            "Medium": 0.6,
            "High": 0.3,
            "Critical": 0.1
        }

        for supplier in state.suppliers:
            # 1. Confidence Score (0.0 to 1.0)
            supplier_key = resolver.resolve(supplier.canonical_name or supplier.name)
            conf_obj = confidence_map.get(supplier.name) or confidence_map.get(supplier_key)
            conf_score = conf_obj.final_confidence if conf_obj else 0.5

            # 2. Criticality Score (0.0 to 1.0)
            crit_obj = criticality_map.get(supplier.name) or criticality_map.get(supplier_key)
            crit_score = crit_obj.criticality_score if crit_obj else 0.5
            if crit_obj and crit_obj.criticality_level == "Critical":
                critical_count += 1

            # 3. Risk Score (0.0 to 1.0)
            supplier_risks = risk_map.get(supplier.name, []) or risk_map.get(supplier_key, [])
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
        effective_coverage = coverage["coverage_ratio"] * verification_quality["quality_factor"]
        health_cap = coverage_confidence_cap(effective_coverage) * 100
        overall_score = min(overall_score, health_cap)
        overall_score = round(overall_score, 1)

        # Status Bands
        if coverage["coverage_ratio"] < 0.5:
            status = "Insufficient Data"
        elif overall_score >= 90:
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
        summary = self._generate_summary(
            state.target_company,
            status,
            critical_count,
            high_risk_count,
            state.risk_assessments,
            coverage,
            verification_quality,
        )

        health_report = SupplyChainHealth(
            overall_score=overall_score,
            status=status,
            supplier_count=len(state.suppliers),
            critical_suppliers=critical_count,
            high_risk_suppliers=high_risk_count,
            summary=summary
        )

        # Logging
        debug_log(logger, "Overall Score: %s", overall_score)
        debug_log(logger, "Status: %s", status)
        debug_log(logger, "Critical Suppliers: %s", critical_count)
        debug_log(logger, "High Risk Suppliers: %s", high_risk_count)
        debug_log(logger, "Discovery Coverage: %s", coverage)
        debug_log(logger, "Summary: %s", summary)

        state.supply_chain_health = health_report
        state.current_task = "Supply chain health assessment completed"
        
        state.history.append({
            "agent": "health_agent",
            "action": "generated_health_report",
            "overall_score": overall_score,
            "health_status": status,
            "discovery_coverage": coverage,
            "verification_quality": verification_quality,
            "status": "success"
        })

        agent_event(f"Health agent completed: {overall_score}/100 ({status})")

        return state

    def _generate_summary(self, target, status, critical, high_risk, risks, coverage, verification_quality) -> str:
        if status == "Insufficient Data":
            if verification_quality["quality_factor"] < 0.5:
                return (
                    f"{target}'s supply chain health cannot be stated confidently because "
                    f"only {verification_quality['verified_count']}/{verification_quality['total_count']} suppliers passed verification."
                )
            if coverage.get("coverage_basis") != "expected_suppliers":
                return (
                    f"{target}'s supply chain health cannot be stated confidently because "
                    "no sufficiently supported Tier-1 suppliers were discovered."
                )
            return (
                f"{target}'s supply chain health cannot be stated confidently because "
                f"Tier-1 discovery coverage is {coverage['label'].lower()} "
                f"({coverage['matched_expected_count']}/{coverage['expected_count']} expected suppliers found)."
            )

        summary_parts = [f"{target}'s supply chain appears {status.lower()} overall."]
        
        if critical > 0:
            # Try to find a critical supplier name
            summary_parts.append(f"{critical} critical supplier(s) identified.")
        
        if high_risk > 0:
            summary_parts.append(f"{high_risk} supplier(s) face high or critical risk exposure.")
        else:
            summary_parts.append("No major operational disruptions were detected.")

        if verification_quality["quality_factor"] < 1.0:
            summary_parts.append(
                f"Verification quality is {verification_quality['label'].lower()} "
                f"({verification_quality['verified_count']}/{verification_quality['total_count']} suppliers verified)."
            )

        return " ".join(summary_parts)

def health_agent(state: AgentState) -> AgentState:
    agent = SupplyChainHealthAgent()
    return agent.generate_health_report(state)
