from models.state import AgentState, CompanyInfo


def company_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for gathering and identifying core company information.
    In a real scenario, this would involve calling scrapers or APIs.
    Currently populates the state with mock data for demonstration.
    """
    # Retrieve the target company name from the state
    company_name = state.target_company or "Unknown Company"
    
    print(f"--- COMPANY AGENT: Researching Target Company: {company_name} ---")

    # Mock data for the target company, using the provided name
    mock_company = CompanyInfo(
        name=company_name,
        industry="Semiconductors",
        headquarters="San Jose, California, USA",
        description=f"{company_name} is a leading manufacturer of high-performance AI chips and specialized hardware accelerators.",
        website="https://technova-example.ai",
        metadata={"stock_symbol": "TNS", "market_cap": "$12.5B", "founded_year": 2015},
    )

    # Update the shared state
    state.company = mock_company
    state.current_task = f"Company identification completed for {company_name}"

    # Add to history for traceability
    state.history.append(
        {
            "agent": "company_agent",
            "action": "populated_company_info",
            "company_name": company_name,
            "status": "success",
        }
    )

    return state
