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
    canonical_name: Optional[str] = None
    location: str
    products: List[str] = Field(default_factory=list)
    tier: int = Field(default=1, description="Supplier tier level (1, 2, 3...)")
    criticality: str = Field(
        default="Medium", description="Business impact: Low, Medium, High"
    )
    status: str = Field(default="Active")
    discovery_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    propagated_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Propagated confidence score based on tier hierarchy",
    )
    parent_company: Optional[str] = Field(
        default=None,
        description="The company this supplier directly sells to in the context of this branch",
    )
    relationship_path: List[str] = Field(
        default_factory=list,
        description="Full ancestry path from the target company down to this supplier",
    )
    evidence: List[Dict[str, str]] = Field(
        default_factory=list, description="Evidence snippets from discovery"
    )


class RiskAnalysis(BaseModel):
    """Risk assessment for a specific supplier or entity."""

    supplier_name: str
    risk_type: str = Field(
        description="e.g., Geopolitical, Operational, Financial, Environmental, Strategic"
    )
    severity: str = Field(description="Critical, High, Medium, Low")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str
    mitigation: Optional[str] = None

    # Keep old fields for backward compatibility if needed, but the agent will use the new ones.
    # Actually, better to just update them to the new names since this is a design phase.
    # The requirement specifies the output fields.


class SupplierConfidence(BaseModel):
    """Granular confidence scoring for a supplier relationship."""

    supplier_name: str
    discovery_confidence: float
    relationship_confidence: float
    verification_confidence: float
    risk_confidence: float
    final_confidence: float
    reasoning: str


class SupplierCriticality(BaseModel):
    """Assessment of supplier importance to the target company."""

    supplier_name: str
    criticality_score: float
    criticality_level: str
    reasoning: str


class SupplyChainHealth(BaseModel):
    """Overall health assessment of the supply chain."""

    overall_score: float
    status: str
    supplier_count: int
    critical_suppliers: int
    high_risk_suppliers: int
    summary: str


class ExecutiveReport(BaseModel):
    """Business-ready summary of the supply chain analysis."""

    company_name: str
    overall_health_score: float
    health_status: str
    executive_summary: str
    key_suppliers: List[str]
    major_risks: List[str]
    recommendations: List[str]


class HistoricalRun(BaseModel):
    """Snapshot of a single supply chain analysis run."""

    timestamp: str
    health_score: float
    health_status: str
    supplier_count: int
    risk_count: int
    suppliers: List[str]


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str


class SupplyChainGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class AgentState(BaseModel):
    """
    The global state object shared between all agents in the supply chain intelligence system.
    This tracks the progress and findings of the entire multi-agent workflow.
    """

    # Core target information
    target_company: Optional[str] = Field(
        default=None, description="The initial company name provided for research"
    )
    current_depth: int = Field(
        default=0, description="Current depth of the active discovery node"
    )
    max_depth: int = Field(
        default=2, description="Maximum depth for recursive supplier discovery"
    )
    max_candidates_per_company: int = Field(
        default=5,
        description="Maximum supplier candidates retained for each discovered company",
    )
    timeout_seconds: int = Field(
        default=180, description="Per-stage timeout in seconds"
    )
    max_articles_per_supplier: int = Field(
        default=10, description="Maximum news articles analyzed per supplier"
    )
    max_retries: int = Field(
        default=2, description="Maximum retries for bounded provider calls"
    )
    max_mapping_queue_size: int = Field(
        default=50, description="Maximum queued companies for tier expansion"
    )
    max_total_suppliers_processed: int = Field(
        default=50, description="Maximum queued companies processed during discovery"
    )
    max_llm_calls: int = Field(
        default=30, description="Maximum LLM calls for a single run"
    )
    max_web_queries: int = Field(
        default=40, description="Maximum web queries for a single run"
    )
    skip_risk: bool = Field(
        default=False, description="Skip all risk providers for faster runs"
    )
    skip_news: bool = Field(
        default=False, description="Skip live news and financial risk providers"
    )
    supplier_cache_enabled: bool = Field(
        default=True, description="Use cached supplier discovery results when available"
    )
    refresh_supplier_cache: bool = Field(
        default=False, description="Ignore existing supplier discovery cache and refresh it"
    )
    mapping_queue: List[str] = Field(
        default_factory=list,
        description="Queue of company names pending supply chain discovery",
    )
    seen_companies: List[str] = Field(
        default_factory=list,
        description="Canonical company names already discovered or enqueued",
    )
    company: Optional[CompanyInfo] = None

    # Supply chain mapping
    suppliers: List[SupplierInfo] = Field(default_factory=list)
    discovered_entities: List[SupplierInfo] = Field(
        default_factory=list,
        description="All entities found during discovery, before filtering",
    )
    relationship_results: List[RelationshipResult] = Field(default_factory=list)

    # Intelligence layers
    verification_results: List[VerificationResult] = Field(default_factory=list)
    risk_assessments: List[RiskAnalysis] = Field(default_factory=list)
    supplier_confidence_scores: List[SupplierConfidence] = Field(default_factory=list)
    supplier_criticality_scores: List[SupplierCriticality] = Field(default_factory=list)
    supply_chain_health: Optional[SupplyChainHealth] = None
    executive_report: Optional[ExecutiveReport] = None
    historical_runs: List[HistoricalRun] = Field(default_factory=list)
    supply_chain_graph: Optional[SupplyChainGraph] = None

    # System metrics and outputs
    confidence_scores: Dict[str, Any] = Field(
        default_factory=dict,
        description="Confidence scores for different analysis stages (e.g., 'mapping', 'risk')",
    )
    final_reports: List[str] = Field(
        default_factory=list, description="Paths or content of generated reports"
    )

    # Workflow control
    current_task: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    active_stage: Optional[str] = None
    stage_started_at: Dict[str, float] = Field(default_factory=dict)
    stage_durations: Dict[str, float] = Field(default_factory=dict)
    timed_out_stages: List[str] = Field(default_factory=list)
    limit_events: List[str] = Field(default_factory=list)
    skip_events: List[str] = Field(default_factory=list)
    runtime_counters: Dict[str, int] = Field(
        default_factory=lambda: {
            "supplier_companies_processed": 0,
            "llm_calls": 0,
            "web_queries": 0,
        }
    )
