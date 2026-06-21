from models.state import AgentState, SupplierInfo
from scraping.supplier_discovery import (
    SupplierDiscoveryScraper,
    candidate_competes_with_target,
    supplier_evidence_is_strong,
    supplier_evidence_explicitly_links_candidate_to_source,
    normalize_supplier_candidate_name,
    validate_supplier_candidate_name,
    unrelated_energy_candidate_without_supply_evidence,
)
from utils.identity_resolution import resolver
from utils.output import OutputMode, agent_event, debug_log, emit, progress
from utils.runtime_controls import (
    emit_limit_once,
    finish_stage,
    start_stage,
    stop_if_timed_out,
    timeout_stage,
)
import logging
import re

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 50
MIN_DISCOVERY_CONFIDENCE = 0.75
MAX_SUPPLIERS_PER_DISCOVERY = 5


def _is_valid_supplier_name(name: str, confidence: float):
    if confidence < MIN_DISCOVERY_CONFIDENCE:
        return False, "Low confidence"

    if not name or len(name.strip()) < 3:
        return False, "Too short"

    clean_name = name.strip()
    if re.search(r"[?.!;:]{1,}$", clean_name):
        return False, "Looks like a sentence fragment or title"

    if clean_name.lower() in {
        "this",
        "it",
        "they",
        "the",
        "company",
        "group",
        "supplier",
        "partner",
        "contract",
        "contracts",
        "customer",
        "customers",
        "suppliers",
        "partners",
    }:
        return False, "Generic placeholder"

    valid_candidate, rejection_reason = validate_supplier_candidate_name(clean_name)
    if not valid_candidate:
        return False, rejection_reason

    if re.search(
        r"\b(?:and|for|of|by|with|from|about)\b", clean_name.lower()
    ) and not re.search(
        r"\b(Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited)\b",
        clean_name,
        re.IGNORECASE,
    ):
        return False, "Likely sentence fragment or relationship phrase"

    if re.search(r"[^A-Za-z0-9&\s\.\-',]", clean_name):
        return False, "Contains unsupported punctuation or symbols"

    if not clean_name[0].isupper() and not re.match(r"^[0-9]", clean_name):
        return False, "Does not resemble an organization name"

    if (
        len(clean_name.split()) == 1
        and len(clean_name) < 4
        and not re.search(
            r"\b(Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited)\b",
            clean_name,
            re.IGNORECASE,
        )
    ):
        return False, "Single-word name looks too short to be valid"

    return True, ""


