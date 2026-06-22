import logging
import re
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union

from models.state import AgentState, RiskAnalysis, SupplierInfo
from utils.supply_chain_metrics import calculate_discovery_coverage
from utils.identity_resolution import resolver
from utils.output import OutputMode, agent_event, debug_log, emit, progress
from utils.runtime_controls import (
    can_consume_web_query,
    emit_skip_once,
    finish_stage,
    remaining_stage_timeout,
    start_stage,
    stop_if_timed_out,
)

"""
SCORING METHODOLOGY:
1. Severity Levels:
   - Critical: Immediate threat to business continuity.
   - High: Significant risk that requires mitigation.
   - Medium: Moderate risk that should be monitored.
   - Low: Minor risk with minimal immediate impact.

2. Confidence Scores:
   - 1.0: Fact-based risk.
   - 0.7 - 0.9: Highly probable risk.
   - 0.5 - 0.7: Speculative risk.

TESTING STRATEGY:
1. Unit Tests: Mock RiskProvider and AgentState to verify individual provider logic.
2. Integration Tests: Run RiskIntelligenceAgent with real and mock supplier data.
3. News Provider Validation: Use specific company names with known recent issues (e.g., 'Foxconn strike') to verify keyword detection.
4. Edge Cases: Test with empty supplier lists, non-verified suppliers, and search failures.
"""

logger = logging.getLogger(__name__)

MIN_RELEVANCE_SCORE = 10


def _identity_keys(name: Optional[str]) -> set[str]:
    if not name:
        return set()
    canonical = resolver.resolve(name)
    return {
        key.lower()
        for key in {name, canonical}
        if key
    }


def _retained_supplier_keys(state: AgentState) -> set[str]:
    keys = set()
    for supplier in state.suppliers:
        keys.update(_identity_keys(supplier.name))
        keys.update(_identity_keys(getattr(supplier, "canonical_name", None)))
    return keys


def _risk_is_for_retained_supplier(
    risk: RiskAnalysis, retained_supplier_keys: set[str]
) -> bool:
    return bool(_identity_keys(risk.supplier_name) & retained_supplier_keys)


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _supplier_names_for_relevance(supplier: Union[SupplierInfo, str]) -> Dict[str, Any]:
    if isinstance(supplier, SupplierInfo):
        supplier_name = supplier.name
        canonical_name = supplier.canonical_name or resolver.resolve(supplier.name)
    else:
        supplier_name = supplier
        canonical_name = resolver.resolve(supplier)

    aliases = {
        key
        for key, canonical in resolver.mapping.items()
        if canonical.lower() == canonical_name.lower()
    }
    aliases.discard(supplier_name)
    aliases.discard(canonical_name)

    return {
        "supplier_name": supplier_name,
        "canonical_name": canonical_name,
        "aliases": sorted(aliases),
    }


def score_article_relevance(
    supplier: Union[SupplierInfo, str], item: Dict[str, Any]
) -> Dict[str, Any]:
    names = _supplier_names_for_relevance(supplier)
    title = item.get("title", "") or ""
    snippet = item.get("snippet", "") or ""
    text = f"{title} {snippet}"
    signals = []
    score = 0

    supplier_name = str(names["supplier_name"])
    canonical_name = str(names["canonical_name"])
    aliases = names["aliases"]

    if _contains_phrase(text, supplier_name):
        score += 5
        signals.append("supplier name exact match:+5")
    if canonical_name != supplier_name and _contains_phrase(text, canonical_name):
        score += 5
        signals.append("canonical name exact match:+5")

    matched_aliases = [alias for alias in aliases if _contains_phrase(text, alias)]
    if matched_aliases:
        score += 3
        signals.append(f"known aliases {matched_aliases}:+3")

    relevance_terms = [supplier_name, canonical_name, *matched_aliases]
    if any(_contains_phrase(title, term) for term in relevance_terms):
        score += 5
        signals.append("mention in title:+5")
    if any(_contains_phrase(snippet, term) for term in relevance_terms):
        score += 3
        signals.append("mention in first paragraphs:+3")

    mention_count = 0
    counted_terms = {term for term in relevance_terms if term}
    for term in counted_terms:
        mention_count += len(
            re.findall(
                rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
                text,
                flags=re.IGNORECASE,
            )
        )
    if mention_count == 1:
        score += 1
        signals.append("mention only once:+1")

    accepted = score >= MIN_RELEVANCE_SCORE
    debug_log(
        logger,
        "[ARTICLE RELEVANCE] Supplier: %s | Article: %s | Relevance: %s | Signals: %s | %s",
        supplier_name,
        title,
        score,
        ", ".join(signals) or "none",
        "Accepted" if accepted else "Rejected",
    )
    return {
        "score": score,
        "signals": signals,
        "accepted": accepted,
        "supplier_name": supplier_name,
        "canonical_name": canonical_name,
        "aliases": aliases,
    }


