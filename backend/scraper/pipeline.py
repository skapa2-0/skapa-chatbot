"""
Pipeline générique : scrape -> parse/chunk -> stocke dans ChromaDB.
Utilisé par /api/scrape/run et par scheduler.py.
"""

import os
import time

from scraper.spider import crawl, crawl_with_playwright
from scraper.parser import parse_page
from scraper.ingest import ingest_chunks

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.metadata import log_scraped_page  # noqa: E402

SCRAPER_TARGET_URL = os.environ.get("SCRAPER_TARGET_URL", "https://example.com")
USE_PLAYWRIGHT = os.environ.get("SCRAPER_USE_PLAYWRIGHT", "false").lower() == "true"
DEFAULT_MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
DEFAULT_MAX_DEPTH = int(os.environ.get("SCRAPER_MAX_DEPTH", 5))


def run_pipeline(target_url=None, max_pages=None, max_depth=None):
    target_url = target_url or SCRAPER_TARGET_URL
    max_pages = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
    max_depth = max_depth if max_depth is not None else DEFAULT_MAX_DEPTH

    started_at = time.time()

    crawl_fn = crawl_with_playwright if USE_PLAYWRIGHT else crawl
    pages, pages_failed, urls_found = crawl_fn(
        target_url, max_pages=max_pages, max_depth=max_depth
    )

    total_chunks = 0
    for page in pages:
        chunks = parse_page(page["url"], page["html"], depth=page["depth"])
        total_chunks += ingest_chunks(chunks)
        title = chunks[0]["metadata"]["title"] if chunks else ""
        log_scraped_page(page["url"], title, len(chunks))

    duration = round(time.time() - started_at, 1)

    result = {
        "status": "success",
        "start_url": target_url,
        "pages_scraped": len(pages),
        "pages_failed": pages_failed,
        "chunks_created": total_chunks,
        "urls_found": urls_found,
        "duration_seconds": duration,
    }
    print(f"[pipeline] {result}")
    return result


if __name__ == "__main__":
    run_pipeline()
