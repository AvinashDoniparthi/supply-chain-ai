import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from models.state import AgentState
from models.verification import VerificationResult
from retrieval.rag_enrichment import enrich_supplier_evidence_with_rag
from scraping.company_scraper import CompanyScraper
from scraping.supplier_discovery import analyze_supplier_evidence, is_known_organization
from utils.identity_resolution import resolver
from utils.output import OutputMode, agent_event, debug_log, emit, progress
from utils.runtime_controls import finish_stage, start_stage, stop_if_timed_out

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
    
    def __init__(self, runtime_state: Optional[AgentState] = None):
        self.provider_name = "Wikipedia"
        self.runtime_state = runtime_state
        self.scraper = CompanyScraper(runtime_state=runtime_state, stage_key="verification")
        
    def verify(self, name: str, evidence: List[Dict[str, str]]) -> ProviderResult:
        try:
            data = None
            matched_candidate = None
            for candidate in resolver.wikipedia_search_candidates(name):
                # Re-use scraper logic to find a Wikipedia page.
                candidate_data = self.scraper.search_company(candidate)
                if "Could not find public information" not in candidate_data.get(
                    "description", ""
                ):
                    data = candidate_data
                    matched_candidate = candidate
                    break
            
            # If description is the "empty" one, it failed
            if not data:
                return ProviderResult(
                    provider_name="Wikipedia",
                    verified=False,
                    confidence=0.0,
                    reasoning="No Wikipedia page found for canonical name or known aliases."
                )
            
            # Confidence based on match quality (simple heuristic for now)
            # If the name is an exact or close match, high confidence
            confidence = 0.8 if data.get("industry") != "Not found" else 0.4
            
            return ProviderResult(
                provider_name="Wikipedia",
                verified=True,
                confidence=confidence,
                data=data,
                reasoning=(
                    f"Wikipedia page found using '{matched_candidate}'. "
                    f"Industry: {data.get('industry')}. HQ: {data.get('headquarters')}."
                )
            )
        except Exception as e:
            return ProviderResult(
                provider_name="Wikipedia",
                verified=False,
                confidence=0.0,
                reasoning=f"Wikipedia verification error: {str(e)}"
            )