def _matched_keywords(text: str, keywords: List[str]) -> List[str]:
    return [keyword for keyword in keywords if keyword in text]


def _matched_labor_disruption_keywords(text: str) -> List[str]:
    patterns = [
        ("workers strike", r"\bworkers?\s+(?:go on\s+|are on\s+|begin\s+|launch\s+|stage\s+|continue\s+|extend\s+|join\s+)?strike\b(?!\s+(?:deal|agreement))"),
        ("employee strike", r"\bemployees?\s+(?:go on\s+|are on\s+|begin\s+|launch\s+|stage\s+|continue\s+|extend\s+|join\s+)?strike\b(?!\s+(?:deal|agreement))"),
        ("union strike", r"\bunion\s+(?:calls?\s+|begins?\s+|launches?\s+|stages?\s+)?strike\b(?!\s+(?:deal|agreement))"),
        ("labor strike", r"\blabo[u]?r\s+strike\b(?!\s+(?:deal|agreement))"),
        ("walkout", r"\bwalkout\b|\bwalk\s*out\b"),
        ("labor stoppage", r"\blabo[u]?r\s+stoppage\b"),
        ("work stoppage", r"\bwork\s+stoppage\b"),
        ("industrial action", r"\bindustrial\s+action\b"),
    ]
    return [
        keyword
        for keyword, pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def _is_market_price_movement_article(text: str) -> bool:
    market_terms = [
        "etf",
        "stock",
        "shares",
        "share price",
        "stock price",
        "price target",
        "trading",
        "trades",
        "nasdaq",
        "nyse",
    ]
    movement_terms = [
        "drop",
        "drops",
        "dropped",
        "down",
        "fall",
        "falls",
        "fell",
        "slip",
        "slips",
        "slumped",
        "decline",
        "declines",
        "lower",
        "selloff",
        "sell-off",
        "tumbles",
    ]
    return any(_contains_phrase(text, term) for term in market_terms) and any(
        _contains_phrase(text, term) for term in movement_terms
    )


def _has_direct_supplier_financial_distress(text: str) -> bool:
    distress_terms = [
        "bankruptcy",
        "insolvency",
        "insolvent",
        "debt crisis",
        "credit downgrade",
        "downgraded credit",
        "major loss",
        "major losses",
        "severe losses",
        "operational distress",
        "liquidation",
        "defaulted",
        "debt default",
        "revenue collapse",
        "plant closure",
        "factory closure",
    ]
    return any(_contains_phrase(text, term) for term in distress_terms)


def _path_display_for_supplier(state: AgentState, supplier: SupplierInfo) -> str:
    target = state.company.name if state.company else state.target_company or ""
    path = supplier.relationship_path or [target, supplier.name]

    display_by_canonical = {}
    if target:
        display_by_canonical[resolver.resolve(target).lower()] = target
    for known_supplier in state.suppliers:
        canonical = known_supplier.canonical_name or resolver.resolve(known_supplier.name)
        display_by_canonical[canonical.lower()] = known_supplier.name

    display_path = []
    for item in path:
        canonical_item = resolver.resolve(item)
        display_path.append(display_by_canonical.get(canonical_item.lower(), item))

    if not display_path and target:
        display_path = [target, supplier.name]
    return " -> ".join(display_path)


def _supplier_region(location: str) -> Optional[str]:
    location_lower = (location or "").lower()
    if "taiwan" in location_lower:
        return "Taiwan"
    if "ukraine" in location_lower:
        return "Ukraine"
    if "south china sea" in location_lower:
        return "South China Sea"
    if "china" in location_lower:
        return "China"
    if "russia" in location_lower:
        return "Russia"
    if "middle east" in location_lower:
        return "Middle East"
    return None


def _news_scope(
    supplier: Union[SupplierInfo, str],
    relevance: Dict[str, Any],
    item: Dict[str, Any],
    keywords: List[str],
    target_company: Optional[str] = None,
) -> str:
    title = item.get("title", "") or ""
    snippet = item.get("snippet", "") or ""
    text = f"{title} {snippet}".lower()
    title_lower = title.lower()

    supplier_terms = [
        str(relevance.get("supplier_name", "")),
        str(relevance.get("canonical_name", "")),
        *[str(alias) for alias in relevance.get("aliases", [])],
    ]
    supplier_terms = [term for term in supplier_terms if term]

    supplier_in_title = any(_contains_phrase(title, term) for term in supplier_terms)
    keyword_in_title = any(keyword in title_lower for keyword in keywords)

    facility_terms = [
        "factory",
        "plant",
        "fab",
        "facility",
        "site",
        "production line",
    ]
    workforce_terms = ["worker", "workforce", "employee", "union", "labor"]
    region_terms = [
        "taiwan",
        "china",
        "ukraine",
        "russia",
        "middle east",
        "red sea",
        "south china sea",
    ]
    direct_terms = [
        "manufacturing",
        "production",
        "operations",
        "delivery",
        "deliveries",
        "shipment",
        "shipments",
        "orders",
        "output",
    ]
    industry_terms = [
        "semiconductor",
        "chip",
        "memory",
        "foundry",
        "electronics",
        "industry",
        "market",
        "brands",
        "chipmakers",
    ]

    target = target_company or ""
    if target and _contains_phrase(text, target) and any(
        term in text
        for term in ["disrupt", "disruption", "shortage", "delay", "production"]
    ):
        return "target_impact"

    if any(term in text for term in facility_terms):
        return "direct_facility"

    if any(term in text for term in workforce_terms):
        return "direct_supplier"

    if any(term in text for term in region_terms):
        return "regional"

    if supplier_in_title and keyword_in_title:
        return "direct_supplier"

    if supplier_in_title and any(term in text for term in direct_terms):
        return "direct_supplier"

    if any(term in text for term in industry_terms):
        return "general_industry"

    return "unscoped"


class RiskProvider(ABC):
    """Base class for risk intelligence providers."""

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:
        pass


class GeopoliticalRiskProvider(RiskProvider):
    """Assess risks based on supplier location and regional stability."""

    def name(self) -> str:
        return "Geopolitical"

    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:
        risks = []

        high_tension_zones = {
            "Taiwan": {
                "severity": "High",
                "summary": "Taiwan geopolitical exposure",
                "reason": "a high-tension geopolitical region",
            },
            "Ukraine": {
                "severity": "Critical",
                "summary": "active conflict-zone exposure",
                "reason": "an active conflict zone",
            },
            "South China Sea": {
                "severity": "Medium",
                "summary": "South China Sea shipping exposure",
                "reason": "a disputed maritime trade region",
            },
        }

        for supplier in state.suppliers:
            if stop_if_timed_out(state, "risk_analysis"):
                break
            debug_log(logger, "=== %s PROVIDER DEBUG ===", self.name())
            debug_log(logger, "Supplier: %s", supplier.name)
            
            supplier_risks = []
            location = getattr(supplier, "location", "") or ""

            region = _supplier_region(location)

            if region in high_tension_zones:
                zone_info = high_tension_zones[region]
                path = _path_display_for_supplier(state, supplier)

                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Geopolitical",
                        severity=zone_info["severity"],
                        confidence=0.9,
                        reasoning=(
                            f"{zone_info['summary']} through {supplier.name}. "
                            f"Affected path: {path}. "
                            f"Reason: {supplier.name} is located in {location}, {zone_info['reason']}."
                        ),
                        mitigation="Identify and qualify alternative suppliers in diverse geographic regions.",
                    )
                )

            elif region in {"China", "Russia", "Middle East"}:
                path = _path_display_for_supplier(state, supplier)
                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Geopolitical",
                        severity="Medium",
                        confidence=0.7,
                        reasoning=(
                            f"Geographic tension exposure through {supplier.name}. "
                            f"Affected path: {path}. "
                            f"Reason: {supplier.name} is located in {location}, creating trade or political exposure for this supply path."
                        ),
                        mitigation="Monitor trade policy changes and explore friend-shoring options.",
                    )
                )

            # Rule: Max 1 geopolitical risk per supplier
            if len(supplier_risks) > 1:
                # Sort by severity: Critical > High > Medium > Low
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = [supplier_risks[0]]

            for risk in supplier_risks:
                debug_log(
                    logger,
                    "RISK -> %s | %s | %s | %s",
                    risk.supplier_name,
                    risk.risk_type,
                    risk.severity,
                    risk.reasoning,
                )
                emit(f"Accepted risk: [{risk.severity}] {risk.reasoning}", OutputMode.NORMAL)
            
            debug_log(logger, "Risks Generated: %s", len(supplier_risks))
            risks.extend(supplier_risks)

        return risks


