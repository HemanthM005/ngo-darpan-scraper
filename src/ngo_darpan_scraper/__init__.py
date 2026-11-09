"""Scrape, clean and validate NGO records from the NGO Darpan directory."""
from .clean import clean
from .scraper import scrape
from .validate import validate

__all__ = ["scrape", "clean", "validate"]
__version__ = "1.0.0"
