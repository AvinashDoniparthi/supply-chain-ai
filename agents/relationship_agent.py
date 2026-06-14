import logging
import re
from typing import List, Dict, Any
from models.state import AgentState
from models.relationship import RelationshipResult

logger = logging.getLogger(__name__)

def relationship_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for classifying the relationship between the target company 
    and discovered entities based on evidence text.
    """
    target_company = state.company.name if state.company else state.target_company
    target_industry = state.company.industry if state.company else None
    print(f"\n--- RELATIONSHIP AGENT: Classifying Company Relationships for {target_company} ---")

    if not target_company:
        state.errors.append("Relationship Agent: No target company name provided in state.")
        return state

    for supplier in state.suppliers:
        candidate_name = supplier.name
        evidence_snippets = supplier.evidence
        
        # Aggregate all evidence text for this candidate
        full_evidence_text = " ".join([e.get("snippet", "") for e in evidence_snippets])
        
        # Perform classification with industry context
        rel_type, confidence, reasoning = classify_relationship(
            target_company, 
            candidate_name, 
            full_evidence_text,
            target_industry=target_industry
        )
        
        # Create result object
        result = RelationshipResult(
            target_company=target_company,
            candidate_company=candidate_name,
            relationship_type=rel_type,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_text=full_evidence_text[:500] # Cap evidence text size
        )
        
        state.relationship_results.append(result)
        
        print(f"Company: {candidate_name}")
        print(f"Relationship: {rel_type}")
        print(f"Confidence: {confidence:.2f}")
        print(f"Evidence: {full_evidence_text[:200]}...")
        print("-" * 20)

    state.current_task = f"Relationship classification completed for {len(state.suppliers)} entities."
    
    # Add to history
    state.history.append({
        "agent": "relationship_agent",
        "action": "relationship_classification",
        "target": target_company,
        "results_count": len(state.relationship_results),
        "status": "success"
    })

    return state

def classify_relationship(target: str, candidate: str, text: str, target_industry: str = None) -> (str, float, str):
    """
    Rule-based classification logic to determine relationship type and confidence.
    Uses fuzzy matching for company names, broad keyword context, and industry inference.
    """
    low_text = text.lower()
    t_low = target.lower()
    c_low = candidate.lower()

    # 0. Pre-filtering: Block non-company entities and generic industry terms
    blocklist = [
        "nand flash", "dram", "ssd", "display panel", 
        "hot dogs", "restaurant", "food", "retailer", "walmart", "mac", "iphone", "ipad"
    ]
    if any(b == c_low or b in c_low for b in blocklist):
        return "unknown", 0.1, "Candidate identified as a product category, generic term, or unrelated retailer."

    # Heuristic: Must look like a company or manufacturer for tech inference
    company_suffixes = ["inc", "ltd", "corp", "group", "co", "plc", "corporation", "limited", "manufacturing", "technology"]
    is_formal_company = any(s in c_low for s in company_suffixes)

    # Define relationship weights
    weights = {
        "supplier": 0.4,
        "partner": 0.2,
        "subsidiary": 0.2,
        "unknown": 0.0,
        "competitor": -0.4,
        "customer": -0.5
    }

    # Keyword categories
    keywords = {
        "supplier": ["supplies", "supplier", "vendor", "contractor", "component", "parts", "provides", "outsourced"],
        "manufacturing": ["manufactures", "manufacture", "assembled", "factory", "production", "fab", "manufacturing", "workers", "industry"],
        "procurement": ["procurement", "purchased", "order", "sourcing", "buy", "purchasing"],
        "partner": ["partnership", "partner", "collaboration", "joint venture", "alliance", "jointly", "collaboration"],
        "subsidiary": ["subsidiary", "owned by", "division of", "parent", "acquired", "doing business as"],
        "competitor": ["competitor", "rival", "competes", "competing", "competition", "vs", "versus"],
        "lawsuit": ["lawsuit", "litigation", "sued", "infringement", "court", "legal action"],
        "customer": ["customer", "client", "buyer"]
    }

    # Industry Inference Rules (Inferred Evidence)
    inference_signals = [
        "contract", "manufacturer", "foundry", "supplier", "vendor",
        "component", "electronics", "odm", "ems", "manufacturing"
    ]
    
    # Improved industry check: Wikipedia often returns broad strings
    target_ind_low = target_industry.lower() if target_industry else ""
    is_tech_target = any(k in target_ind_low for k in ["tech", "electronics", "hardware", "computer", "semiconductor", "consumer electronics"])
    has_inference_signal = any(s in low_text for s in inference_signals)

    # Helper: Check if a name (or part of it) is in the text
    def fuzzy_match(name, text):
        # Full match
        if name in text: return True
        # Partial match for multi-word names (exclude common words)
        parts = [p for p in name.split() if len(p) > 3]
        if parts and any(p in text for p in parts): return True
        return False

    # Directionality detection (Direct Evidence)
    is_customer = False
    is_supplier = False
    
    # Check if Target supplies Candidate (Customer relationship)
    if re.search(rf"{re.escape(t_low)}.*?(?:supplies|provides|manufactures|assembled for|production for).*?{re.escape(c_low)}", low_text):
        is_customer = True
    elif re.search(rf"{re.escape(c_low)}.*?(?:customer|client|buyer) of.*?{re.escape(t_low)}", low_text):
        is_customer = True
    
    # Check if Candidate supplies Target (Supplier relationship)
    if re.search(rf"{re.escape(c_low)}.*?(?:supplies|provides|manufactures|assembled for|production for).*?{re.escape(t_low)}", low_text):
        is_supplier = True
    elif re.search(rf"{re.escape(t_low)}.*?(?:customer|client|buyer) of.*?{re.escape(c_low)}", low_text):
        is_supplier = True

    # Determine primary relationship type
    rel_type = "unknown"
    reasoning = "Insufficient evidence to determine a specific relationship."

    # Fuzzy Context Analysis (Backbone when strict regex fails)
    has_target = fuzzy_match(t_low, low_text)
    has_candidate = fuzzy_match(c_low, low_text)

    if is_customer:
        rel_type = "customer"
        reasoning = f"Direct evidence suggests {target} provides goods or services to {candidate}."
    elif is_supplier:
        rel_type = "supplier"
        reasoning = f"Direct evidence suggests {candidate} provides goods or services to {target}."
    elif any(k in low_text for k in keywords["subsidiary"]) and has_target and has_candidate:
        rel_type = "subsidiary"
        reasoning = f"Evidence suggests a parent-subsidiary or 'doing business as' relationship."
    elif any(k in low_text for k in keywords["competitor"]) and has_target and has_candidate:
        rel_type = "competitor"
        reasoning = f"Evidence mentions competition or rivalry between {target} and {candidate}."
    elif any(k in low_text for k in keywords["partner"]) and has_target and has_candidate:
        rel_type = "partner"
        reasoning = f"Evidence mentions a partnership or collaboration between {target} and {candidate}."
    elif any(k in low_text for k in keywords["supplier"]) and has_target and has_candidate:
        rel_type = "supplier"
        reasoning = f"Evidence contains supplier-related keywords involving both companies."
    elif any(k in low_text for k in keywords["manufacturing"]) and has_target and has_candidate:
        rel_type = "supplier"
        reasoning = f"Evidence mentions manufacturing or assembly context involving both companies."
    # Inference Layer
    elif is_tech_target and has_inference_signal and has_candidate and is_formal_company:
        rel_type = "supplier"
        reasoning = f"Inferred relationship: {candidate} is a known manufacturer/supplier in the {target_industry or 'tech'} industry."

    # Scoring logic
    confidence = 0.5 + weights.get(rel_type, 0.0)

    # Apply boosts
    if rel_type == "supplier":
        if any(k in low_text for k in keywords["manufacturing"]):
            confidence += 0.1
        if any(k in low_text for k in keywords["procurement"]):
            confidence += 0.1
        # Inference boost
        if is_tech_target and has_inference_signal:
            confidence += 0.15
    
    # Apply reductions
    if any(k in low_text for k in keywords["lawsuit"]):
        confidence -= 0.2
    
    # Final clamping and rounding
    confidence = round(max(0.01, min(0.98, confidence)), 2)

    return rel_type, confidence, reasoning
