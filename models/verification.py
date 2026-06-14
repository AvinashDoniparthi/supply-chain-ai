from pydantic import BaseModel, Field
from typing import List, Optional

class VerificationResult(BaseModel):
    """Enhanced results of data verification for a company."""
    supplier_name: str
    relationship_type: str
    verified: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    website: Optional[str] = None
    headquarters: Optional[str] = None
    evidence_sources: List[str] = Field(default_factory=list)
    reasoning: str
