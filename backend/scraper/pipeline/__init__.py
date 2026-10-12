"""Pipeline générique : scrape -> nettoyage/chunks -> ChromaDB.
Utilisé par /api/scrape/run (en tâche de fond) et par scheduler.py."""

import time

from app import config
from app.metadata import log_scraped_page
from scraper.ingest import replace_domain_chunks
from scraper.parser import extract_site_info, parse_page, site_info_chunks
from scraper.pipeline.engine_select import pick_engine_and_crawl as _crawl, resolve_scheme
from scraper.pipeline.site_name import site_name
from scraper.spider import domain_key, normalize_url

SCRAPER_TARGET_URL = config.env("SCRAPER_TARGET_URL", "https://example.com")
DEFAULT_MAX_PAGES = config.env_int("SCRAPER_MAX_PAGES", 100)
DEFAULT_MAX_DEPTH = config.env_int("SCRAPER_MAX_DEPTH", 5)


def _collect_chunks(pages):
    """Parse chaque page et déduplique les chunks identiques entre pages."""
    all_chunks, per_page, seen_texts = [], [], set()
    for page in pages:
        chunks = parse_page(page["url"], page["html"], depth=page["depth"])
        kept = []
        for c in chunks:
            body = c["text"].split("\n", 1)[-1]
            if body in seen_texts:
                continue
            seen_texts.add(body)
            kept.append(c)
        all_chunks.extend(kept)
        title = chunks[0]["metadata"]["title"] if chunks else ""
        per_page.append((page["url"], title, len(kept)))
    return all_chunks, per_page


def _contact_info_chunks(pages, per_page):
    """Chunks du bloc contact (accueil + page contact)."""
    info_parts = []
    for page in pages:
        if page["depth"] == 0 or "contact" in page["url"].lower():
            info = extract_site_info(page["html"])
            if info and info not in info_parts:
                info_parts.append(info)
    title = site_name(pages, [t for _, t, _ in per_page])
    return site_info_chunks(pages[0]["url"], "\n\n".join(info_parts), site_name=title), title


def run_pipeline(target_url=None, max_pages=None, max_depth=None, progress=None):
    target_url = normalize_url(target_url or SCRAPER_TARGET_URL)
    max_pages = int(max_pages) if max_pages else DEFAULT_MAX_PAGES
    max_depth = int(max_depth) if max_depth is not None else DEFAULT_MAX_DEPTH

    started_at = time.time()
    target_url = resolve_scheme(target_url)
    (pages, pages_failed, urls_found), engine = _crawl(
        target_url, max_pages, max_depth, progress)

    if not pages and target_url.startswith("https://"):
        http_url = "http://" + target_url[len("https://"):]
        print(f"[pipeline] aucune page en HTTPS -> nouvel essai en {http_url}")
        (pages, pages_failed, urls_found), engine = _crawl(
            http_url, max_pages, max_depth, progress)

    if not pages:
        return {
            "status": "error",
            "error": "Aucune page n'a pu être récupérée (site inaccessible, bloqué ou vide).",
            "start_url": target_url, "pages_scraped": 0, "pages_failed": pages_failed,
            "chunks_created": 0, "urls_found": urls_found, "engine": engine,
            "duration_seconds": round(time.time() - started_at, 1),
        }

    source_domain = domain_key(pages[0]["url"])
    all_chunks, per_page = _collect_chunks(pages)
    info_chunks, site_title = _contact_info_chunks(pages, per_page)
    all_chunks.extend(info_chunks)

    total_chunks = replace_domain_chunks(source_domain, all_chunks)
    for url, title, n in per_page:
        log_scraped_page(url, title, n)

    result = {
        "status": "success", "start_url": target_url, "site_url": pages[0]["url"],
        "source_domain": source_domain, "site_title": site_title,
        "pages_scraped": len(pages), "pages_failed": pages_failed,
        "chunks_created": total_chunks, "urls_found": urls_found, "engine": engine,
        "duration_seconds": round(time.time() - started_at, 1),
    }
    print(f"[pipeline] {result}")
    return result