def supplier_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for mapping the supply chain of the target company.
    Uses real-world web discovery to identify suppliers and partners.
    Processes exactly one company from the mapping queue per invocation.
    """
    target_name = state.company.name if state.company else state.target_company
    start_stage(state, "supplier_discovery")
    progress(2, 6, "Discovering Suppliers")
    agent_event(f"Supplier agent started: {target_name}")

    if stop_if_timed_out(state, "supplier_discovery"):
        state.mapping_queue = []
        return state

    if not target_name:
        state.errors.append("Supplier Agent: No target company name provided in state.")
        finish_stage(state, "supplier_discovery")
        return state

    if not state.mapping_queue:
        logger.warning("Supplier Agent: mapping_queue is empty. Nothing to process.")
        state.current_task = "No companies left in mapping queue"
        finish_stage(state, "supplier_discovery")
        return state

    if len(state.mapping_queue) > state.max_mapping_queue_size + 1:
        del state.mapping_queue[state.max_mapping_queue_size + 1 :]
        emit_limit_once(
            state,
            "mapping_queue_size",
            f"Mapping queue capped at {state.max_mapping_queue_size} companies.",
        )

    processed = state.runtime_counters.get("supplier_companies_processed", 0)
    if processed >= state.max_total_suppliers_processed:
        state.mapping_queue = []
        emit_limit_once(
            state,
            "total_suppliers_processed",
            f"Total supplier processing cap reached ({state.max_total_suppliers_processed}).",
        )
        timeout_stage(state, "supplier_discovery") if stop_if_timed_out(
            state, "supplier_discovery"
        ) else finish_stage(state, "supplier_discovery")
        return state

    try:
        # Pop the next company from the queue and resolve it
        current_company = state.mapping_queue.pop(0)
        state.runtime_counters["supplier_companies_processed"] = processed + 1
        canonical_current = resolver.resolve(current_company)
        canonical_seen_companies = {
            resolver.resolve(company) for company in state.seen_companies
        }
        canonical_queued_companies = {
            resolver.resolve(company) for company in state.mapping_queue
        }
        debug_log(
            logger,
            "Processing queued company: %s (canonical: %s)",
            current_company,
            canonical_current,
        )

        # Determine parent tier for depth and propagation calculations
        parent_supplier = None
        if current_company != target_name:
            # Locate the supplier entry corresponding to the current company
            # (this will be the parent for any discovered suppliers).
            parent_supplier = next(
                (
                    s
                    for s in state.suppliers
                    if resolver.resolve(s.canonical_name or s.name) == canonical_current
                    or resolver.resolve(s.name) == canonical_current
                ),
                None,
            )

        parent_tier = parent_supplier.tier if parent_supplier else 0
        state.current_depth = parent_tier
        next_tier = parent_tier + 1

        # Note: we intentionally do not skip processing a dequeued company even
        # if its canonical name appears in `seen_companies`. `seen_companies`
        # prevents re-enqueueing duplicates, but dequeued companies must still be
        # processed so their downstream suppliers are discovered.

        discovery = SupplierDiscoveryScraper(runtime_state=state, prefer_curated=True)
        discovered_data = discovery.find_suppliers(current_company)

        # If the discovery returned nothing, attempt common aliases from the
        # identity resolver mapping (e.g. 'TSMC' -> 'Taiwan Semiconductor...')
        # This helps tests and real-world lookups where callers may use short
        # or canonical forms inconsistently.
        if not discovered_data:
            for alias in resolver.aliases_for(canonical_current):
                if alias == current_company:
                    continue
                discovered_data = discovery.find_suppliers(alias)
                if discovered_data:
                    break

        if not discovered_data:
            logger.warning(f"No suppliers discovered for {current_company}")
            state.current_task = (
                f"Supply chain mapping failed: No suppliers found for {current_company}"
            )
            if not state.mapping_queue:
                finish_stage(state, "supplier_discovery")
            return state

        valid_candidates = []
        seen_candidate_canonicals = set()
        for data in discovered_data:
            raw_candidate_name = data.get("name", "").strip()
            candidate_tier = next_tier
            evidence_ok, evidence_reason = supplier_evidence_is_strong(
                data.get("source_evidence", []),
                candidate_tier,
                data.get("confidence", 0.0),
                raw_candidate_name,
                current_company,
            )
            logger.info(evidence_reason)
            if not evidence_ok:
                logger.info(
                    f"[EVIDENCE FILTER] Rejected: {raw_candidate_name} Reason: {evidence_reason}"
                )
                continue

            candidate_name = normalize_supplier_candidate_name(
                raw_candidate_name, current_company
            )
            if not candidate_name:
                logger.info(
                    f"[FILTER] Rejected: {raw_candidate_name} Reason: Not an identifiable organization"
                )
                continue

            if candidate_name != raw_candidate_name:
                logger.info(
                    f"[NORMALIZE] Candidate: {raw_candidate_name} -> {candidate_name}"
                )
                data = {**data, "name": candidate_name}

            canonical_name = resolver.resolve(candidate_name)

            if candidate_competes_with_target(target_name, candidate_name) and not (
                supplier_evidence_explicitly_links_candidate_to_source(
                    candidate_name,
                    target_name,
                    data.get("source_evidence", []),
                )
            ):
                logger.info(
                    f"[FILTER] Rejected: {candidate_name} Reason: Competitor without explicit supplier evidence to {target_name}"
                )
                continue

            if unrelated_energy_candidate_without_supply_evidence(
                candidate_name,
                current_company,
                data.get("source_evidence", []),
            ):
                logger.info(
                    f"[FILTER] Rejected: {candidate_name} Reason: Unrelated energy entity without direct supply evidence"
                )
                continue

            valid_name, rejection_reason = _is_valid_supplier_name(
                candidate_name, data.get("confidence", 0.0)
            )
            if not valid_name:
                logger.info(
                    f"[FILTER] Rejected: {candidate_name} Reason: {rejection_reason}"
                )
                continue

            if (
                canonical_name in canonical_seen_companies
                or canonical_name in canonical_queued_companies
            ):
                logger.info(f"[DEDUP] Skipped duplicate: {canonical_name}")
                continue

            if canonical_name in seen_candidate_canonicals:
                logger.info(
                    f"[DEDUP] Skipped duplicate candidate within batch: {canonical_name}"
                )
                continue

            seen_candidate_canonicals.add(canonical_name)
            valid_candidates.append({**data, "canonical_name": canonical_name})

        logger.info(
            f"[TOP-K] Candidates Found: {len(valid_candidates)} Candidates Retained: {min(len(valid_candidates), state.max_candidates_per_company)}"
        )
        valid_candidates.sort(key=lambda x: x["confidence"], reverse=True)
        if len(valid_candidates) > state.max_candidates_per_company:
            emit_limit_once(
                state,
                f"max_candidates:{current_company}",
                f"Max candidates reached for {current_company}.",
            )
        valid_candidates = valid_candidates[: state.max_candidates_per_company]

        if not valid_candidates:
            logger.warning(
                f"No valid supplier candidates after filtering for {current_company}"
            )
            state.current_task = f"Supply chain mapping completed for {current_company} with no valid filtered suppliers."
            state.history.append(
                {
                    "agent": "supplier_agent",
                    "action": "queue_based_supplier_discovery",
                    "company": current_company,
                    "discovered_count": 0,
                    "queue_length": len(state.mapping_queue),
                    "status": "filtered_out",
                }
            )
            if not state.mapping_queue:
                finish_stage(state, "supplier_discovery")
            return state

        discovered_suppliers = []
        discovery_timed_out = stop_if_timed_out(state, "supplier_discovery")
        for data in valid_candidates:
            if len(state.suppliers) >= state.max_total_suppliers_processed:
                emit_limit_once(
                    state,
                    "total_suppliers_processed",
                    f"Total supplier processing cap reached ({state.max_total_suppliers_processed}).",
                )
                state.mapping_queue = []
                break

            canonical_name = data["canonical_name"]

            if current_company != target_name and next_tier > state.max_depth:
                logger.info(
                    f"Skipping supplier beyond max_depth: {data['name']} (tier={next_tier})"
                )
                continue

            propagated_confidence = data["confidence"]
            parent_company_name = target_name
            relationship_path = [target_name, canonical_name]

            if parent_supplier:
                propagated_confidence = round(
                    parent_supplier.propagated_confidence * data["confidence"] + 1e-9,
                    2,
                )
                parent_company_name = (
                    parent_supplier.canonical_name or parent_supplier.name
                )
                relationship_path = parent_supplier.relationship_path + [canonical_name]

            supplier = SupplierInfo(
                name=data["name"],
                canonical_name=canonical_name,
                location=data["location"],
                products=data["products"],
                tier=next_tier,
                criticality=data["criticality"],
                status="Active",
                discovery_confidence=data["confidence"],
                propagated_confidence=propagated_confidence,
                parent_company=parent_company_name,
                relationship_path=relationship_path,
                evidence=data.get("source_evidence", []),
            )

            state.suppliers.append(supplier)
            state.seen_companies.append(canonical_name)
            discovered_suppliers.append(supplier)

            if discovery_timed_out:
                state.mapping_queue = []
                continue

            if next_tier < state.max_depth:
                if len(state.mapping_queue) >= state.max_mapping_queue_size:
                    logger.warning(
                        f"[QUEUE LIMIT] Queue full Skipped: {canonical_name}"
                    )
                    emit_limit_once(
                        state,
                        "mapping_queue_size",
                        f"Mapping queue capped at {state.max_mapping_queue_size} companies.",
                    )
                else:
                    state.mapping_queue.append(canonical_name)

        emit("Supplier discoveries:", OutputMode.NORMAL)
        for supplier in discovered_suppliers:
            emit(
                f"- {supplier.canonical_name or supplier.name} (tier={supplier.tier})",
                OutputMode.NORMAL,
            )

        state.current_task = (
            f"Supply chain mapping completed for {current_company}. "
            f"Discovered {len(discovered_suppliers)} supplier(s)."
        )
        agent_event(f"Supplier agent completed: {len(discovered_suppliers)} discovered")

        if discovery_timed_out:
            timeout_stage(state, "supplier_discovery")
        elif not state.mapping_queue:
            finish_stage(state, "supplier_discovery")

        state.history.append(
            {
                "agent": "supplier_agent",
                "action": "queue_based_supplier_discovery",
                "company": current_company,
                "discovered_count": len(discovered_suppliers),
                "queue_length": len(state.mapping_queue),
                "status": "success",
            }
        )

    except Exception as e:
        error_msg = f"Supplier Agent Failure: {str(e)}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_task = "Supply chain mapping error"

    return state
