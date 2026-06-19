import logging
from typing import Dict, List, Any
from models.state import AgentState, SupplierInfo
from models.relationship import RelationshipResult
from utils.identity_resolution import resolver

logger = logging.getLogger(__name__)

# Threshold for relationship confidence - below this, we retain all suppliers
# Above this, we filter by relationship type
RELATIONSHIP_FILTER_CONFIDENCE = 0.80

# Relationship types that should be removed if confidence is high
REJECT_RELATIONSHIP_TYPES = {"competitor", "customer", "distributor", "unrelated"}


def deduplication_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for deduplicating suppliers based on their canonical names.
    Merges evidence, products, and picks the highest confidence relationship.
    """
    print("\n--- DEDUPLICATION AGENT: Merging Entities by Identity ---")

    if not state.suppliers:
        return state

    # 1. Group suppliers by canonical name
    canonical_groups: Dict[str, List[SupplierInfo]] = {}
    for supplier in state.suppliers:
        # Ensure canonical name is set (it should be from supplier_agent)
        if not supplier.canonical_name:
            supplier.canonical_name = resolver.resolve(supplier.name)

        c_name = supplier.canonical_name
        if c_name not in canonical_groups:
            canonical_groups[c_name] = []
        canonical_groups[c_name].append(supplier)

    deduplicated_suppliers: List[SupplierInfo] = []

    for c_name, group in canonical_groups.items():
        if len(group) == 1:
            deduplicated_suppliers.append(group[0])
            continue

        print(f"Merging {len(group)} entities into: {c_name}")
        for s in group:
            print(f"  - {s.name}")

        # Merge logic
        primary = group[0]  # Use the first one as the base

        merged_products = set()
        merged_evidence = []
        max_confidence = 0.0

        # Track unique evidence links
        seen_links = set()

        for s in group:
            merged_products.update(s.products)
            for e in s.evidence:
                link = e.get("link")
                if link not in seen_links:
                    merged_evidence.append(e)
                    seen_links.add(link)

            if s.discovery_confidence > max_confidence:
                max_confidence = s.discovery_confidence

        # Create a new merged supplier info
        merged_supplier = SupplierInfo(
            name=c_name,  # Use canonical name as the name for the deduplicated entry
            canonical_name=c_name,
            location=primary.location,  # Could be improved by picking a non-"Unknown" location
            products=list(merged_products),
            tier=min(s.tier for s in group),  # Pick highest tier (lowest number)
            criticality=(
                "High" if any(s.criticality == "High" for s in group) else "Medium"
            ),
            status="Active",
            discovery_confidence=max_confidence,
            evidence=merged_evidence,
        )

        # Find better location if available
        for s in group:
            if s.location and s.location != "Unknown (Verified by Research)":
                merged_supplier.location = s.location
                break

        deduplicated_suppliers.append(merged_supplier)

    # 2. Deduplicate Relationship Results
    # We need to map the candidate_company in RelationshipResult to canonical names
    rel_canonical_groups: Dict[str, List[RelationshipResult]] = {}
    for rel in state.relationship_results:
        c_name = resolver.resolve(rel.candidate_company)
        if c_name not in rel_canonical_groups:
            rel_canonical_groups[c_name] = []
        rel_canonical_groups[c_name].append(rel)

    deduplicated_relationships: List[RelationshipResult] = []
    for c_name, group in rel_canonical_groups.items():
        # Pick the one with the highest confidence
        best_rel = max(group, key=lambda x: x.confidence_score)

        # Update name to canonical for consistency if we want
        best_rel.candidate_company = c_name

        deduplicated_relationships.append(best_rel)

    # 3. Preserve and Filter
    # Store all unique discovered entities for traceability
    state.discovered_entities = deduplicated_suppliers

    # Build mapping of supplier to relationship data
    rel_map = {r.candidate_company: r for r in deduplicated_relationships}

    # Filter suppliers based on improved logic:
    # - Retain all suppliers with relationship_type == "unknown"
    # - Retain all suppliers with relationship confidence < RELATIONSHIP_FILTER_CONFIDENCE
    # - Only remove suppliers with explicitly bad types AND high confidence
    filtered_suppliers = []
    removed_count = 0

    for supplier in deduplicated_suppliers:
        supplier_name = supplier.canonical_name or supplier.name
        rel_result = rel_map.get(supplier_name)

        # If no relationship data, retain the supplier (be conservative)
        if not rel_result:
            filtered_suppliers.append(supplier)
            print(
                f"[RELATIONSHIP FILTER] Supplier: {supplier_name} | Classification: N/A | Confidence: N/A | Removed: False"
            )
            continue

        rel_type = rel_result.relationship_type
        rel_conf = rel_result.confidence_score

        # Retain if unknown relationship (degraded mode)
        if rel_type == "unknown":
            filtered_suppliers.append(supplier)
            print(
                f"[RELATIONSHIP FILTER] Supplier: {supplier_name} | Classification: {rel_type} | Confidence: {rel_conf:.2f} | Removed: False (unknown retained)"
            )
            continue

        # Retain if confidence is below threshold (be conservative with low-confidence data)
        if rel_conf < RELATIONSHIP_FILTER_CONFIDENCE:
            filtered_suppliers.append(supplier)
            print(
                f"[RELATIONSHIP FILTER] Supplier: {supplier_name} | Classification: {rel_type} | Confidence: {rel_conf:.2f} | Removed: False (low confidence retained)"
            )
            continue

        # Only remove if explicitly bad type AND high confidence
        if (
            rel_type in REJECT_RELATIONSHIP_TYPES
            and rel_conf >= RELATIONSHIP_FILTER_CONFIDENCE
        ):
            removed_count += 1
            print(
                f"[RELATIONSHIP FILTER] Supplier: {supplier_name} | Classification: {rel_type} | Confidence: {rel_conf:.2f} | Removed: True"
            )
            continue

        # Default: retain (be conservative)
        filtered_suppliers.append(supplier)
        print(
            f"[RELATIONSHIP FILTER] Supplier: {supplier_name} | Classification: {rel_type} | Confidence: {rel_conf:.2f} | Removed: False"
        )

    # Update state
    state.suppliers = filtered_suppliers
    state.relationship_results = deduplicated_relationships

    print(f"\n--- DEDUPLICATION SUMMARY ---")
    print(f"Total Unique Entities Discovered: {len(state.discovered_entities)}")
    print(f"Entities Retained After Filtering: {len(filtered_suppliers)}")
    print(f"Entities Removed (High-confidence rejects): {removed_count}")
    print(f"Filter Confidence Threshold: {RELATIONSHIP_FILTER_CONFIDENCE}")
    for s in state.discovered_entities:
        rel_result = rel_map.get(s.canonical_name or s.name)
        if rel_result:
            rel_type = rel_result.relationship_type
            rel_conf = rel_result.confidence_score
            is_retained = s in filtered_suppliers
            status = "RETAIN" if is_retained else "REMOVE"
            print(f"  - {s.name}: {rel_type} ({rel_conf:.2f}) -> {status}")
        else:
            status = "RETAIN" if s in filtered_suppliers else "REMOVE"
            print(f"  - {s.name}: N/A -> {status}")

    state.current_task = f"Deduplicated into {len(state.discovered_entities)} entities. Retained {len(state.suppliers)} for verification."
    print(
        f"[PIPELINE COUNT] After deduplication_agent: {len(state.suppliers)} suppliers"
    )
    state.history.append(
        {
            "agent": "deduplication_agent",
            "action": "identity_based_deduplication_and_filtering",
            "total_discovered": len(state.discovered_entities),
            "valid_suppliers": len(state.suppliers),
            "status": "success",
        }
    )

    return state
