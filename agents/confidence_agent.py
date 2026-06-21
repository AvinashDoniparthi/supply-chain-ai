import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, SupplierConfidence, SupplierInfo, RiskAnalysis
from models.relationship import RelationshipResult
from models.verification import VerificationResult
from utils.supply_chain_metrics import (
    calculate_discovery_coverage,
    calculate_verification_quality,
    coverage_confidence_cap,
)
from utils.identity_resolution import resolver
from utils.output import agent_event, debug_log, is_external_risk
from utils.runtime_controls import start_stage

logger = logging.getLogger(__name__)

class SupplierConfidenceAgent:
    """
    Calculates final confidence scores for suppliers based on the entire intelligence pipeline.
    """

    def calculate_supplier_confidence(self, state: AgentState) -> AgentState:
        start_stage(state, "report_generation")
        agent_event("Confidence agent started")
        
        confidence_scores = []
        coverage = calculate_discovery_coverage(state)
        verification_quality = calculate_verification_quality(state)
        discovery_coverage = coverage["coverage_ratio"]
        effective_coverage = discovery_coverage * verification_quality["quality_factor"]
        final_confidence_cap = coverage_confidence_cap(effective_coverage)
        state.confidence_scores["discovery_coverage"] = round(discovery_coverage, 2)
        state.confidence_scores["effective_coverage"] = round(effective_coverage, 2)
        state.confidence_scores["discovery_coverage_label"] = coverage["label"]
        state.confidence_scores["verification_quality_label"] = verification_quality["label"]
        
        # Maps for quick lookup
        relationship_map = {}
        for relationship in state.relationship_results:
            relationship_map[relationship.candidate_company] = relationship
            relationship_map[resolver.resolve(relationship.candidate_company)] = relationship
        verification_map = {}
        for verification in state.verification_results:
            verification_map[verification.supplier_name] = verification
            verification_map[resolver.resolve(verification.supplier_name)] = verification
        
        # Group risks by supplier
        risk_map = {}
        for risk in state.risk_assessments:
            if not is_external_risk(risk):
                continue
            for risk_key in {risk.supplier_name, resolver.resolve(risk.supplier_name)}:
                if risk_key not in risk_map:
                    risk_map[risk_key] = []
                risk_map[risk_key].append(risk)

        for supplier in state.suppliers:
            # 1. Discovery Confidence
            discovery_conf = getattr(supplier, 'discovery_confidence', 0.5)
            if discovery_conf == 0.0: # If it's explicitly 0.0, it might mean it wasn't set
                discovery_conf = 0.5

            # 2. Relationship Confidence
            supplier_key = resolver.resolve(getattr(supplier, 'canonical_name', '') or supplier.name)
            rel_result = relationship_map.get(supplier.name) or relationship_map.get(supplier_key)
            relationship_conf = rel_result.confidence_score if rel_result else 0.5

            # 3. Verification Confidence
            ver_result = verification_map.get(supplier.name) or verification_map.get(supplier_key)
            if ver_result:
                if ver_result.verified:
                    verification_conf = ver_result.confidence_score
                else:
                    verification_conf = ver_result.confidence_score * 0.5
            else:
                verification_conf = 0.3

            # 4. Risk Confidence
            supplier_risks = risk_map.get(supplier.name, []) or risk_map.get(supplier_key, [])
            risk_conf = self._calculate_risk_confidence(supplier_risks, discovery_coverage)

            # Final Score Formula
            final_conf = (
                discovery_conf * 0.20 +
                relationship_conf * 0.30 +
                verification_conf * 0.35 +
                risk_conf * 0.15
            )
            final_conf = min(final_conf, final_confidence_cap)
            final_conf = round(final_conf, 2)

            reasoning = self.generate_reasoning(
                supplier.name, 
                discovery_conf, 
                relationship_conf, 
                verification_conf, 
                risk_conf,
                ver_result,
                supplier_risks,
                coverage,
                verification_quality,
            )

            conf_obj = SupplierConfidence(
                supplier_name=supplier.name,
                discovery_confidence=discovery_conf,
                relationship_confidence=relationship_conf,
                verification_confidence=verification_conf,
                risk_confidence=risk_conf,
                final_confidence=final_conf,
                reasoning=reasoning
            )
            confidence_scores.append(conf_obj)

            # Logging Trace
            debug_log(
                logger,
                "Supplier: %s | Discovery: %.2f | Relationship: %.2f | Verification: %.2f | Risk: %.2f | Final Score: %.2f | Reasoning: %s",
                supplier.name,
                discovery_conf,
                relationship_conf,
                verification_conf,
                risk_conf,
                final_conf,
                reasoning,
            )

        # Summary Logging
        if confidence_scores:
            sorted_scores = sorted(confidence_scores, key=lambda x: x.final_confidence, reverse=True)
            debug_log(logger, "Confidence summary")
            debug_log(logger, "Highest Confidence Suppliers:")
            for i, s in enumerate(sorted_scores[:2]):
                debug_log(logger, "%s. %s (%s)", i + 1, s.supplier_name, s.final_confidence)
            
            debug_log(logger, "Lowest Confidence Suppliers:")
            debug_log(logger, "1. %s (%s)", sorted_scores[-1].supplier_name, sorted_scores[-1].final_confidence)

        state.supplier_confidence_scores = confidence_scores
        if confidence_scores:
            state.confidence_scores["overall_supplier_confidence"] = round(
                sum(score.final_confidence for score in confidence_scores)
                / len(confidence_scores),
                2,
            )
        state.current_task = "Confidence scoring completed"
        
        state.history.append({
            "agent": "confidence_agent",
            "action": "calculated_confidence_scores",
            "total_suppliers": len(confidence_scores),
            "discovery_coverage": coverage,
            "status": "success"
        })

        agent_event(f"Confidence agent completed: {len(confidence_scores)} scored")

        return state

    def _calculate_risk_confidence(self, risks: List[RiskAnalysis], discovery_coverage: float) -> float:
        if not risks:
            return 0.75 if discovery_coverage >= 0.8 else 0.55
        
        # Severity hierarchy
        severity_map = {
            "Critical": 0.2,
            "High": 0.4,
            "Medium": 0.6,
            "Low": 0.8
        }
        
        highest_severity = "Low"
        for risk in risks:
            if risk.severity == "Critical":
                highest_severity = "Critical"
                break
            elif risk.severity == "High":
                highest_severity = "High"
            elif risk.severity == "Medium" and highest_severity == "Low":
                highest_severity = "Medium"
        
        return severity_map[highest_severity]

    def generate_reasoning(self, name, discovery, relationship, verification, risk, ver_result, risks, coverage, verification_quality) -> str:
        parts = []

        if coverage["label"] in {"Low", "Insufficient Data"}:
            if coverage.get("coverage_basis") == "expected_suppliers":
                parts.append(
                    f"Discovery coverage is {coverage['label'].lower()} "
                    f"({coverage['matched_expected_count']}/{coverage['expected_count']} expected Tier-1 suppliers), capping confidence."
                )
            else:
                parts.append(
                    f"Discovery coverage is {coverage['label'].lower()} "
                    f"({coverage['tier1_supplier_count']} discovered Tier-1 suppliers), capping confidence."
                )
        elif coverage["label"] == "Medium":
            if coverage.get("coverage_basis") == "expected_suppliers":
                parts.append(
                    f"Discovery coverage is medium "
                    f"({coverage['matched_expected_count']}/{coverage['expected_count']} expected Tier-1 suppliers)."
                )
            else:
                parts.append(
                    f"Discovery coverage is medium "
                    f"({coverage['tier1_supplier_count']} discovered Tier-1 suppliers)."
                )

        if verification_quality["quality_factor"] < 1.0:
            parts.append(
                f"Verification quality is {verification_quality['label'].lower()} "
                f"({verification_quality['verified_count']}/{verification_quality['total_count']} suppliers verified), lowering confidence."
            )
        
        # Discovery & Relationship
        if discovery >= 0.8 and relationship >= 0.8:
            parts.append("Strongly identified supplier with high-confidence relationship classification.")
        elif discovery < 0.6 or relationship < 0.6:
            parts.append("Supplier identity or relationship classification has moderate uncertainty.")
        else:
            parts.append("Supplier relationship is reasonably well-established.")

        # Verification
        if ver_result:
            if ver_result.verified:
                parts.append(f"Successfully verified with {ver_result.confidence_score*100:.0f}% confidence.")
            else:
                parts.append(f"Verification failed: {ver_result.reasoning}")
        else:
            parts.append("No verification data available, reducing overall confidence.")

        # Risks
        if not risks:
            parts.append("No supplier-specific risk signals were detected in the assessed data.")
        else:
            highest_risk = sorted(risks, key=lambda x: {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}[x.severity], reverse=True)[0]
            parts.append(f"Exposure to {highest_risk.severity.lower()} severity risks ({highest_risk.risk_type}) impacts actionability.")

        return " ".join(parts)

def confidence_agent(state: AgentState) -> AgentState:
    agent = SupplierConfidenceAgent()
    return agent.calculate_supplier_confidence(state)
