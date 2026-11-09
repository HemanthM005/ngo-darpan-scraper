"""Configuration for the NGO Darpan directory scraper.

NGO Darpan (ngodarpan.gov.in) is NITI Aayog's public registry of voluntary
organisations / NGOs. Records are searchable by state and sector and returned
as a paginated HTML table. A captcha guards the search form, so the scraper
runs API/requests-first and falls back to a browser when challenged.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BASE_URL = "https://ngodarpan.gov.in"
SEARCH_PATH = "/index.php/search/"          # public NGO search
RESULTS_PATH = "/index.php/ajaxcontroller/search_index"  # paginated results

# All States + UTs we iterate over. The site keys states by its own numeric
# ids; the loader resolves the live id->name map at runtime, but this list is
# the canonical set we expect to see represented in the output.
STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
)


@dataclass(frozen=True)
class ScraperConfig:
    base_url: str = BASE_URL
    search_path: str = SEARCH_PATH
    results_path: str = RESULTS_PATH
    states: tuple[str, ...] = STATES

    # Politeness / resilience
    user_agent: str = (
        "ngo-darpan-scraper/1.0 "
        "(+https://github.com/HemanthM005/ngo-darpan-scraper)"
    )
    request_timeout: int = 30
    max_retries: int = 4
    backoff_factor: float = 1.5
    min_delay_seconds: float = 1.5           # directory scraping = many pages; be kind
    page_size: int = 10
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)

    # Browser fallback (captcha)
    use_browser_fallback: bool = True
    headless: bool = False
    browser_wait_ms: int = 20_000

    expected_columns: tuple[str, ...] = field(
        default=("unique_id", "ngo_name", "state", "sectors", "address")
    )