class VerificationRiskProvider(RiskProvider):
    """Deprecated: verification failures are data-quality warnings, not risks."""

    def name(self) -> str:
        return "Verification"

    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:
        debug_log(
            logger,
            "Verification risk provider skipped; verification failures are reported as data-quality warnings.",
        )
        return []


class NewsRiskProvider(RiskProvider):
    """Assess risks based on recent news and media reports using Google News RSS."""

    def name(self) -> str:
        return "News"

    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:
        risks = []
        from datetime import datetime, timedelta
        import email.utils

        # Map verification results for quick lookup
        verification_map = {v.supplier_name: v for v in state.verification_results}

        for supplier in state.suppliers:
            if stop_if_timed_out(state, "risk_analysis"):
                break
            debug_log(logger, "=== %s PROVIDER DEBUG ===", self.name())
            debug_log(logger, "Supplier: %s", supplier.name)
            
            # Only analyze verified suppliers
            verification = verification_map.get(supplier.name) or verification_map.get(
                getattr(supplier, "canonical_name", "")
            )

            if not verification or not verification.verified:
                debug_log(logger, "Skipping %s - Not verified", supplier.name)
                continue

            # 1. Fetch news
            news_items = self._fetch_news(supplier.name, state)
            
            # 2. Filter news from the last 90 days
            ninety_days_ago = datetime.now() - timedelta(days=90)
            recent_news = []
            for item in news_items:
                try:
                    pub_date = email.utils.parsedate_to_datetime(item["pub_date"])
                    if pub_date.tzinfo:
                        pub_date = pub_date.replace(tzinfo=None)
                    
                    if pub_date >= ninety_days_ago:
                        recent_news.append(item)
                except Exception as e:
                    continue

            detected_keywords = set()
            supplier_risks = []
            articles_triggering = 0
            
            for item in recent_news[: state.max_articles_per_supplier]:
                if stop_if_timed_out(state, "risk_analysis"):
                    break
                # Rule 1 & 2: one risk per article, highest severity
                risk, keywords = self._analyze_headline_with_keywords(
                    supplier,
                    item,
                    state.company.name if state.company else state.target_company,
                )
                if risk:
                    articles_triggering += 1
                    supplier_risks.append(risk)
                    detected_keywords.update(keywords)
                    
                    # Log triggered article
                    debug_log(logger, "headline: %s", item["title"])
                    debug_log(logger, "matched keyword: %s", ", ".join(keywords))
                    debug_log(logger, "generated severity: %s", risk.severity)

            # Rule 3: Limit to max 3 news risks per supplier (highest severity)
            if len(supplier_risks) > 3:
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = supplier_risks[:3]

            # Mandatory Investigation Logs
            debug_log(logger, "Articles Retrieved: %s", len(news_items))
            debug_log(logger, "Articles After Date Filter: %s", len(recent_news))
            debug_log(logger, "Articles Triggering Risk: %s", articles_triggering)
            debug_log(logger, "Risks Generated: %s", len(supplier_risks))

            for risk in supplier_risks:
                debug_log(
                    logger,
                    "RISK -> %s | %s | %s | %s",
                    risk.supplier_name,
                    risk.risk_type,
                    risk.severity,
                    risk.reasoning,
                )
                emit(f"Accepted risk: [{risk.severity}] {risk.reasoning}", OutputMode.NORMAL)

            risks.extend(supplier_risks)

        if not risks:
            debug_log(logger, "No recent risk-related news found")

        return risks

    def _fetch_news(
        self, supplier_name: str, state: Optional[AgentState] = None
    ) -> List[Dict[str, Any]]:
        """Fetch news using Google News RSS with multiple risk-focused queries."""
        import xml.etree.ElementTree as ET
        
        queries = [
            f"{supplier_name} supply chain",
            f"{supplier_name} disruption",
            f"{supplier_name} strike",
            f"{supplier_name} factory"
        ]
        
        all_items = []
        seen_titles = set()

        max_articles = int(getattr(state, "max_articles_per_supplier", 10) or 10)

        for query in queries:
            if state and stop_if_timed_out(state, "risk_analysis"):
                break
            if not can_consume_web_query(
                state, "risk_analysis", f"Google News RSS query for '{query}'"
            ):
                break
            try:
                url = "https://news.google.com/rss/search"
                params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=remaining_stage_timeout(state, "risk_analysis", 3.0),
                )
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
                    if len(all_items) >= max_articles:
                        break
                    title = item.find("title").text
                    if title not in seen_titles:
                        description = item.find("description").text or ""
                        pub_date = item.find("pubDate").text
                        
                        all_items.append({
                            "title": title,
                            "snippet": description,
                            "pub_date": pub_date
                        })
                        seen_titles.add(title)
                if len(all_items) >= max_articles:
                    break
            except Exception as e:
                logger.error(f"Failed to fetch news for query '{query}': {e}")
                
        return all_items

    def _analyze_headline_with_keywords(
        self,
        supplier: Union[SupplierInfo, str],
        item: Dict[str, Any],
        target_company: Optional[str] = None,
    ) -> tuple[Optional[RiskAnalysis], List[str]]:
        """Analyzes headline and returns (RiskAnalysis, matched_keywords)."""
        relevance = score_article_relevance(supplier, item)
        supplier_name = relevance["supplier_name"]
        if not relevance["accepted"]:
            return None, []

        title = (item.get("title", "") or "").lower()
        snippet = (item.get("snippet", "") or "").lower()
        text = f"{title} {snippet}"
        
        facility_terms = ["factory", "plant", "fab", "facility", "site", "production line"]
        region_terms = ["taiwan", "china", "ukraine", "russia", "middle east", "red sea", "south china sea"]
        industry_terms = ["semiconductor", "chip", "foundry", "electronics", "industry"]

        war_kws = _matched_keywords(text, ["war", "conflict", "invasion", "military attack", "escalation"])
        if war_kws:
            scope = _news_scope(supplier, relevance, item, war_kws, target_company)
            if any(term in text for term in facility_terms):
                severity = "Critical"
                confidence = 0.85
                reasoning = f"War risk may affect supplier facilities: {item.get('title', '')}."
            elif any(term in text for term in region_terms):
                severity = "High"
                confidence = 0.75
                reasoning = f"War risk may affect supplier region: {item.get('title', '')}."
            elif scope == "general_industry" or any(term in text for term in industry_terms):
                severity = "Medium"
                confidence = 0.65
                reasoning = f"Industry-level war risk mention involving {supplier_name}: {item.get('title', '')}."
            else:
                return None, war_kws
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity=severity,
                confidence=confidence,
                reasoning=reasoning,
                mitigation="Assess total exposure and identify immediate alternatives."
            ), war_kws

        critical_kws = _matched_keywords(text, ["shutdown", "sanction", "explosion", "natural disaster", "catastrophe"])
        if critical_kws:
            scope = _news_scope(supplier, relevance, item, critical_kws, target_company)
            if scope == "general_industry":
                severity = "Medium"
                confidence = 0.65
                reasoning = (
                    f"Industry-level risk mention involving {supplier_name}: "
                    f"{item.get('title', '')}."
                )
            elif scope == "regional":
                severity = "High"
                confidence = 0.72
                reasoning = (
                    f"Regional risk may affect {supplier_name}'s supply path: "
                    f"{item.get('title', '')}."
                )
            else:
                severity = "Critical"
                confidence = 0.8
                reasoning = (
                    f"Critical supplier-specific event detected for {supplier_name}: "
                    f"{item.get('title', '')}."
                )
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity=severity,
                confidence=confidence,
                reasoning=reasoning,
                mitigation="Assess total exposure and identify immediate alternatives."
            ), critical_kws

        strike_kws = _matched_labor_disruption_keywords(text)
        if strike_kws:
            workforce_terms = ["worker", "workforce", "employee", "union", "labor"]
            scope = _news_scope(supplier, relevance, item, strike_kws, target_company)
            severity = (
                "High"
                if scope in {"direct_facility", "direct_supplier", "target_impact"}
                or any(term in text for term in workforce_terms + facility_terms)
                else "Low"
            )
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity=severity,
                confidence=0.75 if severity == "High" else 0.55,
                reasoning=f"Supplier labor disruption signal for {supplier_name}: {item.get('title', '')}.",
                mitigation="Notify production teams and prepare buffer stock or secondary routes."
            ), strike_kws

        high_kws = _matched_keywords(text, ["export restriction", "severe disruption", "shortage", "disruption", "fire", "flood", "earthquake"])
        if high_kws:
            scope = _news_scope(supplier, relevance, item, high_kws, target_company)
            if scope == "general_industry":
                severity = "Medium"
                confidence = 0.6
                reasoning = (
                    f"General industry risk mention involving {supplier_name}: "
                    f"{item.get('title', '')}."
                )
            elif scope == "unscoped":
                severity = "Low"
                confidence = 0.55
                reasoning = (
                    f"Unconfirmed supplier risk mention involving {supplier_name}: "
                    f"{item.get('title', '')}."
                )
            else:
                severity = "High"
                confidence = 0.75
                reasoning = (
                    f"Significant supplier-path risk detected for {supplier_name}: "
                    f"{item.get('title', '')}. High probability of delivery delays."
                )
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity=severity,
                confidence=confidence,
                reasoning=reasoning,
                mitigation="Notify production teams and prepare buffer stock or secondary routes."
            ), high_kws

        medium_kws = _matched_keywords(text, ["investigation", "lawsuit", "fine", "litigation"])
        if medium_kws:
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="Medium",
                confidence=0.65,
                reasoning=f"Moderate supplier-specific operational/regulatory issue: {item.get('title', '')}.",
                mitigation="Conduct detailed risk review and monitor for further escalation."
            ), medium_kws

        low_kws = _matched_keywords(text, ["warning", "rumor", "protest", "dispute"])
        if low_kws:
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="Low",
                confidence=0.55,
                reasoning=f"Potential supplier-specific early warning signal: {item.get('title', '')}.",
                mitigation="Track news cycle for 7-14 days for resolution or escalation."
            ), low_kws

        return None, []

    def _analyze_headline(self, supplier_name: str, item: Dict[str, str]) -> Optional[RiskAnalysis]:
        """Legacy method for compatibility if needed, though replaced by _analyze_headline_with_keywords."""
        risk, _ = self._analyze_headline_with_keywords(supplier_name, item)
        return risk


