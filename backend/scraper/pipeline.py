"""
Pipeline complet : scrape -> parse/chunk -> stocke dans Chroma.
Utilisé par l'endpoint /api/scrape/run et par scheduler.py.
"""

import os
import time

from scraper.spider import crawl, crawl_with_playwright
from scraper.parser import parse_page
from scraper.ingest import ingest_chunks

SCRAPER_TARGET_URL = os.environ.get("SCRAPER_TARGET_URL", "https://skapa-academy.com")
USE_PLAYWRIGHT = os.environ.get("SCRAPER_USE_PLAYWRIGHT", "false").lower() == "true"


def run_pipeline(target_url=None):
    target_url = target_url or SCRAPER_TARGET_URL
    started_at = time.time()

    pages = crawl_with_playwright(target_url) if USE_PLAYWRIGHT else crawl(target_url)

    total_chunks = 0
    for page in pages:
        chunks = parse_page(page["url"], page["html"])
        total_chunks += ingest_chunks(chunks)

    duration = round(time.time() - started_at, 1)

    result = {
        "target_url": target_url,
        "pages_scraped": len(pages),
        "chunks_indexed": total_chunks,
        "duration_seconds": duration,
    }
    print(f"[pipeline] {result}")
    return result


if __name__ == "__main__":
    # Lancement manuel : python -m scraper.pipeline
    run_pipeline()
