import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompanyScraper:
    """
    A scraper to gather company information from public sources (primarily Wikipedia).
    """

    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def search_company(self, company_name: str) -> Dict[str, Any]:
        """
        Search for a company and return its details.

        Args:
            company_name: Name of the company to search for.

        Returns:
            A dictionary containing company details.
        """
        logger.info(f"Searching for company: {company_name}")

        try:
            # Step 1: Search Wikipedia for the company
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": company_name,
                "format": "json",
                "limit": 1,
            }

            response = self.session.get(search_url, params=params, headers=self.headers)
            response.raise_for_status()
            search_results = response.json().get("query", {}).get("search", [])

            if not search_results:
                logger.warning(f"No Wikipedia results found for {company_name}")
                return self._get_empty_result(company_name)

            page_title = search_results[0]["title"]
            logger.info(f"Found Wikipedia page: {page_title}")

            # Step 2: Fetch the page content
            page_url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
            page_response = self.session.get(page_url, headers=self.headers)
            page_response.raise_for_status()

            return self._parse_wikipedia_page(page_response.text, company_name)

        except Exception as e:
            logger.error(f"Error scraping company info for {company_name}: {e}")
            return self._get_empty_result(company_name)

    def _parse_wikipedia_page(self, html: str, company_name: str) -> Dict[str, Any]:
        """
        Parses the Wikipedia page to extract company info from the infobox.
        """
        soup = BeautifulSoup(html, "html.parser")
        infobox = soup.find("table", {"class": "infobox"})

        data = {
            "name": company_name,
            "industry": "Unknown",
            "headquarters": "Unknown",
            "description": "",
            "website": None,
        }

        # Extract description from the first few paragraphs
        content_div = soup.find("div", {"class": "mw-parser-output"})
        if content_div:
            paragraphs = content_div.find_all("p", recursive=False)
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 20:
                    data["description"] = text
                    # Remove citations like [1], [2]
                    import re

                    data["description"] = re.sub(r"\[\d+\]", "", data["description"])
                    break

        if infobox:
            rows = infobox.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    label = th.text.strip().lower()
                    # Get all text from td, preserving some structure
                    value = td.get_text(separator=" ").strip()

                    if "industry" in label:
                        data["industry"] = value
                    elif "headquarters" in label:
                        data["headquarters"] = value
                    elif "website" in label:
                        data["website"] = value

        return data

    def _get_empty_result(self, company_name: str) -> Dict[str, Any]:
        return {
            "name": company_name,
            "industry": "Not found",
            "headquarters": "Not found",
            "description": f"Could not find public information for {company_name}.",
            "website": None,
        }
