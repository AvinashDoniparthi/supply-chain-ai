import logging
from typing import Dict, List, Any
from models.state import AgentState, SupplierInfo
from models.relationship import RelationshipResult
from utils.identity_resolution import resolver
from utils.output import agent_event, debug_log

logger = logging.getLogger(__name__)

# Relationship types allowed into the final supplier set.
RETAIN_RELATIONSHIP_TYPES = {"supplier", "upstream_supplier"}


def deduplication_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for deduplicating suppliers based on their canonical names.
    Merges evidence, products, and picks the highest confidence relationship.
    """
    agent_event("Deduplication agent started")

    if not state.suppliers:
        return state

    # 1. Group suppliers by canonical name
    canonical_groups: Dict[str, List[SupplierInfo]] = {}
    for supplier in state.suppliers:
        # Re-resolve existing canonical values so older aliases collapse into
        # the current centralized canonical identity.
        supplier.canonical_name = resolver.resolve(supplier.canonical_name or supplier.name)

        c_name = supplier.canonical_name
        if c_name not in canonical_groups:
            canonical_groups[c_name] = []
        canonical_groups[c_name].append(supplier)

    deduplicated_suppliers: List[SupplierInfo] = []

    for c_name, group in canonical_groups.items():
        if len(group) == 1:
            supplier = group[0]
            supplier.canonical_name = c_name
            supplier.name = resolver.display_name(c_name)
            deduplicated_suppliers.append(supplier)
            continue

        debug_log(logger, "Merging %s entities into: %s", len(group), c_name)
        for s in group:
            debug_log(logger, "  - %s", s.name)

        # Merge logic
        primary = group[0]  # Use the first one as the base

        merged_products = set()
        merged_evidence = []
        max_confidence = 0.0
        max_propagated_confidence = 0.0
        parent_companies = []
        relationship_paths = []

        # Track unique evidence links
        seen_links = set()
        seen_parent_companies = set()
        seen_relationship_paths = set()

        for s in group:
            merged_products.update(s.products)
            for e in s.evidence:
                link = e.get("link")
                if link not in seen_links:
                    merged_evidence.append(e)
                    seen_links.add(link)

            if s.discovery_confidence > max_confidence:
                max_confidence = s.discovery_confidence

            if s.propagated_confidence > max_propagated_confidence:
                max_propagated_confidence = s.propagated_confidence

            if s.parent_company and s.parent_company not in seen_parent_companies:
                parent_companies.append(s.parent_company)
                seen_parent_companies.add(s.parent_company)

            if s.relationship_path:
                path_key = " -> ".join(s.relationship_path)
                if path_key not in seen_relationship_paths:
                    relationship_paths.append(path_key)
                    seen_relationship_paths.add(path_key)

        # Create a new merged supplier info
        merged_supplier = SupplierInfo(
            name=resolver.display_name(c_name),
            canonical_name=c_name,
            location=primary.location,  # Could be improved by picking a non-"Unknown" location
            products=list(merged_products),
            tier=max(s.tier for s in group),
            criticality=(
                "High" if any(s.criticality == "High" for s in group) else "Medium"
            ),
            status="Active",
            discovery_confidence=max_confidence,
            propagated_confidence=max_propagated_confidence,
            parent_company="; ".join(parent_companies) if parent_companies else None,
            relationship_path=relationship_paths,
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

    # Filter suppliers based on supply-chain relationship labels only.
    filtered_suppliers = []
    removed_count = 0
    has_relationship_data = bool(deduplicated_relationships)

    for supplier in deduplicated_suppliers:
        supplier_name = supplier.canonical_name or supplier.name
        rel_result = rel_map.get(supplier_name)

        # If relationship classification completely failed, keep discovered
        # suppliers rather than deleting the entire run. Otherwise no-match
        # entities are not retained as suppliers.
        if not rel_result:
            if not has_relationship_data:
                filtered_suppliers.append(supplier)
            debug_log(
                logger,
                "[RELATIONSHIP FILTER] Supplier: %s | Classification: N/A | Confidence: N/A | Removed: %s",
                supplier_name,
                bool(has_relationship_data),
            )
            if has_relationship_data:
                removed_count += 1
            continue

        rel_type = rel_result.relationship_type.lower()
        rel_conf = rel_result.confidence_score

        if rel_type not in RETAIN_RELATIONSHIP_TYPES:
            removed_count += 1
            debug_log(
                logger,
                "[RELATIONSHIP FILTER] Supplier: %s | Classification: %s | Confidence: %.2f | Removed: True",
                supplier_name,
                rel_type,
                rel_conf,
            )
            continue

        filtered_suppliers.append(supplier)
        debug_log(
            logger,
            "[RELATIONSHIP FILTER] Supplier: %s | Classification: %s | Confidence: %.2f | Removed: False",
            supplier_name,
            rel_type,
            rel_conf,
        )

    # Update state
    state.suppliers = filtered_suppliers
    state.relationship_results = deduplicated_relationships

    debug_log(logger, "[DEDUPLICATION SUMMARY]")
    debug_log(logger, "Total Unique Entities Discovered: %s", len(state.discovered_entities))
    debug_log(logger, "Entities Retained After Filtering: %s", len(filtered_suppliers))
    debug_log(logger, "Entities Removed (non-supplier labels): %s", removed_count)
    debug_log(logger, "Retained Relationship Types: %s", sorted(RETAIN_RELATIONSHIP_TYPES))
    for s in state.discovered_entities:
        rel_result = rel_map.get(s.canonical_name or s.name)
        if rel_result:
            rel_type = rel_result.relationship_type
            rel_conf = rel_result.confidence_score
            is_retained = s in filtered_suppliers
            status = "RETAIN" if is_retained else "REMOVE"
            debug_log(logger, "  - %s: %s (%.2f) -> %s", s.name, rel_type, rel_conf, status)
        else:
            status = "RETAIN" if s in filtered_suppliers else "REMOVE"
            debug_log(logger, "  - %s: N/A -> %s", s.name, status)

    state.current_task = f"Deduplicated into {len(state.discovered_entities)} entities. Retained {len(state.suppliers)} for verification."
    debug_log(
        logger,
        "[PIPELINE COUNT] After deduplication_agent: %s suppliers",
        len(state.suppliers),
    )
    agent_event(f"Deduplication agent completed: {len(state.suppliers)} retained")
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
