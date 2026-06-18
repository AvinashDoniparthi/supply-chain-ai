import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, SupplierConfidence, SupplierInfo, RiskAnalysis
from models.relationship import RelationshipResult
from models.verification import VerificationResult

logger = logging.getLogger(__name__)

class SupplierConfidenceAgent:
    """
    Calculates final confidence scores for suppliers based on the entire intelligence pipeline.
    """

    def calculate_supplier_confidence(self, state: AgentState) -> AgentState:
        print("\n--- SUPPLIER CONFIDENCE AGENT ---")
        
        confidence_scores = []
        
        # Maps for quick lookup
        relationship_map = {r.candidate_company: r for r in state.relationship_results}
        verification_map = {v.supplier_name: v for v in state.verification_results}
        
        # Group risks by supplier
        risk_map = {}
        for risk in state.risk_assessments:
            if risk.supplier_name not in risk_map:
                risk_map[risk.supplier_name] = []
            risk_map[risk.supplier_name].append(risk)

        for supplier in state.suppliers:
            # 1. Discovery Confidence
            discovery_conf = getattr(supplier, 'discovery_confidence', 0.5)
            if discovery_conf == 0.0: # If it's explicitly 0.0, it might mean it wasn't set
                discovery_conf = 0.5

            # 2. Relationship Confidence
            rel_result = relationship_map.get(supplier.name) or relationship_map.get(getattr(supplier, 'canonical_name', ''))
            relationship_conf = rel_result.confidence_score if rel_result else 0.5

            # 3. Verification Confidence
            ver_result = verification_map.get(supplier.name) or verification_map.get(getattr(supplier, 'canonical_name', ''))
            if ver_result:
                if ver_result.verified:
                    verification_conf = ver_result.confidence_score
                else:
                    verification_conf = ver_result.confidence_score * 0.5
            else:
                verification_conf = 0.3

            # 4. Risk Confidence
            supplier_risks = risk_map.get(supplier.name, []) or risk_map.get(getattr(supplier, 'canonical_name', ''), [])
            risk_conf = self._calculate_risk_confidence(supplier_risks)

            # Final Score Formula
            final_conf = (
                discovery_conf * 0.20 +
                relationship_conf * 0.30 +
                verification_conf * 0.35 +
                risk_conf * 0.15
            )
            final_conf = round(final_conf, 2)

            reasoning = self.generate_reasoning(
                supplier.name, 
                discovery_conf, 
                relationship_conf, 
                verification_conf, 
                risk_conf,
                ver_result,
                supplier_risks
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
            print(f"\nSupplier: {supplier.name}")
            print(f"Discovery: {discovery_conf:.2f}")
            print(f"Relationship: {relationship_conf:.2f}")
            print(f"Verification: {verification_conf:.2f}")
            print(f"Risk: {risk_conf:.2f}")
            print(f"\nFinal Score: {final_conf:.2f}")
            print(f"\nReasoning:\n{reasoning}")

        # Summary Logging
        if confidence_scores:
            sorted_scores = sorted(confidence_scores, key=lambda x: x.final_confidence, reverse=True)
            print("\nSUMMARY:")
            print("\nHighest Confidence Suppliers:")
            for i, s in enumerate(sorted_scores[:2]):
                print(f"{i+1}. {s.supplier_name} ({s.final_confidence})")
            
            print("\nLowest Confidence Suppliers:")
            print(f"1. {sorted_scores[-1].supplier_name} ({sorted_scores[-1].final_confidence})")

        state.supplier_confidence_scores = confidence_scores
        state.current_task = "Confidence scoring completed"
        
        state.history.append({
            "agent": "confidence_agent",
            "action": "calculated_confidence_scores",
            "total_suppliers": len(confidence_scores),
            "status": "success"
        })

        return state

    def _calculate_risk_confidence(self, risks: List[RiskAnalysis]) -> float:
        if not risks:
            return 0.9
        
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

    def generate_reasoning(self, name, discovery, relationship, verification, risk, ver_result, risks) -> str:
        parts = []
        
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
            parts.append("No operational or strategic risks detected.")
        else:
            highest_risk = sorted(risks, key=lambda x: {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}[x.severity], reverse=True)[0]
            parts.append(f"Exposure to {highest_risk.severity.lower()} severity risks ({highest_risk.risk_type}) impacts actionability.")

        return " ".join(parts)

def confidence_agent(state: AgentState) -> AgentState:
    agent = SupplierConfidenceAgent()
    return agent.calculate_supplier_confidence(state)
