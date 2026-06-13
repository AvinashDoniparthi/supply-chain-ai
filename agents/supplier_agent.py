from models.state import AgentState, SupplierInfo


def supplier_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for mapping the supply chain of the target company.
    In a real scenario, this would scrape shipping records or supplier directories.
    Currently populates the state with mock supplier data.
    
    This implementation is idempotent: it will not add duplicate suppliers
    if executed multiple times on the same state.
    """
    print("--- SUPPLIER AGENT: Mapping Supply Chain ---")

    # Mock supplier list relevant to a semiconductor company
    mock_suppliers = [
        SupplierInfo(
            name="Global Lithography Systems",
            location="Veldhoven, Netherlands",
            products=["EUV Lithography Machines"],
            tier=1,
            criticality="High",
            status="Active",
        ),
        SupplierInfo(
            name="Pacific Wafer Corp",
            location="Hsinchu, Taiwan",
            products=["Silicon Wafers", "Raw Ingots"],
            tier=1,
            criticality="High",
            status="Active",
        ),
        SupplierInfo(
            name="Evergreen Logistics",
            location="Singapore",
            products=["Global Shipping", "Warehousing"],
            tier=2,
            criticality="Medium",
            status="Active",
        ),
        SupplierInfo(
            name="Alpine Specialty Gases",
            location="Bern, Switzerland",
            products=["High-purity Argon", "Neon"],
            tier=2,
            criticality="High",
            status="Active",
        ),
    ]

    # Identify existing suppliers to avoid duplicates (Name + Location)
    existing_supplier_ids = {
        (s.name, s.location) for s in state.suppliers
    }

    new_suppliers_added = 0
    for supplier in mock_suppliers:
        supplier_id = (supplier.name, supplier.location)
        if supplier_id not in existing_supplier_ids:
            state.suppliers.append(supplier)
            existing_supplier_ids.add(supplier_id)
            new_suppliers_added += 1

    # Update the shared state
    state.current_task = "Supply chain mapping completed"

    # Update confidence score for this stage
    state.confidence_scores["mapping"] = 0.85

    # Add to history
    state.history.append(
        {
            "agent": "supplier_agent",
            "action": "mapped_suppliers",
            "new_suppliers_count": new_suppliers_added,
            "total_suppliers_count": len(state.suppliers),
            "status": "success",
        }
    )

    return state
