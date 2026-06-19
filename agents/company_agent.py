from models.state import AgentState, CompanyInfo
from scraping.company_scraper import CompanyScraper
from utils.identity_resolution import resolver


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

    # Initialize traversal state for LangGraph tier discovery
    canonical_target = resolver.resolve(scraped_company.name)
    if canonical_target not in state.seen_companies:
        state.seen_companies.append(canonical_target)
    if scraped_company.name not in state.mapping_queue:
        state.mapping_queue.append(scraped_company.name)
    state.current_depth = 0

    # HARDCODED FALLBACK FOR MAJOR TARGETS (to ensure inference works)
    if not state.company.industry or state.company.industry == "Unknown":
        name_low = company_name.lower()
        if "apple" in name_low:
            state.company.industry = "Consumer Electronics, Hardware, Software"
        elif "foxconn" in name_low or "hon hai" in name_low:
            state.company.industry = "Electronic Manufacturing Services, Hardware"
        elif "nvidia" in name_low:
            state.company.industry = "Semiconductors, Hardware"

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
