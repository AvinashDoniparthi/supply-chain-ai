from pydantic import BaseModel, Field
from typing import List, Optional

class VerificationResult(BaseModel):
    """Enhanced results of data verification for a company."""
    supplier_name: str
    relationship_type: str
    verified: bool
    company_exists: bool = False
    relationship_verified: bool = False
    evidence_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    source_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    website: Optional[str] = None
    headquarters: Optional[str] = None
    evidence_sources: List[str] = Field(default_factory=list)
    reasoning: str
