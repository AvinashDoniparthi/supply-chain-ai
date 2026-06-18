import logging
import json
import os
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from models.state import AgentState
from models.relationship import RelationshipResult

logger = logging.getLogger(__name__)

class RelationshipClassifier(ABC):
    """Abstract base class for relationship classification."""
    @abstractmethod
    def classify(
        self,
        target_company: str,
        candidate_entity: str,
        evidence: str
    ) -> RelationshipResult:
        pass

class LLMRelationshipClassifier(RelationshipClassifier):
    """LLM implementation of the relationship classifier."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        try:
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")
            
            if not api_key:
                logger.warning("No API key found for RelationshipClassifier (OPENAI_API_KEY or GOOGLE_API_KEY).")
                self.client = None
                return

            self.client = OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            logger.error("openai package not installed. Please install it to use LLMRelationshipClassifier.")
            self.client = None

    def classify(
        self,
        target_company: str,
        candidate_entity: str,
        evidence: str
    ) -> RelationshipResult:
        valid_labels = ["supplier", "customer", "partner", "competitor", "subsidiary", "unknown"]
        
        if not self.client:
            return RelationshipResult(
                target_company=target_company,
                candidate_company=candidate_entity,
                relationship_type="unknown",
                confidence_score=0.1,
                reasoning="LLM client not initialized (check dependencies/API keys).",
                evidence_text=evidence[:500]
            )

        prompt = f"""
Analyze the relationship between the Target Company and the Candidate Entity based on the provided evidence snippet.

Target Company: {target_company}
Candidate Entity: {candidate_entity}

Evidence:
"{evidence}"

Classify the relationship into exactly one of these labels:
- supplier: Candidate supplies products or services to Target.
- customer: Target supplies products or services to Candidate.
- partner: Target and Candidate collaborate or have a joint venture.
- competitor: Target and Candidate compete in the same market.
- subsidiary: Candidate is owned by Target or is a division of Target.
- unknown: Relationship is unclear or not mentioned.

Return ONLY a JSON object with this schema:
{{
  "relationship": "label",
  "confidence": float,
  "reasoning": "string"
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a supply chain intelligence analyst."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            relationship = data.get("relationship", "unknown").lower()
            confidence = float(data.get("confidence", 0.1))
            reasoning = data.get("reasoning", "LLM provided classification.")
            
            if relationship not in valid_labels:
                logger.warning(f"Invalid label '{relationship}' returned by LLM. Falling back to 'unknown'.")
                relationship = "unknown"
                confidence = 0.1
                reasoning = f"Invalid label returned by LLM: {data.get('relationship')}"
                
        except Exception as e:
            logger.error(f"LLM Classification failed for {candidate_entity}: {e}")
            relationship = "unknown"
            confidence = 0.1
            reasoning = f"Classification error: {str(e)}"

        return RelationshipResult(
            target_company=target_company,
            candidate_company=candidate_entity,
            relationship_type=relationship,
            confidence_score=confidence,
            reasoning=reasoning,
            evidence_text=evidence[:500]
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

    if not target_company:
        state.errors.append("Relationship Agent: No target company name provided in state.")
        return state

    for supplier in state.suppliers:
        candidate_name = supplier.name
        evidence_snippets = supplier.evidence
        
        # Aggregate all evidence text for this candidate
        full_evidence_text = " ".join([e.get("snippet", "") for e in evidence_snippets])
        
        # Perform semantic classification
        result = classifier.classify(
            target_company=target_company,
            candidate_entity=candidate_name,
            evidence=full_evidence_text
        )
        
        state.relationship_results.append(result)
        
        # Logging as requested
        print(f"Company: {candidate_name}")
        print(f"Relationship: {result.relationship_type}")
        print(f"Confidence: {result.confidence_score:.2f}")
        print(f"Reasoning: {result.reasoning}")
        print("-" * 20)

    state.current_task = f"Semantic relationship classification completed for {len(state.suppliers)} entities."
    
    # Add to history
    state.history.append({
        "agent": "relationship_agent",
        "action": "semantic_relationship_classification",
        "target": target_company,
        "results_count": len(state.relationship_results),
        "status": "success"
    })

    return state
