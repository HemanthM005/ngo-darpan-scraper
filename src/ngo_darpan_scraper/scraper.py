"""Scrape NGO records from the NGO Darpan directory.

NGO Darpan is an Angular SPA backed by a REST API under ``/apis/``. The scraper:
  1. Establishes a session via ``/apis/capis/sys-id``.
  2. Resolves the master state list from ``/apis/capis/mstr-states`` (so we use
     the site's own state ids rather than guessing them).
  3. Walks state-by-state, POSTing the paginated search and reading JSON.
  4. Falls back to a real browser if the JSON path is blocked (captcha).

The search payload/shape is the one piece that shifts between site revisions;
it is isolated in ``_search_payload`` / ``SEARCH_PATH`` so a change is a
one-line edit, confirmed from the browser Network tab.

Returns raw rows; all typing/cleaning happens in ``clean.py``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

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
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return session


def _establish_session(session: requests.Session, cfg: ScraperConfig) -> None:
    """Prime cookies / system id the API expects before searching."""
    try:
        session.get(f"{cfg.base_url}{cfg.sys_id_path}", timeout=cfg.request_timeout)
    except requests.RequestException as exc:
        logger.warning("sys-id handshake failed (continuing): %s", exc)


def fetch_states(session: requests.Session, cfg: ScraperConfig) -> list[dict[str, Any]]:
    """Return the site's master state list [{id, name}, ...]."""
    url = f"{cfg.base_url}{cfg.states_path}"
    try:
        resp = session.get(url, timeout=cfg.request_timeout)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not load master states (%s); using static list.", exc)
        return [{"id": None, "name": s} for s in cfg.states]
    # Strapi/Spring APIs wrap lists differently; find the first list of dicts.
    items = data.get("data", data) if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        name = it.get("name") or it.get("stateName") or it.get("state_name")
        sid = it.get("id") or it.get("stateId") or it.get("state_id")
        if name:
            out.append({"id": sid, "name": name})
    return out or [{"id": None, "name": s} for s in cfg.states]


def _search_payload(state: dict[str, Any], page: int, cfg: ScraperConfig) -> dict[str, Any]:
    """Build one search request body. CONFIRM keys against the live Network tab."""
    return {
        "stateId": state.get("id"),
        "stateName": state.get("name"),
        "pageNo": page,
        "pageSize": cfg.page_size,
    }


def _extract_json_rows(payload: Any) -> list[RawRow]:
    """Defensively pull NGO records out of a JSON response of unknown shape."""
    found: list[RawRow] = []
    IDISH = ("uniqueid", "unique_id", "regno", "ngoid", "darpanid")
    NAMEISH = ("ngoname", "name", "voname", "orgname")

    def looks_like_ngo(obj: dict[str, Any]) -> bool:
        keys = {k.lower().replace("_", "") for k in obj}
        return any(i in keys for i in IDISH) or any(n in keys for n in NAMEISH)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            dicts = [x for x in node if isinstance(x, dict)]
            if dicts and any(looks_like_ngo(x) for x in dicts):
                found.extend(dicts)
            else:
                for x in node:
                    walk(x)

    walk(payload)
    return found


def fetch_via_api(cfg: ScraperConfig, states: tuple[str, ...] | None) -> list[RawRow]:
    session = _build_session(cfg)
    _establish_session(session, cfg)

    state_list = fetch_states(session, cfg)
    if states:
        wanted = {s.lower() for s in states}
        state_list = [s for s in state_list if s["name"].lower() in wanted]

    url = f"{cfg.base_url}{cfg.search_path}"
    all_rows: list[RawRow] = []
    for state in state_list:
        logger.info("Scraping state: %s", state["name"])
        page, state_count = 1, 0
        while True:
            time.sleep(cfg.min_delay_seconds)
            try:
                resp = session.post(
                    url, json=_search_payload(state, page, cfg), timeout=cfg.request_timeout
                )
            except requests.RequestException as exc:
                logger.warning("  request failed (p%d): %s", page, exc)
                break
            if resp.status_code != 200:
                logger.info("  p%d -> HTTP %s (stopping state)", page, resp.status_code)
                break
            try:
                rows = _extract_json_rows(resp.json())
            except ValueError:
                rows = parse_results_table(resp.text)   # legacy HTML fallback
            if not rows:
                break
            for r in rows:
                r.setdefault("state", state["name"])
            all_rows.extend(rows)
            state_count += len(rows)
            page += 1
        logger.info("  -> %d records", state_count)
    return all_rows


def parse_results_table(html: str) -> list[RawRow]:
    """Legacy parser: handle the old server-rendered results table if seen."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[RawRow] = []
    table = soup.find("table")
    if not table:
        return rows
    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) >= 2:
            keys = headers or ["unique_id", "ngo_name", "address", "sectors", "state"]
            rows.append({keys[i]: c for i, c in enumerate(cells) if i < len(keys)})
    return rows


def fetch_via_browser(cfg: ScraperConfig, states: tuple[str, ...] | None) -> list[RawRow]:
    """Browser fallback: solve the captcha once, then harvest the rendered rows."""
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
        page.goto(f"{cfg.base_url}/#/", timeout=cfg.browser_wait_ms)
        logger.info("Use the opened browser to run a search / solve any captcha...")
        try:
            page.wait_for_selector("table tr td, .ngo-card", timeout=cfg.browser_wait_ms)
            rows = parse_results_table(page.content())
        except Exception:
            logger.warning("No rendered rows captured.")
        browser.close()
    return rows


def scrape(
    cfg: ScraperConfig | None = None, states: tuple[str, ...] | None = None
) -> list[RawRow]:
    """JSON-API first, browser fallback. Optionally limit to given state names."""
    cfg = cfg or ScraperConfig()
    rows = fetch_via_api(cfg, states)
    if rows:
        return rows
    if cfg.use_browser_fallback:
        logger.info("Falling back to browser (captcha)...")
        return fetch_via_browser(cfg, states)
    raise RuntimeError("No rows via API and browser fallback disabled.")
