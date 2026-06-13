from models.state import AgentState, CompanyInfo
from scraping.company_scraper import CompanyScraper


def company_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for gathering and identifying core company information.
    Uses CompanyScraper to search for public data.
    """
    # Retrieve the target company name from the state
    company_name = state.target_company or "Unknown Company"

    print(f"--- COMPANY AGENT: Researching Target Company: {company_name} ---")

    # Use the scraper to fetch real data
    scraper = CompanyScraper()
    company_data = scraper.search_company(company_name)

    # Map scraped data to CompanyInfo model
    scraped_company = CompanyInfo(
        name=company_data.get("name", company_name),
        industry=company_data.get("industry"),
        headquarters=company_data.get("headquarters"),
        description=company_data.get("description"),
        website=company_data.get("website"),
        metadata={"source": "Wikipedia Scraper"},
    )

    # Update the shared state
    state.company = scraped_company
    state.current_task = f"Company identification completed for {company_name}"

    # Add to history for traceability
    state.history.append(
        {
            "agent": "company_agent",
            "action": "scraped_company_info",
            "company_name": company_name,
            "status": "success",
        }
    )

    return state
