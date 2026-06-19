import logging
import json
import os
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from models.state import AgentState
from models.relationship import RelationshipResult

from chains.relationship_chain import get_relationship_chain, RelationshipClassification
from langchain_core.output_parsers import PydanticOutputParser

logger = logging.getLogger(__name__)


class RelationshipClassifier(ABC):
    """Abstract base class for relationship classification."""

    @abstractmethod
    def classify(
        self, target_company: str, candidate_entity: str, evidence: str
    ) -> RelationshipResult:
        pass


class LLMRelationshipClassifier(RelationshipClassifier):
    """LangChain implementation of the relationship classifier."""

    def __init__(self, provider: str = "openai", model: str = "gpt-4o"):
        self.provider = provider
        self.model = model

        # Check for invalid API keys
        api_key = (
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or "mock-key"
        )
        if api_key in ["mock-openai-key", "mock-google-key", "mock-key", ""]:
            log_msg = (
                f"[LLM WARNING]\n"
                f"Invalid API key detected for {provider.upper()}.\n"
                f"Running in degraded mode: relationships will default to 'unknown'.\n"
                f"Set {provider.upper()}_API_KEY environment variable for real classification."
            )
            print(log_msg)
            logger.warning(log_msg)

        try:
            self.chain = get_relationship_chain(provider=provider, model=model)
            self.parser = PydanticOutputParser(
                pydantic_object=RelationshipClassification
            )
        except Exception as e:
            logger.error(f"Failed to initialize relationship chain: {e}")
            self.chain = None

    def classify(
        self, target_company: str, candidate_entity: str, evidence: str
    ) -> RelationshipResult:
        valid_labels = [
            "supplier",
            "customer",
            "partner",
            "competitor",
            "subsidiary",
            "unknown",
        ]

        # Handle chain not initialized
        if not self.chain:
            log_msg = (
                f"[RELATIONSHIP FALLBACK]\n"
                f"Supplier: {candidate_entity}\n"
                f"Reason: LangChain chain not initialized\n"
                f"Relationship: unknown\n"
                f"Confidence: 0.0"
            )
            print(log_msg)
            logger.warning(log_msg)
            return RelationshipResult(
                target_company=target_company,
                candidate_company=candidate_entity,
                relationship_type="unknown",
                confidence_score=0.0,
                reasoning="LangChain chain not initialized (fallback mode).",
                evidence_text=evidence[:500],
            )

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
                logger.warning(
                    f"Invalid label '{relationship}' returned by LLM. Falling back to 'unknown'."
                )
                relationship = "unknown"
                confidence = 0.0
                reasoning = f"Invalid label returned by LLM: {result.relationship} (fallback mode)"

        except Exception as e:
            log_msg = (
                f"[RELATIONSHIP FALLBACK]\n"
                f"Supplier: {candidate_entity}\n"
                f"Reason: {str(e)}\n"
                f"Relationship: unknown\n"
                f"Confidence: 0.0"
            )
            print(log_msg)
            logger.error(log_msg)
            relationship = "unknown"
            confidence = 0.0
            reasoning = f"Classification error (fallback mode): {str(e)}"

        return RelationshipResult(
            target_company=target_company,
            candidate_company=candidate_entity,
            relationship_type=relationship,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_text=evidence[:500],
        )


# Instantiate the default classifier
# In a real app, this might be injected or configured via state/env
classifier = LLMRelationshipClassifier()


def relationship_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for classifying the relationship between the target company
    and discovered entities based on evidence text using an LLM.
    """
    target_company = state.company.name if state.company else state.target_company

    print(f"\n--- RELATIONSHIP AGENT: Semantic Classification for {target_company} ---")
    print(f"Entities to classify: {len(state.suppliers)}")
    print(
        f"[PIPELINE COUNT] Before relationship_agent: {len(state.suppliers)} suppliers"
    )

    if not target_company:
        state.errors.append(
            "Relationship Agent: No target company name provided in state."
        )
        return state

    fallback_count = 0
    for supplier in state.suppliers:
        candidate_name = supplier.name
        evidence_snippets = supplier.evidence

        # Aggregate all evidence text for this candidate
        full_evidence_text = " ".join([e.get("snippet", "") for e in evidence_snippets])

        # Perform semantic classification
        result = classifier.classify(
            target_company=target_company,
            candidate_entity=candidate_name,
            evidence=full_evidence_text,
        )

        # Track fallback cases (confidence 0.0 = fallback mode)
        if result.confidence_score == 0.0:
            fallback_count += 1

        state.relationship_results.append(result)

        # Logging as requested
        print(f"Company: {candidate_name}")
        print(f"Relationship: {result.relationship_type}")
        print(f"Confidence: {result.confidence_score:.2f}")
        print(f"Reasoning: {result.reasoning}")
        print("-" * 20)

    if fallback_count > 0:
        print(
            f"\n[RELATIONSHIP FALLBACK] {fallback_count} suppliers classified in degraded mode"
        )

    state.current_task = f"Semantic relationship classification completed for {len(state.suppliers)} entities."
    print(
        f"[PIPELINE COUNT] After relationship_agent: {len(state.suppliers)} suppliers (fallback: {fallback_count})"
    )

    # Add to history
    state.history.append(
        {
            "agent": "relationship_agent",
            "action": "semantic_relationship_classification",
            "target": target_company,
            "results_count": len(state.relationship_results),
            "fallback_count": fallback_count,
            "status": "success",
        }
    )

    return state
