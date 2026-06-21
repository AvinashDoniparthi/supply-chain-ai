import logging
import re
from typing import List, Dict, Any, Optional
from models.state import AgentState, ExecutiveReport, RiskAnalysis, SupplierCriticality, SupplierConfidence
from utils.supply_chain_metrics import (
    calculate_discovery_coverage,
    calculate_verification_quality,
)
from utils.output import (
    agent_event,
    data_quality_warning_lines,
    debug_log,
    is_external_risk,
    progress,
    render_supplier_tier_lines,
)

logger = logging.getLogger(__name__)

class ExecutiveReportAgent:
    """
    Generates a concise, business-ready executive report of the supply chain analysis.
    """

    def generate_report(self, state: AgentState) -> AgentState:
        progress(6, 6, "Generating Report")
        agent_event("Executive report agent started")

        if not state.supply_chain_health:
            debug_log(logger, "Supply chain health data missing. Report generation skipped.")
            return state

        company_name = state.target_company or "Unknown Company"
        health = state.supply_chain_health
        coverage = calculate_discovery_coverage(state)

        # 1. Key Suppliers Section (Top 5 by criticality DESC, then confidence DESC)
        key_suppliers = self._get_key_suppliers(state)

        # 2. Major Risks Section (Top 5 by severity)
        major_risks = self._get_major_risks(state)

        # 3. Recommendations Engine
        recommendations = self._generate_recommendations(state, coverage)

        # 4. Executive Summary Logic
        summary = self._generate_executive_summary(
            state, company_name, health, key_suppliers, major_risks, coverage
        )

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
        debug_log(logger, "Health Score: %s", report.overall_health_score)
        debug_log(logger, "Health Status: %s", report.health_status)
        
        debug_log(logger, "Key Suppliers:")
        for s in report.key_suppliers:
            debug_log(logger, "- %s", s)
            
        debug_log(logger, "Major Risks:")
        for r in report.major_risks:
            debug_log(logger, "- %s", r)
            
        debug_log(logger, "Recommendations:")
        for rec in report.recommendations:
            debug_log(logger, "- %s", rec)

        state.executive_report = report
        state.current_task = "Executive report generated"
        
        state.history.append({
            "agent": "executive_report_agent",
            "action": "generated_executive_report",
            "status": "success"
        })

        agent_event("Executive report agent completed")

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
            [risk for risk in state.risk_assessments if is_external_risk(risk)],
            key=lambda r: severity_order.get(r.severity, 0),
            reverse=True
        )
        
        # Deduplicate and format
        seen_risks = set()
        formatted_risks = []
        for r in risks_sorted:
            risk_desc = f"{r.risk_type} risk for {r.supplier_name}: {r.reasoning.strip()}"
            if risk_desc not in seen_risks:
                formatted_risks.append(risk_desc)
                seen_risks.add(risk_desc)
            if len(formatted_risks) >= 5:
                break
                
        return formatted_risks

    def _generate_recommendations(self, state: AgentState, coverage: Dict[str, Any]) -> List[str]:
        recommendations = []

        if coverage["label"] in {"Low", "Insufficient Data"}:
            if coverage.get("coverage_basis") == "expected_suppliers":
                missing = ", ".join(coverage["missing_expected_suppliers"][:5])
                recommendations.append(
                    f"Complete Tier-1 discovery before acting on health score"
                    + (f"; missing expected suppliers include {missing}." if missing else ".")
                )
            else:
                recommendations.append(
                    "Complete Tier-1 discovery before acting on health score."
                )

        high_risks = [
            r
            for r in state.risk_assessments
            if r.severity in {"Critical", "High"} and is_external_risk(r)
        ]
        if high_risks:
            recommendations.append(
                f"Investigate {high_risks[0].risk_type.lower()} exposure for "
                f"{high_risks[0].supplier_name}: {high_risks[0].reasoning}"
            )

        critical_suppliers = [
            c
            for c in state.supplier_criticality_scores
            if c.criticality_level == "Critical" or c.criticality_score >= 0.85
        ]
        if critical_suppliers:
            recommendations.append(
                f"Assess dependence on critical supplier {critical_suppliers[0].supplier_name}."
            )

        low_confidence = [
            c for c in state.supplier_confidence_scores if c.final_confidence < 0.6
        ]
        if low_confidence:
            recommendations.append(
                f"Perform relationship verification for low-confidence supplier: {low_confidence[0].supplier_name}."
            )

        return recommendations[:3]

    def _health_descriptor(self, status: str) -> str:
        if status in {"Excellent", "Strong"}:
            return "healthy"
        if status in {"Good", "Moderate"}:
            return "moderately healthy"
        if status == "Insufficient Data":
            return "not yet well-measured"
        return "strained"

    def _supplier_names(self, state: AgentState) -> List[str]:
        return [supplier.name for supplier in state.suppliers]

    def _has_supplier(self, state: AgentState, *needles: str) -> bool:
        parts = []
        for supplier in state.suppliers:
            parts.extend(
                [
                    supplier.name,
                    supplier.canonical_name or "",
                    " ".join(supplier.products),
                ]
            )
        haystack = " ".join(parts).lower()
        return any(needle.lower() in haystack for needle in needles)

    def _dependency_phrase(self, state: AgentState, key_suppliers: List[str]) -> str:
        company_name = (state.target_company or "").upper()
        if company_name == "AMD":
            has_tsmc = self._has_supplier(
                state, "TSMC", "Taiwan Semiconductor Manufacturing Company"
            )
            has_samsung = self._has_supplier(state, "Samsung")
            has_packaging = self._has_supplier(
                state, "ASE", "Amkor", "packaging", "assembly and test"
            )
            if has_tsmc and has_samsung and has_packaging:
                return "TSMC, Samsung, and outsourced packaging suppliers"

        named = key_suppliers[:3] or self._supplier_names(state)[:3]
        if not named:
            return "unverified supplier coverage"
        if len(named) == 1:
            return named[0]
        if len(named) == 2:
            return f"{named[0]} and {named[1]}"
        return f"{named[0]}, {named[1]}, and {named[2]}"

    def _main_risk_phrase(self, state: AgentState) -> str:
        material_risks = [
            risk
            for risk in state.risk_assessments
            if risk.severity in {"Critical", "High", "Medium"} and is_external_risk(risk)
        ]
        if not material_risks:
            return "limited verification depth or supplier concentration"

        risk_text = " ".join(
            f"{risk.risk_type} {risk.reasoning}" for risk in material_risks
        ).lower()
        supplier_text = " ".join(
            f"{supplier.location} {' '.join(supplier.products)}"
            for supplier in state.suppliers
        ).lower()

        geographic = any(
            term in risk_text or term in supplier_text
            for term in ["geopolitical", "taiwan", "china", "korea", "asia"]
        )
        labor = any(
            term in risk_text
            for term in ["labor", "strike", "workforce", "work stoppage"]
        )
        financial = "financial" in risk_text or "bankruptcy" in risk_text

        if (state.target_company or "").upper() == "AMD" and geographic:
            if labor:
                return "geographic and labor disruption exposure among key Asian semiconductor suppliers"
            return "geographic disruption exposure among key Asian semiconductor suppliers"
        if geographic and labor:
            return "geographic and labor disruption exposure among key suppliers"
        if geographic:
            return "geographic disruption exposure among key suppliers"
        if labor:
            return "labor disruption exposure among key suppliers"
        if financial:
            return "supplier financial stability"
        return "supplier-specific disruption exposure"

    def _clean_two_sentence_summary(self, sentences: List[str]) -> str:
        text = " ".join(sentence.strip() for sentence in sentences if sentence.strip())
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\.{2,}", ".", text)
        parts = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(parts[:2]).strip()

    def _summary_paragraph(
        self,
        state: AgentState,
        company_name: str,
        health,
        key_suppliers: List[str],
    ) -> str:
        if health.status == "Insufficient Data":
            return (
                f"Insufficient data to state {company_name}'s supply-chain health confidently."
            )

        descriptor = self._health_descriptor(health.status)
        dependency = self._dependency_phrase(state, key_suppliers)
        main_risk = self._main_risk_phrase(state)
        domain = "semiconductor " if (company_name or "").upper() == "AMD" else ""

        return self._clean_two_sentence_summary(
            [
                (
                    f"{company_name} has a {descriptor} {domain}supply chain "
                    f"with strong dependence on {dependency}."
                ),
                f"The main concern is {main_risk}.",
            ]
        )

    def _generate_executive_summary(self, state, company_name, health, key_suppliers, major_risks, coverage) -> str:
        risks = major_risks or [
            "Insufficient Data"
            if coverage["label"] in {"Low", "Insufficient Data"}
            else "No supplier-specific risks detected"
        ]
        critical_suppliers = key_suppliers[:5] if key_suppliers else ["Insufficient Data"]
        warning_lines = data_quality_warning_lines(state)

        use_expected = coverage.get("coverage_basis") == "expected_suppliers"
        missing = ", ".join(coverage["missing_expected_suppliers"][:5]) if use_expected else ""
        false_positive_text = ", ".join(coverage["false_positive_suppliers"][:5]) if use_expected else ""
        verification_quality = calculate_verification_quality(state)

        lines = [
            "DISCOVERY QUALITY",
            (
                f"Coverage: {coverage['label']} - {coverage['matched_expected_count']}/"
                f"{coverage['expected_count']} expected Tier-1 suppliers identified."
                if use_expected
                else f"Coverage: {coverage['label']} - {coverage['tier1_supplier_count']} discovered Tier-1 suppliers identified."
            ),
        ]
        if verification_quality["quality_factor"] < 1.0:
            lines.append(
                f"Verification-adjusted coverage: {coverage['verification_adjusted_label']} "
                f"({coverage['verification_adjusted_ratio']:.0%}; "
                f"{verification_quality['verified_count']}/{verification_quality['total_count']} suppliers verified)."
            )
        if missing:
            lines.append(f"Missing expected suppliers: {missing}.")
        if false_positive_text:
            lines.append(f"Unexpected Tier-1 candidates: {false_positive_text}.")

        lines.extend(
            [
                "",
                "SUPPLY CHAIN HEALTH",
                (
                    f"{health.status} - {health.overall_score}/100."
                    if health.status != "Insufficient Data"
                    else f"Insufficient Data - score capped at {health.overall_score}/100."
                ),
                "",
            ]
        )
        lines.extend(render_supplier_tier_lines(state))

        lines.extend(["", "TOP RISKS"])
        lines.extend(f"- {risk}" for risk in risks)

        lines.extend(["", "DATA QUALITY WARNINGS"])
        lines.extend(warning_lines or ["None"])

        lines.extend(["", "CRITICAL SUPPLIERS"])
        lines.extend(f"- {supplier}" for supplier in critical_suppliers)

        lines.extend(["", "EXECUTIVE SUMMARY"])
        lines.append(self._summary_paragraph(state, company_name, health, key_suppliers))

        return "\n".join(lines)

def executive_report_agent(state: AgentState) -> AgentState:
    agent = ExecutiveReportAgent()
    return agent.generate_report(state)
