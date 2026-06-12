from models.state import AgentState, SupplierInfo


def supplier_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for mapping the supply chain of the target company.
    In a real scenario, this would scrape shipping records or supplier directories.
    Currently populates the state with mock supplier data.
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

    # Update the shared state
    state.suppliers.extend(mock_suppliers)
    state.current_task = "Supply chain mapping completed"

    # Update confidence score for this stage
    state.confidence_scores["mapping"] = 0.85

    # Add to history
    state.history.append(
        {
            "agent": "supplier_agent",
            "action": "mapped_suppliers",
            "count": len(mock_suppliers),
            "status": "success",
        }
    )

    return state
