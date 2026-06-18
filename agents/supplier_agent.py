from models.state import AgentState, SupplierInfo
from scraping.supplier_discovery import SupplierDiscoveryScraper
from utils.identity_resolution import resolver
import logging

logger = logging.getLogger(__name__)

def supplier_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for mapping the supply chain of the target company.
    Uses real-world web discovery to identify suppliers and partners.
    """
    company_name = state.company.name if state.company else state.target_company
    print(f"--- SUPPLIER AGENT: Mapping Real Supply Chain for {company_name} ---")

    if not company_name:
        state.errors.append("Supplier Agent: No target company name provided in state.")
        return state

    try:
        # Initialize the real discovery scraper
        discovery = SupplierDiscoveryScraper()
        
        # Search for real suppliers
        discovered_suppliers = discovery.find_suppliers(company_name)
        
        if not discovered_suppliers:
            logger.warning(f"No suppliers discovered for {company_name}")
            state.current_task = "Supply chain mapping failed: No suppliers found"
            return state

        new_suppliers_added = 0
        total_confidence = 0
        
        for data in discovered_suppliers:
            # Resolve identity to canonical name
            canonical_name = resolver.resolve(data["name"])
            
            # Create SupplierInfo object
            supplier = SupplierInfo(
                name=data["name"],
                canonical_name=canonical_name,
                location=data["location"],
                products=data["products"],
                tier=data["tier"],
                criticality=data["criticality"],
                status="Active",
                discovery_confidence=data["confidence"],
                evidence=data.get("source_evidence", [])
            )
            
            # Simple deduplication by raw name for initial mapping
            if not any(s.name == supplier.name for s in state.suppliers):
                state.suppliers.append(supplier)
                new_suppliers_added += 1
                total_confidence += data["confidence"]

        # Update the shared state metrics
        avg_confidence = total_confidence / new_suppliers_added if new_suppliers_added > 0 else 0.5
        state.confidence_scores["mapping"] = round(avg_confidence, 2)
        state.current_task = f"Supply chain mapping completed. Found {new_suppliers_added} partners."

        # Add to history
        state.history.append({
            "agent": "supplier_agent",
            "action": "real_supplier_discovery",
            "company": company_name,
            "new_suppliers_count": new_suppliers_added,
            "avg_confidence": avg_confidence,
            "status": "success"
        })

    except Exception as e:
        error_msg = f"Supplier Agent Failure: {str(e)}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_task = "Supply chain mapping error"

    return state
