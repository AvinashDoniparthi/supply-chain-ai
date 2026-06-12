from datetime import datetime
from models.state import AgentState, VerificationResult

def verification_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for verifying the accuracy of the gathered intelligence.
    In a real scenario, this would cross-reference data across multiple official sources
    like government registries, trade databases, and news reports.
    """
    print("--- VERIFICATION AGENT: Fact-Checking Findings ---")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Mock verification results for the gathered data
    mock_verifications = []
    
    # Verify Company
    if state.company:
        mock_verifications.append(VerificationResult(
            entity_name=state.company.name,
            source="Official Registry",
            verified=True,
            confidence=1.0,
            findings="Entity is active and in good standing.",
            timestamp=timestamp
        ))
    
    # Verify Suppliers
    for supplier in state.suppliers: 
        is_evergreen = "Evergreen" in supplier.name
        mock_verifications.append(VerificationResult(
            entity_name=supplier.name,
            source="Trade Database",
            verified=not is_evergreen,
            confidence=0.95 if not is_evergreen else 0.70,
            findings="Verified" if not is_evergreen else "Recent reports suggest localized delays.",
            timestamp=timestamp
        ))
    
    # Update the shared state
    state.verification_results.extend(mock_verifications)
    state.current_task = "Intelligence verification completed"
    
    # Update confidence score for this stage
    state.confidence_scores["verification"] = 0.92
    
    # Add to history
    state.history.append({
        "agent": "verification_agent",
        "action": "verified_entities",
        "verified_count": len([v for v in mock_verifications if v.verified]),
        "flagged_count": len([v for v in mock_verifications if not v.verified]),
        "status": "success"
    })
    
    return state
