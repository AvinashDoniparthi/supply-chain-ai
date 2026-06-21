import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from models.state import AgentState
from models.relationship import RelationshipResult

from chains.relationship_chain import get_relationship_chain, RelationshipClassification
from langchain_core.output_parsers import PydanticOutputParser
from providers.llm_provider import print_llm_config_once, resolve_provider
from scraping.supplier_discovery import (
    analyze_supplier_evidence,
    candidate_competes_with_target,
    is_product_or_brand_name,
)
from utils.output import OutputMode, agent_event, debug_log, emit, progress
from utils.runtime_controls import (
    can_consume_llm_call,
    emit_skip_once,
    finish_stage,
    start_stage,
    stop_if_timed_out,
)

logger = logging.getLogger(__name__)

MIN_CLASSIFICATION_CONFIDENCE = 0.65
MIN_SUPPLIER_EVIDENCE_SCORE = 5

class RelationshipClassifier(ABC):
    """Abstract base class for relationship classification."""

    @abstractmethod
    def classify(
        self, target_company: str, candidate_entity: str, evidence: str
    ) -> RelationshipResult:
        pass


class LLMRelationshipClassifier(RelationshipClassifier):
    """LangChain implementation of the relationship classifier."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.config = resolve_provider(provider=provider, model=model)
        self.provider = self.config.provider
        self.model = self.config.model
        logger.debug(
            "[RELATIONSHIP INIT] provider=%s model=%s api_key_source=%s",
            self.provider,
            self.model,
            self.config.key_source,
        )

        try:
            self.chain = get_relationship_chain(
                provider=self.provider, model=self.model
            )
            self.parser = PydanticOutputParser(
                pydantic_object=RelationshipClassification
            )
            logger.debug(
                "[RELATIONSHIP INIT] Chain initialization succeeded provider=%s model=%s",
                self.provider,
                self.model,
            )
        except Exception as e:
            logger.exception(
                "[RELATIONSHIP INIT] Chain initialization failed provider=%s model=%s",
                self.provider,
                self.model,
            )
            raise RuntimeError("Failed to initialize relationship chain") from e

    def classify(
        self, target_company: str, candidate_entity: str, evidence: str
    ) -> RelationshipResult:
        valid_labels = [
            "supplier",
            "upstream_supplier",
            "customer",
            "partner",
            "competitor",
            "unrelated",
            "product_or_brand",
        ]

        if not self.chain:
            raise RuntimeError("Relationship chain is not initialized")

        try:
            # Execute chain with required inputs
            result: RelationshipClassification = self.chain.invoke(
                {
                    "target_company": target_company,
                    "candidate_entity": candidate_entity,
                    "evidence": evidence,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )

            relationship = result.relationship.lower()
            confidence = float(result.confidence)
            reasoning = result.reasoning

            if relationship not in valid_labels:
                raise RuntimeError(
                    f"Invalid relationship label returned by LLM: {result.relationship}"
                )

        except RuntimeError as e:
            if "Invalid relationship label" in str(e):
                raise
            logger.exception(
                "[RELATIONSHIP INVOKE] Chain invocation failed target=%s candidate=%s",
                target_company,
                candidate_entity,
            )
            raise RuntimeError(
                f"Relationship classification failed for {candidate_entity}"
            ) from e
        except Exception as e:
            logger.exception(
                "[RELATIONSHIP INVOKE] Chain invocation failed target=%s candidate=%s",
                target_company,
                candidate_entity,
            )
            raise RuntimeError(
                f"Relationship classification failed for {candidate_entity}"
            ) from e

        return RelationshipResult(
            target_company=target_company,
            candidate_company=candidate_entity,
            relationship_type=relationship,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_text=evidence[:500],
        )


class HeuristicRelationshipClassifier(RelationshipClassifier):
    """Deterministic fallback classifier based on explicit relationship evidence."""

    def classify(
        self, target_company: str, candidate_entity: str, evidence: str
    ) -> RelationshipResult:
        text = evidence.lower()
        analysis = analyze_supplier_evidence([{"snippet": evidence}])

        relationship = "unrelated"
        confidence = 0.35
        reasoning = "Evidence does not establish a supplier relationship."

        candidate = candidate_entity.lower()
        target = target_company.lower()

        if is_product_or_brand_name(candidate_entity):
            relationship = "product_or_brand"
            confidence = 0.9
            reasoning = "Candidate appears to be a product or brand, not a supplier company."
        elif (
            f"{candidate} is a subsidiary" in text
            or f"{candidate} is owned by" in text
            or f"{candidate} was acquired by {target}" in text
        ):
            relationship = "unrelated"
            confidence = 0.82
            reasoning = "Evidence indicates ownership or subsidiary status, not a supplier relationship."
        elif (
            f"{target} supplies" in text
            or f"{target} provides" in text
            or f"{candidate} is a customer" in text
            or f"{candidate} is a client" in text
        ):
            relationship = "customer"
            confidence = 0.78
            reasoning = "Evidence indicates the target sells to the candidate."
        elif (
            candidate_competes_with_target(target_company, candidate_entity)
            or any(term in text for term in ["competitor", "rival", "competes with"])
        ) and analysis["score"] < MIN_SUPPLIER_EVIDENCE_SCORE:
            relationship = "competitor"
            confidence = 0.75
            reasoning = "Evidence indicates a competitor relationship without supplier support."
        elif analysis["score"] >= MIN_SUPPLIER_EVIDENCE_SCORE:
            relationship = "supplier"
            confidence = min(
                0.95,
                0.62
                + analysis["score"] * 0.035
                + analysis["strong_hits"] * 0.03
                + analysis["supporting_snippets"] * 0.02,
            )
            reasoning = (
                "Evidence contains direct supplier, manufacturing, foundry, "
                "component, or assembly language."
            )
        elif analysis["medium_hits"] > 0:
            relationship = "partner"
            confidence = 0.58
            reasoning = "Evidence indicates partnership language but not supply direction."

        return RelationshipResult(
            target_company=target_company,
            candidate_company=candidate_entity,
            relationship_type=relationship,
            confidence_score=round(confidence, 2),
            reasoning=reasoning,
            evidence_text=evidence[:500],
        )


def _enforce_relationship_thresholds(result: RelationshipResult) -> RelationshipResult:
    analysis = analyze_supplier_evidence([{"snippet": result.evidence_text}])
    rel_type = result.relationship_type.lower()
    confidence = result.confidence_score
    supplier_labels = {"supplier", "upstream_supplier"}

    if rel_type in supplier_labels and analysis["score"] < MIN_SUPPLIER_EVIDENCE_SCORE:
        return RelationshipResult(
            target_company=result.target_company,
            candidate_company=result.candidate_company,
            relationship_type="unrelated",
            confidence_score=min(confidence, 0.4),
            reasoning=(
                f"Supplier classification downgraded: evidence score {analysis['score']} "
                f"is below required threshold {MIN_SUPPLIER_EVIDENCE_SCORE}. {result.reasoning}"
            ),
            evidence_text=result.evidence_text,
        )

    if rel_type != "unrelated" and confidence < MIN_CLASSIFICATION_CONFIDENCE:
        return RelationshipResult(
            target_company=result.target_company,
            candidate_company=result.candidate_company,
            relationship_type="unrelated",
            confidence_score=confidence,
            reasoning=(
                f"Classification downgraded below minimum confidence "
                f"{MIN_CLASSIFICATION_CONFIDENCE:.2f}. {result.reasoning}"
            ),
            evidence_text=result.evidence_text,
        )

    return result


classifier: Optional[LLMRelationshipClassifier] = None


def get_classifier() -> LLMRelationshipClassifier:
    global classifier
    if classifier is None:
        classifier = LLMRelationshipClassifier()
    return classifier


def relationship_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for classifying the relationship between the target company
    and discovered entities based on evidence text using an LLM.
    """
    target_company = state.company.name if state.company else state.target_company

    start_stage(state, "relationship_classification")
    progress(3, 6, "Classifying Relationships")
    agent_event(f"Relationship agent started: {len(state.suppliers)} entities")
    debug_log(
        logger,
        "[PIPELINE COUNT] Before relationship_agent: %s suppliers",
        len(state.suppliers),
    )

    if not target_company:
        state.errors.append(
            "Relationship Agent: No target company name provided in state."
        )
        finish_stage(state, "relationship_classification")
        return state

    fast_mode = state.skip_risk and state.max_depth <= 1
    if fast_mode:
        emit_skip_once(
            state,
            "relationship_llm",
            "Relationship LLM skipped in fast mode.",
        )
        active_classifier = HeuristicRelationshipClassifier()
    else:
        try:
            active_classifier: RelationshipClassifier = get_classifier()
            if isinstance(active_classifier, LLMRelationshipClassifier):
                print_llm_config_once(active_classifier.config)
        except ValueError as exc:
            debug_log(
                logger,
                "LLM classifier unavailable; using deterministic relationship classifier: %s",
                exc,
            )
            active_classifier = HeuristicRelationshipClassifier()

    for supplier in state.suppliers:
        if stop_if_timed_out(state, "relationship_classification"):
            break

        candidate_name = supplier.name
        relationship_source = supplier.parent_company or target_company
        canonical_name = supplier.canonical_name or candidate_name
        evidence_snippets = supplier.evidence

        # Aggregate all evidence text for this candidate
        full_evidence_text = " ".join([e.get("snippet", "") for e in evidence_snippets])

        # Perform semantic classification
        evidence_payload = (
            f"Supplier name: {candidate_name}\n"
            f"Parent company: {relationship_source}\n"
            f"Canonical company: {canonical_name}\n"
            f"Evidence snippets:\n{full_evidence_text}"
        )
        classification_evidence = (
            evidence_payload
            if isinstance(active_classifier, LLMRelationshipClassifier)
            else full_evidence_text
        )

        try:
            if isinstance(active_classifier, LLMRelationshipClassifier):
                if can_consume_llm_call(
                    state,
                    "relationship_classification",
                    f"relationship classification for {candidate_name}",
                ):
                    result = active_classifier.classify(
                        target_company=relationship_source,
                        candidate_entity=candidate_name,
                        evidence=classification_evidence,
                    )
                else:
                    result = HeuristicRelationshipClassifier().classify(
                        target_company=relationship_source,
                        candidate_entity=candidate_name,
                        evidence=full_evidence_text,
                    )
            else:
                result = active_classifier.classify(
                    target_company=relationship_source,
                    candidate_entity=candidate_name,
                    evidence=classification_evidence,
                )
        except Exception as exc:
            debug_log(
                logger,
                "Relationship classifier failed for %s; using heuristic fallback: %s",
                candidate_name,
                exc,
            )
            result = HeuristicRelationshipClassifier().classify(
                target_company=relationship_source,
                candidate_entity=candidate_name,
                evidence=full_evidence_text,
            )

        result = result.model_copy(update={"evidence_text": full_evidence_text[:500]})
        result = _enforce_relationship_thresholds(result)
        if result.relationship_type == "supplier" and supplier.tier > 1:
            result = result.model_copy(update={"relationship_type": "upstream_supplier"})
        elif result.relationship_type == "upstream_supplier" and supplier.tier <= 1:
            result = result.model_copy(update={"relationship_type": "supplier"})

        state.relationship_results.append(result)
        evidence_analysis = analyze_supplier_evidence([{"snippet": result.evidence_text}])

        debug_log(
            logger,
            "Company: %s | Relationship: %s | Confidence: %.2f | Evidence Score: %s | Reasoning: %s",
            candidate_name,
            result.relationship_type,
            result.confidence_score,
            evidence_analysis["score"],
            result.reasoning,
        )

    state.current_task = f"Semantic relationship classification completed for {len(state.suppliers)} entities."
    debug_log(
        logger,
        "[PIPELINE COUNT] After relationship_agent: %s suppliers",
        len(state.suppliers),
    )
    agent_event(f"Relationship agent completed: {len(state.relationship_results)} classified")
    finish_stage(state, "relationship_classification")

    # Add to history
    state.history.append(
        {
            "agent": "relationship_agent",
            "action": "semantic_relationship_classification",
            "target": target_company,
            "results_count": len(state.relationship_results),
            "classifications": [
                {
                    "candidate": result.candidate_company,
                    "relationship": result.relationship_type,
                    "confidence": result.confidence_score,
                    "evidence": result.evidence_text[:250],
                    "reasoning": result.reasoning,
                }
                for result in state.relationship_results
            ],
            "status": "success",
        }
    )

    return state
