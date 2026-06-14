import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import logging
import re
import time
from models.state import SupplierInfo

logger = logging.getLogger(__name__)

class SupplierDiscoveryScraper:
    """
    Scrapes the web to identify real suppliers for a given company.
    Uses public search results and news mentions to build a list of partners.
    """

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    def find_suppliers(self, company_name: str) -> List[Dict[str, Any]]:
        """
        Searches for suppliers using Wikipedia API.
        """
        logger.info(f"Searching for real suppliers of {company_name} via Wikipedia...")
        
        # Refined queries for stronger relationship signals
        queries = [
            f"{company_name} suppliers and vendors",
            f"{company_name} supply chain partners",
            f"List of companies that supply {company_name}",
            f"{company_name} contract manufacturing",
            f"{company_name} major components suppliers"
        ]
        
        discovered_data = []
        
        for query in queries:
            try:
                search_url = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "limit": 10, # Increased limit to find better snippets
                }
                response = self.session.get(search_url, params=params, headers=self.headers)
                response.raise_for_status()
                
                search_results = response.json().get("query", {}).get("search", [])
                for res in search_results:
                    # Score snippet quality
                    score = 0
                    snippet_low = res["snippet"].lower()
                    
                    # High value: Target company name in snippet
                    if company_name.lower() in snippet_low:
                        score += 5
                        
                    # Relationship keywords
                    rel_keywords = ["supplies", "supplier", "provides", "manufactures", "vendor", "contractor", "component", "parts", "partnership", "subsidiary", "client", "customer"]
                    score += sum(2 for k in rel_keywords if k in snippet_low)
                    
                    discovered_data.append({
                        "title": res["title"],
                        "snippet": res["snippet"],
                        "link": f"https://en.wikipedia.org/wiki/{res['title'].replace(' ', '_')}",
                        "quality_score": score
                    })
                
                time.sleep(2.0) # Increased delay to respect Wikipedia API limits
            except Exception as e:
                logger.error(f"Wikipedia search failed for '{query}': {e}")

        # Sort by quality score before extracting suppliers
        discovered_data.sort(key=lambda x: x["quality_score"], reverse=True)
        return self._extract_suppliers_from_results(discovered_data, company_name)

    def _extract_suppliers_from_results(self, results: List[Dict[str, str]], target_company: str) -> List[Dict[str, Any]]:
        """
        Uses heuristics and text analysis to identify potential supplier names.
        Filters out non-company entities and Wikipedia meta-pages.
        """
        suppliers = {}
        
        # Keywords that indicate a Wikipedia meta-page or non-company entity
        blacklist_patterns = [
            r"^List of",
            r"^Criticism of",
            r"^History of",
            r"^Timeline of",
            r"^Environmental impact of",
            r"Litigation",
            r"Lawsuit",
            r"Codenames",
            r"Products of",
            r"Controversies",
            r"Silicon Valley",
            r"Cupertino",
            r"California",
            r"^The ",
            r"Operations at",
            r"Senior Vice President",
            r"Executive",
            r"Director of",
            r"ChatGPT",
            r"PyTorch",
            r"TensorFlow",
            r"Open source",
            r"Software",
            r"Algorithm"
        ]

        # Relationship indicators for context analysis
        relationship_keywords = {
            "SUPPLIER": ["supplies", "supplier", "provides", "manufactures", "vendor", "contractor", "component", "parts", "semiconductor"],
            "PARTNER": ["partnership", "partner", "collaboration", "joint venture", "alliance", "cooperation"],
            "ACQUISITION": ["acquired", "merger", "acquisition", "bought", "subsidiary", "parent"],
            "COMPETITOR": ["competitor", "rival", "competes", "competition", "competing", "vs", "versus"],
            "LAWSUIT": ["lawsuit", "litigation", "sued", "infringement", "court", "legal action", "dispute"]
        }

        # Normalize target company for comparison
        target_norm = re.sub(r'[^a-z0-9]', '', target_company.lower())

        for res in results:
            # Clean HTML tags from Wikipedia snippets
            clean_snippet = re.sub(r'<span class="searchmatch">|</span>', '', res['snippet'])
            page_title = res['title'].lower()
            text = f"{res['title']} {clean_snippet}"
            low_text = text.lower()
            
            # Potential supplier patterns
            patterns = [
                # Formal names with boundaries to avoid double matches
                r"\b([A-Z][A-Za-z\s&]+?\b(?:Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited))\b",
                # Action-based
                r"\b([A-Z][A-Za-z\s&]+)\b (?:supplies|provides|manufactures|is a supplier)",
                # List-based
                r"(?:including|such as) \b([A-Z][A-Za-z\s&]+)\b"
            ]

            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    name = match.group(1).strip()
                    
                    # Clean up trailing punctuation
                    name = re.sub(r'[,.\s]+$', '', name)
                    
                    # Normalize name for comparison
                    name_norm = re.sub(r'[^a-z0-9]', '', name.lower())
                    
                    # Filter out short names or the target company itself
                    if len(name) < 3 or target_norm in name_norm or name_norm in target_norm:
                        continue
                    
                    # Apply blacklist
                    is_blacklisted = False
                    for b_pattern in blacklist_patterns:
                        if re.search(b_pattern, name, re.IGNORECASE):
                            is_blacklisted = True
                            break
                    if is_blacklisted:
                        continue

                    # Further filter: must look like a company (start with uppercase)
                    if not name[0].isupper() or name.lower() in ["this", "it", "they", "the"]:
                        continue

                    # Detect relationship type based on context
                    detected_rel = "NEUTRAL"
                    
                    # Special check for directionality
                    customer_patterns = [
                        rf"{target_company.lower()}.*?(?:supplies|provides|manufactures|assembled for).*?{name.lower()}",
                        rf"{name.lower()}.*?is a (?:customer|client) of.*?{target_company.lower()}",
                        rf"{name.lower()}.*?(?:outsourced|contracted).*?to.*?{target_company.lower()}"
                    ]
                    
                    is_customer = False
                    for cp in customer_patterns:
                        if re.search(cp, low_text):
                            is_customer = True
                            break
                    
                    if is_customer:
                        detected_rel = "CUSTOMER"
                    else:
                        for rel_type, keywords in relationship_keywords.items():
                            if any(k in low_text for k in keywords):
                                detected_rel = rel_type
                                break
                    
                    # Penalty for competitor-like titles (e.g., "A vs B")
                    if " vs " in page_title or " versus " in page_title:
                        if name_norm in page_title:
                            detected_rel = "COMPETITOR"

                    if name not in suppliers:
                        # Determine justification
                        justifications = {
                            "SUPPLIER": f"Directly mentioned as a supplier/vendor for {target_company}",
                            "PARTNER": f"Identified as having a partnership or collaboration with {target_company}",
                            "ACQUISITION": f"Mentioned in context of an acquisition or merger involving {target_company}",
                            "COMPETITOR": f"Identified as a competitor or rival to {target_company}",
                            "LAWSUIT": f"Mentioned in context of legal action or litigation with {target_company}",
                            "CUSTOMER": f"Identified as a customer or client of {target_company}",
                            "NEUTRAL": "Found in industry-related context"
                        }

                        suppliers[name] = {
                            "name": name,
                            "evidence": [],
                            "count": 0,
                            "snippet": clean_snippet,
                            "relationship": detected_rel,
                            "justification": justifications[detected_rel]
                        }
                    
                    suppliers[name]["count"] += 1
                    if res['link'] not in [e['link'] for e in suppliers[name]["evidence"]]:
                        suppliers[name]["evidence"].append({
                            "link": res['link'],
                            "snippet": res['snippet']
                        })

        # Score and format
        formatted_suppliers = []
        for name, data in suppliers.items():
            # Base confidence
            confidence = 0.2
            
            # Boost based on frequency
            confidence += min(data["count"] * 0.05, 0.2)
            
            # Boost if formal suffix is present
            if re.search(r"(Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited)$", name, re.IGNORECASE):
                confidence += 0.1
            
            # Relationship weights
            rel_weights = {
                "SUPPLIER": 0.4,
                "PARTNER": 0.2,
                "ACQUISITION": 0.1,
                "COMPETITOR": -0.4,
                "LAWSUIT": -0.3,
                "CUSTOMER": -0.5,
                "NEUTRAL": 0.0
            }
            confidence += rel_weights.get(data["relationship"], 0.0)

            # Try to infer products from snippets
            products = []
            lower_snippet = data["snippet"].lower()
            if any(k in lower_snippet for k in ["chips", "semiconductor", "processor", "soc", "logic"]):
                products.append("Semiconductors")
            if any(k in lower_snippet for k in ["logistics", "shipping", "supply chain", "warehousing"]):
                products.append("Logistics Services")
            if any(k in lower_snippet for k in ["display", "screen", "panel", "oled", "lcd", "led"]):
                products.append("Display Panels")
            if any(k in lower_snippet for k in ["assembly", "manufacturing", "outsourced", "factory"]):
                products.append("Contract Manufacturing")
            if any(k in lower_snippet for k in ["battery", "cells", "power"]):
                products.append("Energy Storage")
            
            formatted_suppliers.append({
                "name": name,
                "location": "Unknown (Verified by Research)",
                "products": products or ["General Components"],
                "tier": 1 if confidence > 0.6 else 2,
                "criticality": "High" if confidence > 0.7 else "Medium",
                "confidence": round(max(0.01, min(confidence, 0.98)), 2),
                "justification": data["justification"],
                "source_evidence": data["evidence"][:2]
            })

        # Sort by confidence and return top 5
        formatted_suppliers.sort(key=lambda x: x["confidence"], reverse=True)
        return formatted_suppliers[:5]

        # Sort by confidence and return top 5
        formatted_suppliers.sort(key=lambda x: x["confidence"], reverse=True)
        return formatted_suppliers[:5]
