"""CLI: scrape -> clean -> validate -> CSV.

    python -m ngo_darpan_scraper --out data/ngos.csv --states "Telangana,Kerala"
"""
from __future__ import annotations

import argparse
import logging
import sys

from .clean import clean
from .config import ScraperConfig
from .scraper import scrape
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape the NGO Darpan directory.")
    parser.add_argument("--out", default="data/ngos.csv", help="output CSV path")
    parser.add_argument("--states", help="comma-separated subset of states (default: all)")
    parser.add_argument("--no-browser", action="store_true", help="disable browser fallback")
    parser.add_argument("--headless", action="store_true", help="run browser headless")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = ScraperConfig(use_browser_fallback=not args.no_browser, headless=args.headless)
    states = tuple(s.strip() for s in args.states.split(",")) if args.states else None

    logging.info("Scraping NGO Darpan...")
    raw = scrape(cfg, states)
    if not raw:
        logging.error("No data scraped. Exiting.")
        return 1

    df = clean(raw)
    logging.info("Cleaned %d unique NGO records across %d states.",
                 len(df), df["state"].nunique())

    try:
        validate(df)
    except Exception as exc:
        logging.error("Validation FAILED - not writing output.\n%s", exc)
        return 2

    df.to_csv(args.out, index=False)
    logging.info("Validated & wrote %d rows -> %s", len(df), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
