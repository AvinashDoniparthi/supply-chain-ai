import logging
import re
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from models.state import AgentState, RiskAnalysis, SupplierInfo
from models.verification import VerificationResult

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
            "Hsinchu, Taiwan": {
                "severity": "High",
                "reasoning": "High-tension regional zone with potential for conflict-driven disruptions.",
            },
            "Ukraine": {
                "severity": "Critical",
                "reasoning": "Active conflict zone.",
            },
            "South China Sea": {
                "severity": "Medium",
                "reasoning": "Territorial disputes impacting maritime trade routes.",
            },
        }

        for supplier in state.suppliers:
            print(f"\n=== {self.name()} PROVIDER DEBUG ===")
            print(f"Supplier: {supplier.name}")
            
            supplier_risks = []
            location = getattr(supplier, "location", "") or ""

            if location in high_tension_zones:
                zone_info = high_tension_zones[location]

                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Geopolitical",
                        severity=zone_info["severity"],
                        confidence=0.9,
                        reasoning=zone_info["reasoning"],
                        mitigation="Identify and qualify alternative suppliers in diverse geographic regions.",
                    )
                )

            elif any(
                zone in location
                for zone in ["China", "Taiwan", "Russia", "Middle East"]
            ):
                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Geopolitical",
                        severity="Medium",
                        confidence=0.7,
                        reasoning=f"Supplier located in region with increasing trade or political tensions ({location}).",
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
                print(
                    f"RISK -> "
                    f"{risk.supplier_name} | "
                    f"{risk.risk_type} | "
                    f"{risk.severity} | "
                    f"{risk.reasoning}"
                )
            
            print(f"Risks Generated: {len(supplier_risks)}")
            risks.extend(supplier_risks)

        return risks