class CuratedCompanyVerificationProvider(VerificationProvider):
    """Fast existence verification for known benchmark and major supplier entities."""

    def __init__(self):
        self.provider_name = "CuratedKnowledgeBase"

    def verify(self, name: str, evidence: List[Dict[str, str]]) -> ProviderResult:
        canonical_name = resolver.resolve(name)
        if (
            resolver.is_known_entity(name)
            or is_known_organization(name)
            or is_known_organization(canonical_name)
        ):
            return ProviderResult(
                provider_name=self.provider_name,
                verified=True,
                confidence=0.92,
                data={
                    "canonical_name": canonical_name,
                    "aliases": resolver.aliases_for(canonical_name),
                },
                reasoning="Recognized in curated supply-chain knowledge base.",
            )

        return ProviderResult(
            provider_name=self.provider_name,
            verified=False,
            confidence=0.0,
            reasoning="Entity not present in curated supply-chain knowledge base.",
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
    
    def __init__(
        self,
        providers: List[VerificationProvider],
        runtime_state: Optional[AgentState] = None,
    ):
        self.providers = providers
        self.runtime_state = runtime_state
        
    def aggregate(
        self,
        name: str,
        rel_type: str,
        evidence: List[Dict[str, str]],
        relationship_confidence: float,
    ) -> VerificationResult:
        canonical_name = resolver.resolve(name)
        provider_results = {}
        for provider in self.providers:
            if self.runtime_state and stop_if_timed_out(
                self.runtime_state, "verification"
            ):
                break
            if (
                provider.provider_name == "Wikipedia"
                and provider_results.get("CuratedKnowledgeBase")
                and provider_results["CuratedKnowledgeBase"].verified
                and provider_results["CuratedKnowledgeBase"].confidence >= 0.85
            ):
                provider_results[provider.provider_name] = ProviderResult(
                    provider_name=provider.provider_name,
                    verified=True,
                    confidence=0.85,
                    data={},
                    reasoning="Skipped network lookup because curated existence verification is strong.",
                )
                continue
            provider_results[provider.provider_name] = provider.verify(canonical_name, evidence)
            
        # Cross-provider data sharing: If Wikipedia found a website, let's boost Website provider
        wiki_res = provider_results.get("Wikipedia")
        web_res = provider_results.get("Website")
        
        if wiki_res and wiki_res.verified and wiki_res.data.get("website"):
            if web_res and not web_res.verified:
                web_res.verified = True
                web_res.confidence = 0.8 # Higher confidence if confirmed by Wikipedia
                web_res.data["website"] = wiki_res.data.get("website")
                web_res.reasoning = f"Website confirmed via Wikipedia: {web_res.data['website']}"

        evidence_quality = self._calculate_evidence_quality(evidence)
        source_quality = self._calculate_source_quality(evidence)
        
        company_confidence = 0.0
        company_exists = False
        final_website = None
        final_hq = "Unknown"
        reasoning_steps = []
        sources = [e.get("link", "Unknown Source") for e in evidence]
        
        for p_name, res in provider_results.items():
            if res.verified:
                company_exists = True
                company_confidence = max(company_confidence, res.confidence)
                reasoning_steps.append(f"[{res.provider_name}]: {res.reasoning}")
                
                if res.provider_name == "Wikipedia":
                    final_hq = res.data.get("headquarters", final_hq)
                    if not final_website:
                        final_website = res.data.get("website")
                if res.provider_name == "Website" and not final_website:
                    final_website = res.data.get("website")
            else:
                reasoning_steps.append(f"[{res.provider_name}]: Failed - {res.reasoning}")

        relationship_verified = (
            rel_type in {"supplier", "upstream_supplier"}
            and relationship_confidence >= 0.65
            and evidence_quality >= 0.5
        )

        if (
            not company_exists
            and relationship_verified
            and resolver.is_known_entity(canonical_name)
        ):
            company_exists = True
            company_confidence = max(company_confidence, 0.86)
            reasoning_steps.append(
                "[CuratedKnowledgeBase]: Canonical resolver recognizes this entity."
            )

        relationship_component = (
            relationship_confidence if relationship_verified else min(relationship_confidence, 0.35)
        )
        total_confidence = (
            company_confidence * 0.25
            + relationship_component * 0.35
            + evidence_quality * 0.25
            + source_quality * 0.15
        )
        if not company_exists:
            total_confidence = min(total_confidence, 0.35)
        if not relationship_verified:
            total_confidence = min(total_confidence, 0.55)

        final_verified = (
            company_exists
            and relationship_verified
            and total_confidence >= 0.55
        )

        reasoning_steps.append(
            "[RelationshipVerification]: "
            f"company_exists={company_exists}; relationship_verified={relationship_verified}; "
            f"relationship_confidence={relationship_confidence:.2f}; "
            f"evidence_quality={evidence_quality:.2f}; source_quality={source_quality:.2f}."
        )
        
        return VerificationResult(
            supplier_name=canonical_name,
            relationship_type=rel_type,
            verified=final_verified,
            company_exists=company_exists,
            relationship_verified=relationship_verified,
            evidence_quality=evidence_quality,
            source_quality=source_quality,
            confidence_score=min(1.0, total_confidence),
            website=final_website,
            headquarters=final_hq,
            evidence_sources=sources,
            reasoning=" | ".join(reasoning_steps)
        )

    def _calculate_evidence_quality(self, evidence: List[Dict[str, str]]) -> float:
        if not evidence:
            return 0.0

        analysis = analyze_supplier_evidence(evidence)
        score_component = min(1.0, analysis["score"] / 10)
        support_component = min(1.0, analysis["supporting_snippets"] / 2)
        penalty = 0.15 if analysis["negative_hits"] else 0.0
        return round(max(0.0, score_component * 0.7 + support_component * 0.3 - penalty), 2)

    def _calculate_source_quality(self, evidence: List[Dict[str, str]]) -> float:
        links = [item.get("link", "") for item in evidence if item.get("link")]
        if not links:
            return 0.0

        scores = []
        for link in links:
            lower_link = link.lower()
            if lower_link.startswith("curated://"):
                scores.append(0.9)
            elif "wikipedia.org" in lower_link:
                scores.append(0.55)
            elif lower_link.startswith("http"):
                scores.append(0.7)
            else:
                scores.append(0.4)

        count_boost = min(0.1, max(0, len(set(links)) - 1) * 0.05)
        return round(min(1.0, sum(scores) / len(scores) + count_boost), 2)

def verification_agent(state: AgentState) -> AgentState:
    """
    Agent responsible for verifying the existence and details of discovered entities.
    Uses a provider-based architecture for real-world validation.
    """
    progress(4, 6, "Verifying Suppliers")
    start_stage(state, "verification")
    agent_event(f"Verification agent started: {len(state.suppliers)} suppliers")
    debug_log(
        logger,
        "[PIPELINE COUNT] Before verification_agent: %s suppliers",
        len(state.suppliers),
    )
    state = enrich_supplier_evidence_with_rag(state, "verification")
    
    # Initialize providers
    providers = [
        CuratedCompanyVerificationProvider(),
        WikipediaVerificationProvider(runtime_state=state),
        WebsiteVerificationProvider()
    ]
    aggregator = VerificationAggregator(providers, runtime_state=state)
    
    # Map relationship results by candidate company name for easy lookup
    # After deduplication, candidate_company should match supplier.name (canonical)
    rel_map = {}
    for relationship in state.relationship_results:
        rel_map[relationship.candidate_company] = relationship
        rel_map[resolver.resolve(relationship.candidate_company)] = relationship
    
    verified_results = []
    TO_VERIFY = ["supplier", "upstream_supplier"]
    
    for supplier in state.suppliers:
        if stop_if_timed_out(state, "verification"):
            break

        # Use canonical name as the primary identifier
        canonical_name = resolver.resolve(supplier.canonical_name or supplier.name)
        supplier.canonical_name = canonical_name
        
        rel = rel_map.get(canonical_name) or rel_map.get(supplier.name)
        
        if not rel:
            logger.info(f"Skipping verification for {canonical_name}: no relationship result")
            continue

        rel_type = rel.relationship_type.lower()
        if rel_type not in TO_VERIFY:
            logger.info(
                f"Skipping verification for {canonical_name}: relationship_type={rel.relationship_type}"
            )
            continue
            
        # Aggregated verification using canonical name
        debug_log(logger, "Verifying: %s", canonical_name)
        result = aggregator.aggregate(
            canonical_name,
            rel_type,
            supplier.evidence,
            rel.confidence_score,
        )
        
        verified_results.append(result)
        
        # Update supplier location if verified
        if result.verified and result.headquarters and result.headquarters != "Unknown":
            supplier.location = result.headquarters
            
        debug_log(
            logger,
            "Supplier: %s | Verified: %s | Confidence: %.2f | HQ: %s",
            canonical_name,
            result.verified,
            result.confidence_score,
            result.headquarters,
        )
        if result.verified:
            emit(
                f"Verified supplier: {canonical_name} ({result.confidence_score:.2f})",
                OutputMode.NORMAL,
            )

    state.verification_results.extend(verified_results)
    
    if verified_results:
        avg_conf = sum(r.confidence_score for r in verified_results) / len(verified_results)
        state.confidence_scores["verification"] = round(avg_conf, 2)
    
    state.current_task = f"Verification completed for {len(verified_results)} entities using multi-provider architecture."
    debug_log(
        logger,
        "[PIPELINE COUNT] After verification_agent: %s suppliers",
        len(state.suppliers),
    )
    agent_event(
        f"Verification agent completed: {len([r for r in verified_results if r.verified])} verified"
    )
    finish_stage(state, "verification")
    
    state.history.append({
        "agent": "verification_agent",
        "action": "provider_based_verification",
        "verified_count": len([r for r in verified_results if r.verified]),
        "status": "success"
    })
    
    return state
