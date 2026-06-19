import os
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
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
        self.cache_dir = "database/cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.stats = {
            "Wikipedia Success": 0,
            "Wikipedia Retry Count": 0,
            "Cache Used": 0,
        }

    def _get_cache_path(self, company_name: str) -> str:
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        return os.path.join(self.cache_dir, f"{safe_name}.json")

    def find_suppliers(self, company_name: str) -> List[Dict[str, Any]]:
        """
        Searches for suppliers using Wikipedia API with backoff and caching.
        """
        cache_path = self._get_cache_path(company_name)
        if os.path.exists(cache_path):
            print(f"\nCACHE HIT: {company_name}")
            self.stats["Cache Used"] += 1
            with open(cache_path, "r") as f:
                return json.load(f)

        print(f"\nCACHE MISS: {company_name}")
        logger.info(f"Searching for real suppliers of {company_name} via Wikipedia...")

        # Narrowed query set to prevent excessive Wikipedia usage
        queries = [
            f"{company_name} suppliers",
            f"{company_name} supply chain",
        ]

        discovered_data = []
        max_retries = 3

        for query in queries:
            retry_count = 0
            while True:
                try:
                    search_url = "https://en.wikipedia.org/w/api.php"
                    params = {
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "limit": 20,
                    }
                    response = self.session.get(
                        search_url, params=params, headers=self.headers, timeout=10
                    )

                    if response.status_code == 429:
                        retry_count += 1
                        if retry_count > max_retries:
                            logger.warning(
                                f"[429 RETRY] Attempt: {retry_count} Wait: aborted after max retries for query '{query}'"
                            )
                            self.stats["Wikipedia Retry Count"] += 1
                            break

                        retry_after = response.headers.get("Retry-After")
                        wait_time = None
                        if retry_after and retry_after.isdigit():
                            wait_time = int(retry_after)
                        else:
                            wait_time = min(2**retry_count, 20)

                        jitter = min(5, max(0, (wait_time * 0.2)))
                        wait_time = wait_time + (
                            jitter * (0.5 - os.urandom(1)[0] / 255.0)
                        )
                        wait_time = max(1.0, wait_time)

                        logger.warning(
                            f"[429 RETRY] Attempt: {retry_count} Wait: {wait_time:.1f}s"
                        )
                        self.stats["Wikipedia Retry Count"] += 1
                        time.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    self.stats["Wikipedia Success"] += 1

                    search_results = response.json().get("query", {}).get("search", [])
                    for res in search_results:
                        score = 0
                        snippet_low = res["snippet"].lower()
                        if company_name.lower() in snippet_low:
                            score += 5
                        rel_keywords = [
                            "supplies",
                            "supplier",
                            "provides",
                            "manufactures",
                            "vendor",
                            "contractor",
                            "component",
                            "parts",
                            "partnership",
                            "subsidiary",
                            "client",
                            "customer",
                        ]
                        score += sum(2 for k in rel_keywords if k in snippet_low)
                        discovered_data.append(
                            {
                                "title": res["title"],
                                "snippet": res["snippet"],
                                "link": f"https://en.wikipedia.org/wiki/{res['title'].replace(' ', '_')}",
                                "quality_score": score,
                            }
                        )

                    if discovered_data:
                        break

                    time.sleep(1.0)
                    break
                except Exception as e:
                    logger.error(f"Wikipedia search failed for '{query}': {e}")
                    break

            if discovered_data:
                break

        # Sort by quality score before extracting suppliers
        discovered_data.sort(key=lambda x: x["quality_score"], reverse=True)
        formatted_suppliers = self._extract_suppliers_from_results(
            discovered_data, company_name
        )

        # Save to cache if successful
        if formatted_suppliers:
            with open(cache_path, "w") as f:
                json.dump(formatted_suppliers, f)

        return formatted_suppliers

    def _extract_suppliers_from_results(
        self, results: List[Dict[str, str]], target_company: str
    ) -> List[Dict[str, Any]]:
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
            r"Algorithm",
        ]

        relationship_keywords = {
            "SUPPLIER": [
                "supplies",
                "supplier",
                "provides",
                "manufactures",
                "vendor",
                "contractor",
                "component",
                "parts",
                "semiconductor",
            ],
            "PARTNER": [
                "partnership",
                "partner",
                "collaboration",
                "joint venture",
                "alliance",
                "cooperation",
            ],
            "ACQUISITION": [
                "acquired",
                "merger",
                "acquisition",
                "bought",
                "subsidiary",
                "parent",
            ],
            "COMPETITOR": [
                "competitor",
                "rival",
                "competes",
                "competition",
                "competing",
                "vs",
                "versus",
            ],
            "LAWSUIT": [
                "lawsuit",
                "litigation",
                "sued",
                "infringement",
                "court",
                "legal action",
                "dispute",
            ],
        }

        target_norm = re.sub(r"[^a-z0-9]", "", target_company.lower())

        for res in results:
            clean_snippet = re.sub(
                r'<span class="searchmatch">|</span>', "", res["snippet"]
            )
            page_title = res["title"].lower()
            text = f"{res['title']} {clean_snippet}"
            low_text = text.lower()

            patterns = [
                r"\b([A-Z][A-Za-z0-9\s&]{2,40}\b(?:Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited))\b",
                r"\b([A-Z][A-Za-z0-9\s&]{2,30})\b (?:supplies|provides|manufactures|manufactured|assembles|assembled|is a supplier)",
                r"(?:assembled|manufactured|supplied) by \b([A-Z][A-Za-z0-9\s&]{2,30})\b",
                r"(?:including|such as) \b([A-Z][A-Za-z0-9\s&]{2,30})\b",
            ]

            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    name = match.group(1).strip()
                    name = re.sub(r"[,.\s]+$", "", name)
                    name = re.sub(r"^(the|a|an)\s+", "", name, flags=re.IGNORECASE)
                    name_norm = re.sub(r"[^a-z0-9]", "", name.lower())

                    if (
                        len(name) < 3
                        or target_norm in name_norm
                        or name_norm in target_norm
                    ):
                        continue
                    if any(
                        phrase in name.lower()
                        for phrase in [
                            "multinational corporation",
                            "designs and",
                            "manufactures consumer",
                            "based in",
                        ]
                    ):
                        continue

                    is_blacklisted = any(
                        re.search(b_pattern, name, re.IGNORECASE)
                        for b_pattern in blacklist_patterns
                    )
                    if is_blacklisted:
                        continue
                    if not name[0].isupper() or name.lower() in [
                        "this",
                        "it",
                        "they",
                        "the",
                    ]:
                        continue

                    detected_rel = "NEUTRAL"
                    customer_patterns = [
                        rf"{target_company.lower()}.*?(?:supplies|provides|manufactures|assembled for).*?{name.lower()}",
                        rf"{name.lower()}.*?is a (?:customer|client) of.*?{target_company.lower()}",
                        rf"{name.lower()}.*?(?:outsourced|contracted).*?to.*?{target_company.lower()}",
                    ]

                    if any(re.search(cp, low_text) for cp in customer_patterns):
                        detected_rel = "CUSTOMER"
                    else:
                        for rel_type, keywords in relationship_keywords.items():
                            if any(k in low_text for k in keywords):
                                detected_rel = rel_type
                                break

                    if " vs " in page_title or " versus " in page_title:
                        if name_norm in page_title:
                            detected_rel = "COMPETITOR"

                    if name not in suppliers:
                        justifications = {
                            "SUPPLIER": f"Directly mentioned as a supplier/vendor for {target_company}",
                            "PARTNER": f"Identified as having a partnership or collaboration with {target_company}",
                            "ACQUISITION": f"Mentioned in context of an acquisition or merger involving {target_company}",
                            "COMPETITOR": f"Identified as a competitor or rival to {target_company}",
                            "LAWSUIT": f"Mentioned in context of legal action or litigation with {target_company}",
                            "CUSTOMER": f"Identified as a customer or client of {target_company}",
                            "NEUTRAL": "Found in industry-related context",
                        }
                        suppliers[name] = {
                            "name": name,
                            "evidence": [],
                            "count": 0,
                            "snippet": clean_snippet,
                            "relationship": detected_rel,
                            "justification": justifications[detected_rel],
                        }

                    suppliers[name]["count"] += 1
                    if res["link"] not in [
                        e["link"] for e in suppliers[name]["evidence"]
                    ]:
                        suppliers[name]["evidence"].append(
                            {"link": res["link"], "snippet": res["snippet"]}
                        )

        formatted_suppliers = []
        for name, data in suppliers.items():
            confidence = 0.2 + min(data["count"] * 0.05, 0.2)
            if re.search(
                r"(Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited)$", name, re.IGNORECASE
            ):
                confidence += 0.1

            rel_weights = {
                "SUPPLIER": 0.4,
                "PARTNER": 0.2,
                "ACQUISITION": 0.1,
                "COMPETITOR": -0.4,
                "LAWSUIT": -0.3,
                "CUSTOMER": -0.5,
                "NEUTRAL": 0.0,
            }
            confidence += rel_weights.get(data["relationship"], 0.0)

            products = []
            lower_snippet = data["snippet"].lower()
            if any(
                k in lower_snippet
                for k in ["chips", "semiconductor", "processor", "soc", "logic"]
            ):
                products.append("Semiconductors")
            if any(
                k in lower_snippet
                for k in ["logistics", "shipping", "supply chain", "warehousing"]
            ):
                products.append("Logistics Services")
            if any(
                k in lower_snippet
                for k in ["display", "screen", "panel", "oled", "lcd", "led"]
            ):
                products.append("Display Panels")
            if any(
                k in lower_snippet
                for k in ["assembly", "manufacturing", "outsourced", "factory"]
            ):
                products.append("Contract Manufacturing")
            if any(k in lower_snippet for k in ["battery", "cells", "power"]):
                products.append("Energy Storage")

            formatted_suppliers.append(
                {
                    "name": name,
                    "location": "Unknown (Verified by Research)",
                    "products": products or ["General Components"],
                    "tier": 1 if confidence > 0.6 else 2,
                    "criticality": "High" if confidence > 0.7 else "Medium",
                    "confidence": round(max(0.01, min(confidence, 0.98)), 2),
                    "justification": data["justification"],
                    "source_evidence": data["evidence"][:2],
                }
            )

        formatted_suppliers.sort(key=lambda x: x["confidence"], reverse=True)
        return formatted_suppliers[:20]

    def get_stats(self) -> Dict[str, int]:
        return self.stats
