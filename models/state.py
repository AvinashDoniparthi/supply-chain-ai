from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from models.relationship import RelationshipResult
from models.verification import VerificationResult

class CompanyInfo(BaseModel):
    """Basic information about the target company."""
    name: str
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SupplierInfo(BaseModel):
    """Details about a supplier within the supply chain."""
    name: str
    location: str
    products: List[str] = Field(default_factory=list)
    tier: int = Field(default=1, description="Supplier tier level (1, 2, 3...)")
    criticality: str = Field(default="Medium", description="Business impact: Low, Medium, High")
    status: str = Field(default="Active")
    evidence: List[Dict[str, str]] = Field(default_factory=list, description="Evidence snippets from discovery")

class RiskAnalysis(BaseModel):
    """Risk assessment for a specific category or entity."""
    category: str = Field(description="e.g., Geopolitical, Financial, Environmental")
    threat_level: str = Field(description="Critical, High, Medium, Low")
    description: str
    potential_impact: str
    mitigation_recommendation: Optional[str] = None

class AgentState(BaseModel):
    """
    The global state object shared between all agents in the supply chain intelligence system.
    This tracks the progress and findings of the entire multi-agent workflow.
    """
    # Core target information
    target_company: Optional[str] = Field(default=None, description="The initial company name provided for research")
    company: Optional[CompanyInfo] = None
    
    # Supply chain mapping
    suppliers: List[SupplierInfo] = Field(default_factory=list)
    relationship_results: List[RelationshipResult] = Field(default_factory=list)
    
    # Intelligence layers
    verification_results: List[VerificationResult] = Field(default_factory=list)
    risk_assessments: List[RiskAnalysis] = Field(default_factory=list)
    
    # System metrics and outputs
    confidence_scores: Dict[str, float] = Field(
        default_factory=dict, 
        description="Confidence scores for different analysis stages (e.g., 'mapping', 'risk')"
    )
    final_reports: List[str] = Field(default_factory=list, description="Paths or content of generated reports")
    
    # Workflow control
    current_task: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
