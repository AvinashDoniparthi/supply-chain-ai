from models.state import AgentState, CompanyInfo


def company_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for gathering and identifying core company information.
    In a real scenario, this would involve calling scrapers or APIs.
    Currently populates the state with mock data for demonstration.
    """
    print("--- COMPANY AGENT: Researching Target Company ---")

    # Mock data for the target company
    mock_company = CompanyInfo(
        name="TechNova Solutions",
        industry="Semiconductors",
        headquarters="San Jose, California, USA",
        description="A leading manufacturer of high-performance AI chips and specialized hardware accelerators.",
        website="https://technova-example.ai",
        metadata={"stock_symbol": "TNS", "market_cap": "$12.5B", "founded_year": 2015},
    )

    # Update the shared state
    state.company = mock_company
    state.current_task = "Company identification completed"

    # Add to history for traceability
    state.history.append(
        {
            "agent": "company_agent",
            "action": "populated_company_info",
            "status": "success",
        }
    )

    return state