class VerificationRiskProvider(RiskProvider):
    """Assess risks based on verification confidence and status."""

    def name(self) -> str:
        return "Verification"

    def assess_risk(self, state: AgentState) -> List[RiskAnalysis]:

        risks = []
        verification_map = {v.supplier_name: v for v in state.verification_results}

        for supplier in state.suppliers:
            print(f"\n=== {self.name()} PROVIDER DEBUG ===")
            print(f"Supplier: {supplier.name}")
            
            supplier_risks = []
            verification = verification_map.get(supplier.name) or verification_map.get(
                getattr(supplier, "canonical_name", "")
            )

            # Missing verification
            if not verification:
                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Operational",
                        severity="Medium",
                        confidence=1.0,
                        reasoning="No verification data found for this supplier. Legitimacy cannot be confirmed.",
                        mitigation="Initiate immediate verification process for this entity.",
                    )
                )
            # Failed verification
            elif not verification.verified:
                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Strategic",
                        severity="High",
                        confidence=verification.confidence_score,
                        reasoning=f"Supplier failed verification. Reasoning: {verification.reasoning}",
                        mitigation="Discontinue relationship or perform an exhaustive manual audit.",
                    )
                )
            # Low-confidence verification
            elif verification.confidence_score < 0.8:
                supplier_risks.append(
                    RiskAnalysis(
                        supplier_name=supplier.name,
                        risk_type="Operational",
                        severity="Low",
                        confidence=verification.confidence_score,
                        reasoning=f"Low verification confidence ({verification.confidence_score:.2f}). Data may be stale or contradictory.",
                        mitigation="Request updated documentation or on-site verification.",
                    )
                )

            # Rule: Max 1 verification risk per supplier
            if len(supplier_risks) > 1:
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = [supplier_risks[0]]

            for risk in supplier_risks:
                print(
                    f"RISK -> "
                    f"{risk.supplier_name} | "
                    f"{risk.risk_type} | "
                    f"{risk.severity} | "
                    f"{risk.reasoning}"
                )
            
            print(f"Risks Generated: {len(supplier_risks)}")
            risks.extend(supplier_risks)

        return risks


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
            print(f"\n=== {self.name()} PROVIDER DEBUG ===")
            print(f"Supplier: {supplier.name}")
            
            # Only analyze verified suppliers
            verification = verification_map.get(supplier.name) or verification_map.get(
                getattr(supplier, "canonical_name", "")
            )

            if not verification or not verification.verified:
                print(f"Skipping {supplier.name} - Not verified")
                continue

            # 1. Fetch news
            news_items = self._fetch_news(supplier.name)
            
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
            
            for item in recent_news:
                # Rule 1 & 2: one risk per article, highest severity
                risk, keywords = self._analyze_headline_with_keywords(supplier.name, item)
                if risk:
                    articles_triggering += 1
                    supplier_risks.append(risk)
                    detected_keywords.update(keywords)
                    
                    # Log triggered article
                    print(f"headline: {item['title']}")
                    print(f"matched keyword: {', '.join(keywords)}")
                    print(f"generated severity: {risk.severity}")

            # Rule 3: Limit to max 3 news risks per supplier (highest severity)
            if len(supplier_risks) > 3:
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = supplier_risks[:3]

            # Mandatory Investigation Logs
            print(f"Articles Retrieved: {len(news_items)}")
            print(f"Articles After Date Filter: {len(recent_news)}")
            print(f"Articles Triggering Risk: {articles_triggering}")
            print(f"Risks Generated: {len(supplier_risks)}")

            for risk in supplier_risks:
                print(
                    f"RISK -> "
                    f"{risk.supplier_name} | "
                    f"{risk.risk_type} | "
                    f"{risk.severity} | "
                    f"{risk.reasoning}"
                )

            risks.extend(supplier_risks)

        return risks

    def _fetch_news(self, supplier_name: str) -> List[Dict[str, Any]]:
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

        for query in queries:
            try:
                url = "https://news.google.com/rss/search"
                params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
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
            except Exception as e:
                logger.error(f"Failed to fetch news for query '{query}': {e}")
                
        return all_items

    def _analyze_headline_with_keywords(self, supplier_name: str, item: Dict[str, Any]) -> tuple[Optional[RiskAnalysis], List[str]]:
        """Analyzes headline and returns (RiskAnalysis, matched_keywords)."""
        title = item["title"].lower()
        snippet = item["snippet"].lower()
        text = f"{title} {snippet}"
        
        found_keywords = []
        
        # 1. Critical
        critical_kws = ["shutdown", "war", "sanction", "bankruptcy", "explosion", "natural disaster", "catastrophe"]
        matched_critical = [kw for kw in critical_kws if kw in text]
        if matched_critical:
            found_keywords.extend(matched_critical)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="Critical",
                confidence=0.8,
                reasoning=f"Critical event detected: {item['title']}.",
                mitigation="Assess total exposure and identify immediate alternatives."
            ), found_keywords

        # 2. High
        high_kws = ["strike", "export restriction", "severe disruption", "shortage", "disruption", "fire", "flood", "earthquake", "escalation"]
        matched_high = [kw for kw in high_kws if kw in text]
        if matched_high:
            found_keywords.extend(matched_high)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="High",
                confidence=0.75,
                reasoning=f"Significant risk detected: {item['title']}. High probability of delivery delays.",
                mitigation="Notify production teams and prepare buffer stock or secondary routes."
            ), found_keywords

        # 3. Medium
        medium_kws = ["investigation", "lawsuit", "restructuring", "fine", "litigation"]
        matched_medium = [kw for kw in medium_kws if kw in text]
        if matched_medium:
            found_keywords.extend(matched_medium)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="Medium",
                confidence=0.65,
                reasoning=f"Moderate operational/regulatory issue: {item['title']}.",
                mitigation="Conduct detailed risk review and monitor for further escalation."
            ), found_keywords

        # 4. Low
        low_kws = ["warning", "rumor", "layoff", "protest", "dispute"]
        matched_low = [kw for kw in low_kws if kw in text]
        if matched_low:
            found_keywords.extend(matched_low)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="News",
                severity="Low",
                confidence=0.55,
                reasoning=f"Potential early warning signal: {item['title']}.",
                mitigation="Track news cycle for 7-14 days for resolution or escalation."
            ), found_keywords

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
            print(f"\n=== {self.name()} PROVIDER DEBUG ===")
            print(f"Supplier: {supplier.name}")
            
            # Only analyze verified suppliers
            verification = verification_map.get(supplier.name) or verification_map.get(
                getattr(supplier, "canonical_name", "")
            )

            if not verification or not verification.verified:
                print(f"Skipping {supplier.name} - Not verified")
                continue

            # 1. Fetch news
            news_items = self._fetch_news(supplier.name)
            
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
            
            for item in recent_news:
                risk, keywords = self._analyze_financial_headline(supplier.name, item)
                if risk:
                    articles_triggering += 1
                    supplier_risks.append(risk)
                    detected_keywords.update(keywords)
                    
                    # Log triggered article
                    print(f"headline: {item['title']}")
                    print(f"matched keyword: {', '.join(keywords)}")
                    print(f"generated severity: {risk.severity}")

            # Rule: Limit to max 3 financial risks per supplier (highest severity)
            if len(supplier_risks) > 3:
                severity_map = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                supplier_risks.sort(key=lambda r: severity_map.get(r.severity, 0), reverse=True)
                supplier_risks = supplier_risks[:3]

            # Mandatory Investigation Logs
            print(f"Articles Retrieved: {len(news_items)}")
            print(f"Articles After Date Filter: {len(recent_news)}")
            print(f"Articles Triggering Risk: {articles_triggering}")
            print(f"Risks Generated: {len(supplier_risks)}")

            for risk in supplier_risks:
                print(
                    f"RISK -> "
                    f"{risk.supplier_name} | "
                    f"{risk.risk_type} | "
                    f"{risk.severity} | "
                    f"{risk.reasoning}"
                )

            risks.extend(supplier_risks)

        return risks

    def _fetch_news(self, supplier_name: str) -> List[Dict[str, Any]]:
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

        for query in queries:
            try:
                url = "https://news.google.com/rss/search"
                params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
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
            except Exception as e:
                logger.error(f"Failed to fetch financial news for query '{query}': {e}")
                
        return all_items

    def _analyze_financial_headline(self, supplier_name: str, item: Dict[str, Any]) -> tuple[Optional[RiskAnalysis], List[str]]:
        """Analyzes financial headline and returns (RiskAnalysis, matched_keywords)."""
        title = item["title"].lower()
        snippet = item["snippet"].lower()
        text = f"{title} {snippet}"
        
        found_keywords = []
        
        # 1. Critical
        critical_kws = ["bankruptcy", "insolvency", "liquidation", "default", "restructuring"]
        matched_critical = [kw for kw in critical_kws if kw in text]
        if matched_critical:
            found_keywords.extend(matched_critical)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="Critical",
                confidence=0.85,
                reasoning=f"Critical financial event: {item['title']}.",
                mitigation="Evaluate immediate alternate suppliers and assess total exposure."
            ), found_keywords

        # 2. High
        high_kws = ["debt crisis", "major layoffs", "plant closure", "factory closure", "revenue collapse", "severe losses"]
        matched_high = [kw for kw in high_kws if kw in text]
        if matched_high:
            found_keywords.extend(matched_high)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="High",
                confidence=0.8,
                reasoning=f"High financial risk detected: {item['title']}.",
                mitigation="Evaluate alternate suppliers and monitor financial disclosures."
            ), found_keywords

        # 3. Medium
        medium_kws = ["earnings miss", "declining revenue", "profit warning", "cost cutting", "workforce reduction"]
        matched_medium = [kw for kw in medium_kws if kw in text]
        if matched_medium:
            found_keywords.extend(matched_medium)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="Medium",
                confidence=0.7,
                reasoning=f"Moderate financial signal: {item['title']}.",
                mitigation="Request financial health disclosure and monitor quarterly performance."
            ), found_keywords

        # 4. Low
        low_kws = ["slowdown", "weak demand", "reduced guidance"]
        matched_low = [kw for kw in low_kws if kw in text]
        if matched_low:
            found_keywords.extend(matched_low)
            return RiskAnalysis(
                supplier_name=supplier_name,
                risk_type="Financial",
                severity="Low",
                confidence=0.6,
                reasoning=f"Minor financial warning: {item['title']}.",
                mitigation="Track performance for next 2 quarters for stabilization."
            ), found_keywords

        return None, []


