"""
Pipeline générique : scrape -> parse/chunk -> stocke dans ChromaDB.
Utilisé par /api/scrape/run et par scheduler.py.
"""

import os
import time

import requests
from bs4 import BeautifulSoup

from scraper.spider import crawl, crawl_with_playwright, USER_AGENT
from scraper.parser import parse_page, clean_html
from scraper.ingest import ingest_chunks

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.metadata import log_scraped_page  # noqa: E402

SCRAPER_TARGET_URL = os.environ.get("SCRAPER_TARGET_URL", "https://example.com")

# "true" -> toujours Playwright | "false" -> toujours requests+BS4
# "auto" (defaut) -> le pipeline teste la page de depart et decide seul :
#   si le HTML brut ne contient (quasi) aucun texte/lien exploitable
#   (site en React/Vue/Next/Lovable... rendu cote client), on bascule
#   automatiquement sur Playwright pour ce run. Sinon on garde requests
#   (beaucoup plus rapide) sans rien configurer manuellement par site.
USE_PLAYWRIGHT_MODE = os.environ.get("SCRAPER_USE_PLAYWRIGHT", "auto").lower()

# Seuils de detection "SPA / contenu charge en JS"
MIN_TEXT_LENGTH = int(os.environ.get("SCRAPER_SPA_MIN_TEXT_LENGTH", 200))
MIN_LINKS_FOUND = int(os.environ.get("SCRAPER_SPA_MIN_LINKS", 1))

DEFAULT_MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
DEFAULT_MAX_DEPTH = int(os.environ.get("SCRAPER_MAX_DEPTH", 5))


def _looks_like_js_rendered_spa(target_url):
    """
    Fait une requete rapide (sans navigateur) sur la page de depart et
    verifie si elle contient un minimum de texte visible et de liens.
    Si non -> le site rend probablement son contenu en JS cote client
    (SPA React/Vue/Next/Lovable/etc.) et requests+BeautifulSoup ne pourra
    jamais recuperer les autres pages.
    """
    try:
        resp = requests.get(
            target_url, headers={"User-Agent": USER_AGENT}, timeout=15
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException as exc:
        print(f"[pipeline] pre-check echoue ({exc}) -> on tente Playwright par securite")
        return True

    _, text = clean_html(html)
    nb_links = len(BeautifulSoup(html, "html.parser").find_all("a", href=True))

    is_thin = len(text) < MIN_TEXT_LENGTH
    has_few_links = nb_links < MIN_LINKS_FOUND

    print(
        f"[pipeline] pre-check '{target_url}': "
        f"{len(text)} car. de texte, {nb_links} liens <a> -> "
        f"{'SPA detectee, Playwright requis' if (is_thin or has_few_links) else 'HTML statique, requests suffit'}"
    )
    return is_thin or has_few_links


def _resolve_crawl_fn(target_url):
    if USE_PLAYWRIGHT_MODE == "true":
        return crawl_with_playwright
    if USE_PLAYWRIGHT_MODE == "false":
        return crawl
    # mode "auto" (par defaut)
    return crawl_with_playwright if _looks_like_js_rendered_spa(target_url) else crawl


def run_pipeline(target_url=None, max_pages=None, max_depth=None):
    target_url = target_url or SCRAPER_TARGET_URL
    max_pages = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
    max_depth = max_depth if max_depth is not None else DEFAULT_MAX_DEPTH

    started_at = time.time()

    crawl_fn = _resolve_crawl_fn(target_url)
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