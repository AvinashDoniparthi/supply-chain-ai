import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from models.state import AgentState
from models.verification import VerificationResult
from scraping.company_scraper import CompanyScraper
from utils.identity_resolution import resolver

logger = logging.getLogger(__name__)

class ProviderResult(BaseModel):
    """Result from an individual verification provider."""
    provider_name: str
    verified: bool
    confidence: float
    data: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str

class VerificationProvider(ABC):
    """Abstract base class for verification providers."""
    
    @abstractmethod
    def verify(self, name: str, evidence: List[Dict[str, str]]) -> ProviderResult:
        pass

class WikipediaVerificationProvider(VerificationProvider):
    """Verifies company existence via Wikipedia."""
    
    def __init__(self):
        self.provider_name = "Wikipedia"
        self.scraper = CompanyScraper()
        
    def verify(self, name: str, evidence: List[Dict[str, str]]) -> ProviderResult:
        try:
            # Re-use scraper logic to find a Wikipedia page
            data = self.scraper.search_company(name)
            
            # If description is the "empty" one, it failed
            if "Could not find public information" in data.get("description", ""):
                return ProviderResult(
                    provider_name="Wikipedia",
                    verified=False,
                    confidence=0.0,
                    reasoning="No Wikipedia page found for this entity."
                )
            
            # Confidence based on match quality (simple heuristic for now)
            # If the name is an exact or close match, high confidence
            confidence = 0.8 if data.get("industry") != "Not found" else 0.4
            
            return ProviderResult(
                provider_name="Wikipedia",
                verified=True,
                confidence=confidence,
                data=data,
                reasoning=f"Wikipedia page found. Industry: {data.get('industry')}. HQ: {data.get('headquarters')}."
            )
        except Exception as e:
            return ProviderResult(
                provider_name="Wikipedia",
                verified=False,
                confidence=0.0,
                reasoning=f"Wikipedia verification error: {str(e)}"
            )

class WebsiteVerificationProvider(VerificationProvider):
    """Verifies company via official website presence."""
    
    def __init__(self):
        self.provider_name = "Website"

    def verify(self, name: str, evidence: List[Dict[str, str]]) -> ProviderResult:
        # This provider will be called within the aggregator or can be passed data.
        # For now, it mainly checks discovery evidence.
        websites = []
        for e in evidence:
            snippet = e.get("snippet", "").lower()
            if "www." in snippet or "http" in snippet:
                websites.append(e.get("link"))
        
        if websites:
            return ProviderResult(
                provider_name="Website",
                verified=True,
                confidence=0.6,
                data={"website": websites[0]},
                reasoning=f"Potential official website or deep link found in discovery evidence: {websites[0]}"
            )
        
        return ProviderResult(
            provider_name="Website",
            verified=False,
            confidence=0.0,
            reasoning="No official website found in initial discovery evidence."
        )

class VerificationAggregator:
    """Aggregates results from multiple providers into a final VerificationResult."""
    
    def __init__(self, providers: List[VerificationProvider]):
        self.providers = providers
        
    def aggregate(self, name: str, rel_type: str, evidence: List[Dict[str, str]]) -> VerificationResult:
        provider_results = {}
        for provider in self.providers:
            provider_results[provider.provider_name] = provider.verify(name, evidence)
            
        # Cross-provider data sharing: If Wikipedia found a website, let's boost Website provider
        wiki_res = provider_results.get("Wikipedia")
        web_res = provider_results.get("Website")
        
        if wiki_res and wiki_res.verified and wiki_res.data.get("website"):
            if not web_res.verified:
                web_res.verified = True
                web_res.confidence = 0.8 # Higher confidence if confirmed by Wikipedia
                web_res.data["website"] = wiki_res.data.get("website")
                web_res.reasoning = f"Website confirmed via Wikipedia: {web_res.data['website']}"

        # Scoring Model: Weighted Average
        weights = {"Wikipedia": 0.6, "Website": 0.4}
        
        total_confidence = 0.0
        is_verified = False
        final_website = None
        final_hq = "Unknown"
        reasoning_steps = []
        sources = [e.get("link", "Unknown Source") for e in evidence]
        
        for p_name, res in provider_results.items():
            weight = weights.get(p_name, 0.1)
            total_confidence += res.confidence * weight
            
            if res.verified:
                is_verified = True
                reasoning_steps.append(f"[{res.provider_name}]: {res.reasoning}")
                
                if res.provider_name == "Wikipedia":
                    final_hq = res.data.get("headquarters", final_hq)
                    if not final_website:
                        final_website = res.data.get("website")
                if res.provider_name == "Website" and not final_website:
                    final_website = res.data.get("website")
            else:
                reasoning_steps.append(f"[{res.provider_name}]: Failed - {res.reasoning}")

        # Final verified status threshold
        final_verified = is_verified and total_confidence > 0.4
        
        return VerificationResult(
            supplier_name=name,
            relationship_type=rel_type,
            verified=final_verified,
            confidence_score=min(1.0, total_confidence),
            website=final_website,
            headquarters=final_hq,
            evidence_sources=sources,
            reasoning=" | ".join(reasoning_steps)
        )

def verification_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for verifying the existence and details of discovered entities.
    Uses a provider-based architecture for real-world validation.
    """
    print("\n--- VERIFICATION AGENT: Fact-Checking Relationships (Provider-Based) ---")
    print(f"Suppliers sent to verification: {len(state.suppliers)}")
    print(f"[PIPELINE COUNT] Before verification_agent: {len(state.suppliers)} suppliers")
    
    # Initialize providers
    providers = [
        WikipediaVerificationProvider(),
        WebsiteVerificationProvider()
    ]
    aggregator = VerificationAggregator(providers)
    
    # Map relationship results by candidate company name for easy lookup
    # After deduplication, candidate_company should match supplier.name (canonical)
    rel_map = {r.candidate_company: r for r in state.relationship_results}
    
    verified_results = []
    TO_VERIFY = ["supplier", "partner", "subsidiary"]
    
    for supplier in state.suppliers:
        # Use canonical name as the primary identifier
        canonical_name = supplier.canonical_name or supplier.name
        
        rel = rel_map.get(canonical_name)
        
        if not rel or rel.relationship_type not in TO_VERIFY:
            logger.info(f"Skipping verification for {canonical_name}")
            continue
            
        # Aggregated verification using canonical name
        print(f"Verifying: {canonical_name}")
        result = aggregator.aggregate(canonical_name, rel.relationship_type, supplier.evidence)
        
        verified_results.append(result)
        
        # Update supplier location if verified
        if result.verified and result.headquarters and result.headquarters != "Unknown":
            supplier.location = result.headquarters
            
        print(f"Supplier: {canonical_name}")
        print(f"Verified: {result.verified}")
        print(f"Confidence: {result.confidence_score:.2f}")
        print(f"HQ: {result.headquarters}")
        print("-" * 20)

    state.verification_results.extend(verified_results)
    
    if verified_results:
        avg_conf = sum(r.confidence_score for r in verified_results) / len(verified_results)
        state.confidence_scores["verification"] = round(avg_conf, 2)
    
    state.current_task = f"Verification completed for {len(verified_results)} entities using multi-provider architecture."
    print(f"[PIPELINE COUNT] After verification_agent: {len(state.suppliers)} suppliers\")\n    \n    state.history.append({
        "agent": "verification_agent",
        "action": "provider_based_verification",
        "verified_count": len([r for r in verified_results if r.verified]),
        "status": "success"
    })
    
    return state
