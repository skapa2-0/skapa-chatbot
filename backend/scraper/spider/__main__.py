"""Permet d'invoquer le crawler via `python -m scraper.spider`."""

from app import config
from scraper.spider import crawl

if __name__ == "__main__":
    target = config.env("SCRAPER_TARGET_URL", "https://example.com")
    results, _, _ = crawl(target, max_pages=10, max_depth=2)
    print(f"{len(results)} pages recuperees")