class FinancialRiskProvider(RiskProvider):
    """Assess risks based on financial stability and media reports using Google News RSS."""

    def name(self) -> str:
        return "Financial"

    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:
        risks = []
        from datetime import datetime, timedelta
        import email.utils

        # Map verification results for quick lookup
        verification_map = {v.supplier_name: v for v in state.verification_results}

        for supplier in state.suppliers:
            if stop_if_timed_out(state, "risk_analysis"):
                break
            debug_log(logger, "=== %s PROVIDER DEBUG ===", self.name())
            debug_log(logger, "Supplier: %s", supplier.name)
            
            # Only analyze verified suppliers
            verification = verification_map.get(supplier.name) or verification_map.get(
                getattr(supplier, "canonical_name", "")
            )

            if not verification or not verification.verified:
                debug_log(logger, "Skipping %s - Not verified", supplier.name)
                continue

            # 1. Fetch news
            news_items = self._fetch_news(supplier.name, state)
            
            # 2. Filter news from the last 180 days
            one_hundred_eighty_days_ago = datetime.now() - timedelta(days=180)
            recent_news = []
            for item in news_items:
                try:
                    pub_date = email.utils.parsedate_to_datetime(item["pub_date"])
                    if pub_date.tzinfo:
                        pub_date = pub_date.replace(tzinfo=None)
                    
                    if pub_date >= one_hundred_eighty_days_ago:
                        recent_news.append(item)
                except Exception as e:
                    continue

            detected_keywords = set()
            supplier_risks = []
            articles_triggering = 0
            
            for item in recent_news[: state.max_articles_per_supplier]:
                if stop_if_timed_out(state, "risk_analysis"):
                    break
                risk, keywords = self._analyze_financial_headline(supplier, item)
                if risk:
                    articles_triggering += 1
                    supplier_risks.append(risk)
                    detected_keywords.update(keywords)
                    
                    # Log triggered article
                    debug_log(logger, "headline: %s", item["title"])
                    debug_log(logger, "matched keyword: %s", ", ".join(keywords))
                    debug_log(logger, "generated severity: %s", risk.severity)

            # Rule: Limit to max 3 financial risks per supplier (highest severity)
            if len(supplier_risks) > 3:
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = supplier_risks[:3]

            # Mandatory Investigation Logs
            debug_log(logger, "Articles Retrieved: %s", len(news_items))
            debug_log(logger, "Articles After Date Filter: %s", len(recent_news))
            debug_log(logger, "Articles Triggering Risk: %s", articles_triggering)
            debug_log(logger, "Risks Generated: %s", len(supplier_risks))

            for risk in supplier_risks:
                debug_log(
                    logger,
                    "RISK -> %s | %s | %s | %s",
                    risk.supplier_name,
                    risk.risk_type,
                    risk.severity,
                    risk.reasoning,
                )
                emit(f"Accepted risk: [{risk.severity}] {risk.reasoning}", OutputMode.NORMAL)

            risks.extend(supplier_risks)

        if not risks:
            debug_log(logger, "No recent financial risk signals found.")

        return risks

    def _fetch_news(
        self, supplier_name: str, state: Optional[AgentState] = None
    ) -> List[Dict[str, Any]]:
        """Fetch news using Google News RSS with multiple financial queries."""
        import xml.etree.ElementTree as ET
        
        queries = [
            f"{supplier_name} earnings",
            f"{supplier_name} revenue",
            f"{supplier_name} layoffs",
            f"{supplier_name} bankruptcy",
            f"{supplier_name} debt",
            f"{supplier_name} financial results"
        ]
        
        all_items = []
        seen_titles = set()

        max_articles = int(getattr(state, "max_articles_per_supplier", 10) or 10)

        for query in queries:
            if state and stop_if_timed_out(state, "risk_analysis"):
                break
            if not can_consume_web_query(
                state, "risk_analysis", f"Google News RSS query for '{query}'"
            ):
                break
            try:
                url = "https://news.google.com/rss/search"
                params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=remaining_stage_timeout(state, "risk_analysis", 3.0),
                )
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
                    if len(all_items) >= max_articles:
                        break
                    title = item.find("title").text
                    if title not in seen_titles:
                        description = item.find("description").text or ""
                        pub_date = item.find("pubDate").text
                        
                        all_items.append({
                            "title": title,
                            "snippet": description,
                            "pub_date": pub_date
                        })
                        seen_titles.add(title)
                if len(all_items) >= max_articles:
                    break
            except Exception as e:
                logger.error(f"Failed to fetch financial news for query '{query}': {e}")
                
        return all_items

    def _analyze_financial_headline(self, supplier: Union[SupplierInfo, str], item: Dict[str, Any]) -> tuple[Optional[RiskAnalysis], List[str]]:
        """Analyzes financial headline and returns (RiskAnalysis, matched_keywords)."""
        relevance = score_article_relevance(supplier, item)
        supplier_name = relevance["supplier_name"]
        if not relevance["accepted"]:
            return None, []

        title = (item.get("title", "") or "").lower()
        snippet = (item.get("snippet", "") or "").lower()
        text = f"{title} {snippet}"

        if _is_market_price_movement_article(text) and not _has_direct_supplier_financial_distress(text):
            return None, []
        
        self_terms = [
            "files for",
            "filed for",
            "seeks bankruptcy",
            "enters bankruptcy",
            "declares bankruptcy",
            "insolvent",
            "liquidation",
            "defaulted",
        ]
        customer_terms = ["customer", "client", "buyer", "major customer"]

        bankruptcy_kws = _matched_keywords(
            text, ["bankruptcy", "insolvency", "liquidation", "default"]
        )
        if bankruptcy_kws:
            if any(term in text for term in self_terms):
                severity = "Critical"
                confidence = 0.85
                reasoning = f"Supplier itself appears financially distressed: {item.get('title', '')}."
            elif any(term in text for term in customer_terms):
                severity = "High"
                confidence = 0.75
                reasoning = f"Major customer financial distress may affect supplier demand: {item.get('title', '')}."
            else:
                return None, bankruptcy_kws
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity=severity,
                confidence=confidence,
                reasoning=reasoning,
                mitigation="Evaluate immediate alternate suppliers and assess total exposure."
            ), bankruptcy_kws

        high_kws = _matched_keywords(text, ["debt crisis", "plant closure", "factory closure", "revenue collapse", "severe losses"])
        if high_kws:
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="High",
                confidence=0.8,
                reasoning=f"High supplier-specific financial risk detected: {item.get('title', '')}.",
                mitigation="Evaluate alternate suppliers and monitor financial disclosures."
            ), high_kws

        layoff_kws = _matched_keywords(text, ["layoff", "layoffs", "workforce reduction", "job cuts", "major layoffs"])
        if layoff_kws:
            if any(term in text for term in ["supplier", "company", "workforce", "employees", supplier_name.lower()]):
                return RiskAnalysis(
                    supplier_name=supplier_name,
                    risk_type="Financial",
                    severity="Medium",
                    confidence=0.7,
                    reasoning=f"Supplier layoffs detected: {item.get('title', '')}.",
                    mitigation="Monitor operational continuity and supplier financial disclosures."
                ), layoff_kws
            return None, layoff_kws

        medium_kws = _matched_keywords(text, ["earnings miss", "declining revenue", "profit warning", "cost cutting", "restructuring"])
        if medium_kws:
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="Medium",
                confidence=0.7,
                reasoning=f"Moderate supplier-specific financial signal: {item.get('title', '')}.",
                mitigation="Request financial health disclosure and monitor quarterly performance."
            ), medium_kws

        low_kws = _matched_keywords(text, ["slowdown", "weak demand", "reduced guidance"])
        if low_kws:
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="Low",
                confidence=0.6,
                reasoning=f"Minor supplier-specific financial warning: {item.get('title', '')}.",
                mitigation="Track performance for next 2 quarters for stabilization."
            ), low_kws

        return None, []


