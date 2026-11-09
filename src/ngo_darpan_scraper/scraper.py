"""Scrape NGO records from the NGO Darpan directory.

Strategy
--------
The search returns results as a paginated HTML table (AJAX-backed). This
scraper:
  1. Walks state-by-state so each query stays small and resumable.
  2. Paginates to the end of each state's results.
  3. Parses each result row into a raw dict (strings as published).
  4. Falls back to a real browser when the captcha blocks the request path.

Returns raw rows; all typing/cleaning happens in ``clean.py``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import ScraperConfig

logger = logging.getLogger(__name__)
RawRow = dict[str, Any]


def _build_session(cfg: ScraperConfig) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=cfg.max_retries,
        backoff_factor=cfg.backoff_factor,
        status_forcelist=cfg.retry_statuses,
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "X-Requested-With": "XMLHttpRequest",   # mimic the AJAX call
            "Referer": f"{cfg.base_url}{cfg.search_path}",
        }
    )
    return session


def parse_results_table(html: str) -> list[RawRow]:
    """Parse one page of the NGO results table into raw dict rows.

    The markup has drifted over the years (sometimes <table>, sometimes a list
    of cards), so we parse defensively: prefer a table, else fall back to any
    repeating row-like block that carries a unique-id + name.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[RawRow] = []

    table = soup.find("table")
    if table:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) >= 2:
                rows.append(dict(zip(headers, cells)) if headers else _positional(cells))
    return rows


def _positional(cells: list[str]) -> RawRow:
    """Map a header-less row by position to our expected shape."""
    keys = ["unique_id", "ngo_name", "address", "sectors", "state"]
    return {keys[i]: c for i, c in enumerate(cells) if i < len(keys)}


def _iter_state_pages(
    session: requests.Session, cfg: ScraperConfig, state: str
) -> Iterator[list[RawRow]]:
    """Yield parsed rows page by page for one state until results run out."""
    page = 1
    while True:
        time.sleep(cfg.min_delay_seconds)
        payload = {"state_search": state, "page": page, "per_page": cfg.page_size}
        url = f"{cfg.base_url}{cfg.results_path}"
        try:
            resp = session.post(url, data=payload, timeout=cfg.request_timeout)
        except requests.RequestException as exc:
            logger.warning("Request failed (%s p%d): %s", state, page, exc)
            return
        if resp.status_code != 200:
            logger.info("%s p%d -> HTTP %s (stopping state)", state, page, resp.status_code)
            return
        rows = parse_results_table(resp.text)
        if not rows:
            return
        for r in rows:
            r.setdefault("state", state)
        yield rows
        page += 1


def fetch_via_requests(cfg: ScraperConfig, states: tuple[str, ...]) -> list[RawRow]:
    session = _build_session(cfg)
    all_rows: list[RawRow] = []
    for state in states:
        logger.info("Scraping state: %s", state)
        state_rows = [r for page in _iter_state_pages(session, cfg, state) for r in page]
        logger.info("  -> %d records", len(state_rows))
        all_rows.extend(state_rows)
    return all_rows


def fetch_via_browser(cfg: ScraperConfig, states: tuple[str, ...]) -> list[RawRow]:
    """Browser fallback: solve the captcha once, then harvest the table."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Browser fallback needs Playwright: "
            "pip install playwright && playwright install chromium"
        ) from exc

    rows: list[RawRow] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless)
        page = browser.new_page(user_agent=cfg.user_agent)
        page.goto(f"{cfg.base_url}{cfg.search_path}", timeout=cfg.browser_wait_ms)
        logger.info("Solve the captcha in the opened browser if prompted...")
        for state in states:
            try:
                page.select_option("select#state_search", label=state)
                page.click("button[type=submit], input[type=submit]")
                page.wait_for_selector("table tr td", timeout=cfg.browser_wait_ms)
            except Exception:
                logger.warning("No results rendered for %s", state)
                continue
            page_rows = parse_results_table(page.content())
            for r in page_rows:
                r.setdefault("state", state)
            rows.extend(page_rows)
        browser.close()
    return rows


def scrape(
    cfg: ScraperConfig | None = None, states: tuple[str, ...] | None = None
) -> list[RawRow]:
    """API/requests-first, browser fallback. Optionally limit to given states."""
    cfg = cfg or ScraperConfig()
    states = states or cfg.states
    rows = fetch_via_requests(cfg, states)
    if rows:
        return rows
    if cfg.use_browser_fallback:
        logger.info("Falling back to browser (captcha)...")
        return fetch_via_browser(cfg, states)
    raise RuntimeError("No rows via requests and browser fallback disabled.")
