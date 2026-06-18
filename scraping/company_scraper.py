import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import logging
import json
import os
import re

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
        Search for a company, return its details, and save them to the database.

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
            
            # Validation: Ensure the title actually matches the company name
            name_norm = re.sub(r"[^\w\s]", "", company_name.lower())
            title_norm = re.sub(r"[^\w\s]", "", page_title.lower())
            
            # 1. Exact or substring match
            is_match = name_norm in title_norm or title_norm in name_norm
            
            # 2. Significant word overlap (loosened)
            if not is_match:
                # Words like "Semiconductor" or "Precision"
                significant_words = [w for w in name_norm.split() if len(w) > 6]
                if any(word in title_norm for word in significant_words):
                    is_match = True
            
            # 3. Abbreviation match (e.g., TSMC vs Taiwan Semiconductor...)
            if not is_match:
                from utils.identity_resolution import detect_abbreviation
                if detect_abbreviation(page_title, company_name) or detect_abbreviation(company_name, page_title):
                    is_match = True
            
            if not is_match:
                logger.warning(f"Wikipedia result '{page_title}' does not match target '{company_name}'. Rejecting.")
                return self._get_empty_result(company_name)

            logger.info(f"Found Wikipedia page: {page_title}")

            # Step 2: Fetch the page content
            page_url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
            page_response = self.session.get(page_url, headers=self.headers)
            page_response.raise_for_status()

            data = self._parse_wikipedia_page(page_response.text, company_name)

            # Step 3: Save the results (Fixing the 'isnt saving' issue)
            self.save_results(data)

            return data

        except Exception as e:
            logger.error(f"Error scraping company info for {company_name}: {e}")
            return self._get_empty_result(company_name)

    def save_results(self, data: Dict[str, Any], filename: Optional[str] = None):
        """
        Persists the scraped company data to a JSON file in the database directory.
        """
        if not filename:
            # Create a safe filename from the company name
            safe_name = (
                re.sub(r"[^\w\s-]", "", data["name"]).strip().replace(" ", "_").lower()
            )
            filename = f"{safe_name}_info.json"

        # Ensure database directory exists
        db_dir = "database"
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        filepath = os.path.join(db_dir, filename)

        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Successfully saved company data to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save results to {filepath}: {e}")

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
        # We look for the first paragraph with substantial text that isn't inside a table
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            # Skip paragraphs inside tables (like infoboxes or lists)
            if p.find_parent("table"):
                continue

            text = p.get_text().strip()
            if len(text) > 60:
                # Clean up citations and extra whitespace
                text = re.sub(r"\[.*?\]", "", text)
                text = re.sub(r"\s+", " ", text)
                data["description"] = text
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
                        # Try to find a real link
                        link = td.find("a", href=True)
                        if link and link["href"].startswith("http"):
                            data["website"] = link["href"]
                        else:
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
