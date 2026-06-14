from pydantic import BaseModel, Field
from typing import Optional

class RelationshipResult(BaseModel):
    """Result of classifying the relationship between two companies."""
    target_company: str
    candidate_company: str
    relationship_type: str = Field(description="One of: supplier, customer, competitor, partner, subsidiary, unknown")
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_text: str
