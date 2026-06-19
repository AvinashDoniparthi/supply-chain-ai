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
        
        # Track seen companies for cycle protection
        target_canonical = resolver.resolve(company_name)
        seen_companies = {target_canonical}
        
        tier1_suppliers = []
        tier2_suppliers = []

        # 1. Discover Tier 1 suppliers
        discovered_data_tier1 = discovery.find_suppliers(company_name)
        
        if not discovered_data_tier1:
            logger.warning(f"No suppliers discovered for {company_name}")
            state.current_task = "Supply chain mapping failed: No suppliers found"
            return state

        for data in discovered_data_tier1:
            canonical_name = resolver.resolve(data["name"])
            if canonical_name in seen_companies:
                continue
            
            # Create Tier 1 SupplierInfo
            supplier = SupplierInfo(
                name=data["name"],
                canonical_name=canonical_name,
                location=data["location"],
                products=data["products"],
                tier=1,
                criticality=data["criticality"],
                status="Active",
                discovery_confidence=data["confidence"],
                propagated_confidence=data["confidence"],
                parent_company=company_name,
                relationship_path=[company_name, canonical_name],
                evidence=data.get("source_evidence", [])
            )
            
            state.suppliers.append(supplier)
            tier1_suppliers.append(supplier)
            seen_companies.add(canonical_name)

        # 2. Discover Tier 2 suppliers
        for tier1_supplier in tier1_suppliers:
            discovered_data_tier2 = discovery.find_suppliers(tier1_supplier.canonical_name or tier1_supplier.name)
            
            for data in discovered_data_tier2:
                canonical_name = resolver.resolve(data["name"])
                if canonical_name in seen_companies:
                    continue
                
                # Create Tier 2 SupplierInfo
                supplier = SupplierInfo(
                    name=data["name"],
                    canonical_name=canonical_name,
                    location=data["location"],
                    products=data["products"],
                    tier=2,
                    criticality=data["criticality"],
                    status="Active",
                    discovery_confidence=data["confidence"],
                    propagated_confidence=round(tier1_supplier.propagated_confidence * data["confidence"], 2),
                    parent_company=tier1_supplier.canonical_name or tier1_supplier.name,
                    relationship_path=tier1_supplier.relationship_path + [canonical_name],
                    evidence=data.get("source_evidence", [])
                )
                
                state.suppliers.append(supplier)
                tier2_suppliers.append(supplier)
                seen_companies.add(canonical_name)

        # Logging
        print("\n--- TIER DISCOVERY ---")
        print("\nTier 1 Suppliers:")
        for s in tier1_suppliers:
            print(f"- {s.canonical_name or s.name}")
        
        print("\nTier 2 Suppliers:")
        for t1 in tier1_suppliers:
            t2_for_t1 = [t2 for t2 in tier2_suppliers if t2.parent_company == (t1.canonical_name or t1.name)]
            if t2_for_t1:
                print(f"\n{t1.canonical_name or t1.name}:")
                for t2 in t2_for_t1:
                    print(f"  - {t2.canonical_name or t2.name}")

        print(f"\nTotal Tier 1: {len(tier1_suppliers)}")
        print(f"Total Tier 2: {len(tier2_suppliers)}")

        # Update the shared state metrics
        new_suppliers_added = len(tier1_suppliers) + len(tier2_suppliers)
        state.current_task = f"Supply chain mapping completed. Found {len(tier1_suppliers)} Tier 1 and {len(tier2_suppliers)} Tier 2 partners."

        # Add to history
        state.history.append({
            "agent": "supplier_agent",
            "action": "recursive_supplier_discovery",
            "company": company_name,
            "tier1_count": len(tier1_suppliers),
            "tier2_count": len(tier2_suppliers),
            "status": "success"
        })

    except Exception as e:
        error_msg = f"Supplier Agent Failure: {str(e)}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_task = "Supply chain mapping error"

    return state
