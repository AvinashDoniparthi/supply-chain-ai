from models.state import AgentState, RiskAnalysis

def risk_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for identifying and assessing risks in the supply chain.
    It utilizes verified supplier information to ensure that risk analysis is grounded in reality.
    """
    print("--- RISK AGENT: Analyzing Supply Chain Vulnerabilities (Verified Data Only) ---")
    
    # 1. Map entity names to their verification status for easy lookup
    verification_map = {v.entity_name: v for v in state.verification_results}
    
    # 2. Identify unverified entities to flag as a 'Data Integrity' risk
    unverified_entities = [name for name, v in verification_map.items() if not v.verified]
    if unverified_entities:
        state.risk_assessments.append(RiskAnalysis(
            category="Data Integrity",
            threat_level="Medium",
            description=f"Risk analysis skipped for unverified entities: {', '.join(unverified_entities)}",
            potential_impact="Incomplete risk profile. Logistics or production may be halted by unconfirmed partners.",
            mitigation_recommendation="Contact legal/compliance to verify registration of these specific entities."
        ))

    # 3. Perform risk assessment ONLY on verified suppliers
    # In a real system, this would involve complex logic. Here we use rules based on supplier location/product.
    for supplier in state.suppliers:
        verification = verification_map.get(supplier.name)
        
        # EXCLUSION: Skip risk calculation if not verified or missing
        if not verification:
            state.errors.append(f"Safety Warning: Supplier {supplier.name} found but has no verification record.")
            continue
            
        if not verification.verified:
            continue
            
        # RULE 1: Geopolitical Risk (Location based)
        if supplier.location == "Hsinchu, Taiwan" and supplier.criticality == "High":
            state.risk_assessments.append(RiskAnalysis(
                category="Geopolitical",
                threat_level="High",
                description=f"Verified supplier {supplier.name} is in a high-tension regional zone.",
                potential_impact="Production stoppage if regional conflict occurs.",
                mitigation_recommendation="Establish secondary sourcing in stable regions."
            ))
            
        # RULE 2: Logistical Risk (Region based + Tier)
        if "Singapore" in supplier.location or "Netherlands" in supplier.location:
            # Adjust threat level based on verification confidence
            # Lower confidence in verification increases the perceived risk
            threat = "Medium" if (verification.confidence or 0.0) > 0.9 else "High"
            state.risk_assessments.append(RiskAnalysis(
                category="Logistical",
                threat_level=threat,
                description=f"Transit hub bottleneck for verified supplier: {supplier.name}.",
                potential_impact="Delays in component arrival impacting assembly timelines.",
                mitigation_recommendation="Diversify shipping routes or increase safety stock."
            ))

        # RULE 3: Criticality Escalation
        conf_val = verification.confidence if verification.confidence is not None else 0.0
        if supplier.criticality == "High" and conf_val < 0.95:
            state.risk_assessments.append(RiskAnalysis(
                category="Strategic",
                threat_level="Medium",
                description=f"High criticality supplier {supplier.name} has sub-optimal verification confidence ({conf_val:.2f}).",
                potential_impact="Dependency on a supplier whose operational status is not perfectly certain.",
                mitigation_recommendation="Perform an on-site audit to increase confidence."
            ))

    state.current_task = "Verified risk analysis completed"
    
    # Final confidence score is an average of mapping and verification stages
    # Robust conversion to float and handling of NoneType
    try:
        map_conf = float(state.confidence_scores.get("mapping") or 0.5)
        ver_conf = float(state.confidence_scores.get("verification") or 0.5)
        state.confidence_scores["risk_analysis"] = (map_conf + ver_conf) / 2.0
    except (ValueError, TypeError):
        state.confidence_scores["risk_analysis"] = 0.5
        state.errors.append("Error calculating combined confidence score; defaulting to 0.5")
    
    # Add to history
    state.history.append({
        "agent": "risk_agent",
        "action": "assessed_verified_risks",
        "total_risks": len(state.risk_assessments),
        "status": "success"
    })
    
    return state