class RiskIntelligenceAgent:
    """Orchestrator for multiple risk providers."""

    def __init__(self):
        self.providers = [
            GeopoliticalRiskProvider(),
            VerificationRiskProvider(),
            NewsRiskProvider(),
            FinancialRiskProvider(),
        ]

    def run(self, state: AgentState) -> AgentState:

        print("\n=== RISK INPUT TRACE ===")
        print(f"Suppliers sent to risk analysis: {len(state.suppliers)}")

        for supplier in state.suppliers:
            print(
                f"Supplier: {supplier.name} | "
                f"Canonical: {getattr(supplier, 'canonical_name', 'N/A')} | "
                f"Location: {getattr(supplier, 'location', 'N/A')}"
            )

        print("\n--- RISK INTELLIGENCE AGENT: Orchestrating Risk Assessments ---")

        all_risks = []

        for provider in self.providers:
            provider_risks = provider.assess_risk(state)
            
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
                    print(f"\nDUPLICATE RISK REMOVED:\nSupplier={risk.supplier_name}\nRiskType={risk.risk_type}")

            print(f"\nTOTAL RISKS FROM {provider.name()}: {len(unique_provider_risks)}")
            all_risks.extend(unique_provider_risks)

        print(f"\nTOTAL RISKS GENERATED: {len(all_risks)}")

        state.risk_assessments.extend(all_risks)
        state.current_task = "Risk assessment completed"

        if all_risks:
            avg_conf = sum(r.confidence for r in all_risks) / len(all_risks)
            state.confidence_scores["risk_analysis"] = avg_conf
        else:
            state.confidence_scores["risk_analysis"] = 1.0

        state.history.append(
            {
                "agent": "risk_intelligence_agent",
                "action": "orchestrated_risk_providers",
                "providers": [p.name() for p in self.providers],
                "total_risks_found": len(all_risks),
                "status": "success",
            }
        )

        return state


def risk_agent(state: AgentState) -> AgentState:
    """Entry point for the risk agent."""
    agent = RiskIntelligenceAgent()
    return agent.run(state)
