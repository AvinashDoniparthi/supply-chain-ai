import json
import os
from langchain_core.tools import tool

@tool
def get_supplier_info(name: str) -> str:
    """
    Retrieves information about a specific supplier from the database.
    """
    # Normalize name for filename
    base_name = name.lower().replace(" ", "_").replace(",", "").replace(".", "")
    possible_files = [
        f"database/{base_name}_info.json",
        f"database/{base_name}.json"
    ]
    
    for filename in possible_files:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.dumps(json.load(f), indent=2)
                
    return f"No detailed information found for supplier: {name}. Checked {possible_files}"

@tool
def get_risk_info(name: str) -> str:
    """
    Retrieves risk assessment summary for a specific supplier from existing analysis records.
    """
    # In a real app, this might query a centralized risk DB. 
    # For now, we search the database directory for files containing risk info.
    return f"Risk assessment lookup for {name} initiated. (Mock implementation)"

@tool
def get_historical_trends(name: str) -> str:
    """
    Retrieves historical supply chain health trends for a company from the history database.
    """
    base_name = name.lower().replace(" ", "_").replace(",", "").replace(".", "")
    filename = f"database/history/{base_name}.json"
    
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.dumps(json.load(f), indent=2)
            
    return f"No historical trend data found for: {name} in {filename}"
