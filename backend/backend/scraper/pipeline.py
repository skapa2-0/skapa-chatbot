"""Pipeline générique : scrape -> parse/chunk -> ChromaDB."""

import os
import time
import sys

from scraper.spider import crawl, crawl_auto, crawl_with_playwright
from scraper.parser import parse_page
from scraper.ingest import ingest_chunks

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.metadata import log_scraped_page  # noqa: E402

SCRAPER_TARGET_URL = os.environ.get("SCRAPER_TARGET_URL", "https://example.com")
SCRAPER_MODE = os.environ.get("SCRAPER_USE_PLAYWRIGHT", "auto").lower()
DEFAULT_MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
DEFAULT_MAX_DEPTH = int(os.environ.get("SCRAPER_MAX_DEPTH", 5))


def run_pipeline(target_url=None, max_pages=None, max_depth=None):
    target_url = target_url or SCRAPER_TARGET_URL
    max_pages = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
    max_depth = max_depth if max_depth is not None else DEFAULT_MAX_DEPTH
    started_at = time.time()

    if SCRAPER_MODE == "true":
        crawl_fn = crawl_with_playwright
    elif SCRAPER_MODE == "false":
        crawl_fn = crawl
    else:
        crawl_fn = crawl_auto

    pages, pages_failed, urls_found = crawl_fn(target_url, max_pages=max_pages, max_depth=max_depth)

    total_chunks = 0
    for page in pages:
        chunks = parse_page(page["url"], page["html"], depth=page["depth"])
        total_chunks += ingest_chunks(chunks)
        title = chunks[0]["metadata"]["title"] if chunks else ""
        log_scraped_page(page["url"], title, len(chunks))

    result = {
        "status": "success",
        "start_url": target_url,
        "scraper_mode": SCRAPER_MODE,
        "pages_scraped": len(pages),
        "pages_failed": pages_failed,
        "chunks_created": total_chunks,
        "urls_found": urls_found,
        "duration_seconds": round(time.time() - started_at, 1),
    }
    print(f"[pipeline] {result}")
    return result
