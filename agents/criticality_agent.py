import logging
from typing import List, Dict, Any, Optional
from models.state import AgentState, SupplierCriticality, SupplierInfo, RiskAnalysis
from models.relationship import RelationshipResult
from models.verification import VerificationResult

logger = logging.getLogger(__name__)

class CriticalityAgent:
    """
    Estimates how important each supplier is to the target company.
    """

    def calculate_criticality(self, state: AgentState) -> AgentState:
        print("\n--- CRITICALITY AGENT ---")
        
        criticality_results = []
        
        # Maps for quick lookup
        relationship_map = {r.candidate_company: r for r in state.relationship_results}
        verification_map = {v.supplier_name: v for v in state.verification_results}
        
        # Track product categories for uniqueness
        product_categories = {}
        for supplier in state.suppliers:
            for product in supplier.products:
                cat = product.lower()
                if cat not in product_categories:
                    product_categories[cat] = []
                product_categories[cat].append(supplier.name)

        for supplier in state.suppliers:
            # A. Relationship importance
            rel_result = relationship_map.get(supplier.name) or relationship_map.get(getattr(supplier, 'canonical_name', ''))
            rel_type = rel_result.relationship_type.lower() if rel_result else "unknown"
            
            rel_score = 0.0
            if rel_type == "supplier":
                rel_score = 0.4
            elif rel_type == "partner":
                rel_score = 0.3
            elif rel_type == "subsidiary":
                rel_score = 0.5
            else:
                rel_score = 0.2 # Default for unknown/others

            # B. Product importance
            high_kws = ["chip", "semiconductor", "processor", "foundry", "battery", "display", "memory"]
            med_kws = ["assembly", "manufacturing", "electronics", "component"]
            low_kws = ["packaging", "logistics", "service"]
            
            # Combine products and description for keyword matching
            search_text = " ".join(supplier.products).lower()
            if hasattr(supplier, 'description') and supplier.description:
                search_text += " " + supplier.description.lower()
            
            prod_score = 0.0
            if any(kw in search_text for kw in high_kws):
                prod_score = 0.3
            elif any(kw in search_text for kw in med_kws):
                prod_score = 0.2
            elif any(kw in search_text for kw in low_kws):
                prod_score = 0.1
            else:
                prod_score = 0.05

            # C. Supplier uniqueness
            unique_score = 0.0
            is_unique = False
            for product in supplier.products:
                cat = product.lower()
                if len(product_categories.get(cat, [])) == 1:
                    unique_score = 0.2
                    is_unique = True
                    break

            # D. Verification confidence (multiplier)
            ver_result = verification_map.get(supplier.name) or verification_map.get(getattr(supplier, 'canonical_name', ''))
            # Use verification confidence_score if available, else default to 0.5 (unverified)
            ver_multiplier = ver_result.confidence_score if ver_result else 0.5
            
            # Base Score = A + B + C
            base_score = rel_score + prod_score + unique_score
            
            # Final Score = Base Score * D
            final_score = round(base_score * ver_multiplier, 2)
            
            # Determine Level
            if final_score >= 0.85:
                level = "Critical"
            elif final_score >= 0.70:
                level = "High"
            elif final_score >= 0.50:
                level = "Medium"
            else:
                level = "Low"

            # Generate Reasoning
            reasoning = self._generate_reasoning(
                supplier.name, 
                rel_type, 
                search_text, 
                is_unique,
                high_kws, med_kws, low_kws
            )

            res_obj = SupplierCriticality(
                supplier_name=supplier.name,
                criticality_score=final_score,
                criticality_level=level,
                reasoning=reasoning
            )
            criticality_results.append(res_obj)

            # Logging
            print(f"\nSupplier: {supplier.name}")
            print(f"Criticality Score: {final_score}")
            print(f"Level: {level}")
            print(f"Reason: {reasoning}")

        state.supplier_criticality_scores = criticality_results
        state.current_task = "Criticality assessment completed"
        
        state.history.append({
            "agent": "criticality_agent",
            "action": "calculated_criticality_scores",
            "total_suppliers": len(criticality_results),
            "status": "success"
        })

        return state

    def _generate_reasoning(self, name, rel_type, search_text, is_unique, high_kws, med_kws, low_kws) -> str:
        parts = []
        
        # Product part
        if any(kw in search_text for kw in high_kws):
            parts.append(f"Supplier manufactures core {next(kw for kw in high_kws if kw in search_text)} components")
        elif any(kw in search_text for kw in med_kws):
            parts.append(f"Supplier provides essential {next(kw for kw in med_kws if kw in search_text)} services")
        else:
            parts.append("Supplier provides non-core support services")

        # Uniqueness part
        if is_unique:
            parts.append("and appears to be a sole-source dependency.")
        else:
            parts.append("with multiple alternative sources available.")

        # Relationship part
        if rel_type == "subsidiary":
            parts.append(f"As a subsidiary, it has deep integration with the target company.")
        elif rel_type == "partner":
            parts.append(f"It maintains a strategic partnership.")
        
        return " ".join(parts)

def criticality_agent(state: AgentState) -> AgentState:
    agent = CriticalityAgent()
    return agent.calculate_criticality(state)
