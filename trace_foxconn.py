
from scraping.supplier_discovery import SupplierDiscoveryScraper
from agents.relationship_agent import classify_relationship
import json

def trace_foxconn():
    target = "Foxconn"
    scraper = SupplierDiscoveryScraper()
    suppliers = scraper.find_suppliers(target)
    
    print(f"Discovered {len(suppliers)} candidates for {target}:")
    results = []
    for s in suppliers:
        name = s['name']
        evidence_text = " ".join([e['snippet'] for e in s['source_evidence']])
        rel_type, confidence, reasoning = classify_relationship(target, name, evidence_text)
        
        results.append({
            "name": name,
            "rel_type": rel_type,
            "confidence": confidence,
            "reasoning": reasoning,
            "evidence": evidence_text
        })
        
        print(f"\nCandidate: {name}")
        print(f"Relationship: {rel_type}")
        print(f"Confidence: {confidence}")
        print(f"Reasoning: {reasoning}")
        print(f"Evidence Snippet: {evidence_text[:200]}...")

    # Check AgentState population (simulated)
    from models.state import AgentState, SupplierInfo
    from agents.supplier_agent import supplier_agent
    from agents.relationship_agent import relationship_agent
    from workflows.supply_chain_workflow import supply_chain_app
    
    state = AgentState(target_company=target)
    # Simulate workflow
    # Note: we need to see if relationship_agent is actually called in the real workflow
    print("\nChecking if relationship_agent is in the workflow...")
    # LangGraph app.get_graph().nodes
    try:
        nodes = supply_chain_app.get_graph().nodes
        print(f"Workflow nodes: {list(nodes.keys())}")
        has_rel_agent = "relationship_agent" in nodes
        print(f"Is relationship_agent in workflow? {has_rel_agent}")
    except Exception as e:
        print(f"Could not inspect workflow: {e}")

if __name__ == "__main__":
    trace_foxconn()