class RiskIntelligenceAgent:
    """Orchestrator for multiple risk providers."""

    def __init__(self):
        self.providers = [
            GeopoliticalRiskProvider(),
            NewsRiskProvider(),
            FinancialRiskProvider(),
        ]

    def run(self, state: AgentState) -> AgentState:

        progress(5, 6, "Assessing Risks")
        start_stage(state, "risk_analysis")
        agent_event(f"Risk agent started: {len(state.suppliers)} suppliers")
        debug_log(logger, "=== RISK INPUT TRACE ===")
        debug_log(logger, "Suppliers sent to risk analysis: %s", len(state.suppliers))

        if state.skip_risk:
            emit_skip_once(state, "risk_analysis", "Risk analysis skipped in fast mode.")
            emit_skip_once(state, "news_risk", "News risk skipped in fast mode.")
            state.confidence_scores["risk_analysis"] = 0.75
            state.current_task = "Risk assessment skipped"
            state.history.append(
                {
                    "agent": "risk_intelligence_agent",
                    "action": "skipped_risk_providers",
                    "status": "skipped",
                }
            )
            finish_stage(state, "risk_analysis")
            return state

        for supplier in state.suppliers:
            debug_log(
                logger,
                "Supplier: %s | Canonical: %s | Location: %s",
                supplier.name,
                getattr(supplier, "canonical_name", "N/A"),
                getattr(supplier, "location", "N/A"),
            )

        debug_log(logger, "Risk intelligence agent orchestrating risk assessments")

        all_risks = []
        retained_supplier_keys = _retained_supplier_keys(state)

        for provider in self.providers:
            if stop_if_timed_out(state, "risk_analysis"):
                break
            if state.skip_news and isinstance(
                provider, (NewsRiskProvider, FinancialRiskProvider)
            ):
                if isinstance(provider, NewsRiskProvider):
                    emit_skip_once(
                        state, "news_risk", "News risk skipped in fast mode."
                    )
                else:
                    emit_skip_once(
                        state,
                        "financial_news_risk",
                        "Financial news risk skipped in fast mode.",
                    )
                continue

            provider_risks = [
                risk
                for risk in provider.assess_risk(state)
                if _risk_is_for_retained_supplier(risk, retained_supplier_keys)
            ]
            
            # Deduplication within provider and total
            unique_provider_risks = []
            seen_keys = set()
            
            for risk in provider_risks:
                # Deduplication Requirement Unique Key
                risk_key = (
                    risk.supplier_name,
                    risk.risk_type,
                    risk.severity,
                    risk.reasoning
                )
                
                if risk_key not in seen_keys:
                    unique_provider_risks.append(risk)
                    seen_keys.add(risk_key)
                else:
                    debug_log(
                        logger,
                        "DUPLICATE RISK REMOVED: Supplier=%s RiskType=%s",
                        risk.supplier_name,
                        risk.risk_type,
                    )

            debug_log(logger, "TOTAL RISKS FROM %s: %s", provider.name(), len(unique_provider_risks))
            all_risks.extend(unique_provider_risks)

        debug_log(logger, "TOTAL RISKS GENERATED: %s", len(all_risks))
        agent_event(f"Risk agent completed: {len(all_risks)} accepted risks")

        state.risk_assessments.extend(all_risks)
        state.current_task = "Risk assessment completed"

        if all_risks:
            avg_conf = sum(r.confidence for r in all_risks) / len(all_risks)
            state.confidence_scores["risk_analysis"] = avg_conf
        else:
            coverage = calculate_discovery_coverage(state)
            state.confidence_scores["risk_analysis"] = (
                0.75 if coverage["coverage_ratio"] >= 0.8 else 0.55
            )

        state.history.append(
            {
                "agent": "risk_intelligence_agent",
                "action": "orchestrated_risk_providers",
                "providers": [p.name() for p in self.providers],
                "total_risks_found": len(all_risks),
                "status": "success",
            }
        )
        finish_stage(state, "risk_analysis")

        return state


def risk_agent(state: AgentState) -> AgentState:
    """Entry point for the risk agent."""
    agent = RiskIntelligenceAgent()
    return agent.run(state)
