"""
Pipeline générique : scrape -> nettoyage/chunks -> ChromaDB.
Utilisé par /api/scrape/run (en tâche de fond) et par scheduler.py.

    cd backend && python -m scraper.pipeline https://mon-site.fr
"""

import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from app import config
from app.metadata import log_scraped_page
from scraper.ingest import replace_domain_chunks
from scraper.parser import clean_html, extract_site_info, parse_page, site_info_chunks
from scraper.spider import USER_AGENT, crawl, crawl_with_playwright, domain_key, normalize_url

SCRAPER_TARGET_URL = config.env("SCRAPER_TARGET_URL", "https://example.com")

# "true" -> toujours Playwright | "false" -> toujours requests
# "auto" (défaut) -> requests, et bascule sur Playwright si le site est une SPA
USE_PLAYWRIGHT_MODE = config.env("SCRAPER_USE_PLAYWRIGHT", "auto").lower()
MIN_TEXT_LENGTH = config.env_int("SCRAPER_SPA_MIN_TEXT_LENGTH", 200)
MIN_LINKS_FOUND = config.env_int("SCRAPER_SPA_MIN_LINKS", 1)

DEFAULT_MAX_PAGES = config.env_int("SCRAPER_MAX_PAGES", 100)
DEFAULT_MAX_DEPTH = config.env_int("SCRAPER_MAX_DEPTH", 5)


def _looks_like_js_rendered_spa(html):
    """Peu de texte / pas de liens dans le HTML brut -> contenu généré en JS."""
    _, text = clean_html(html)
    soup = BeautifulSoup(html, "html.parser")
    nb_links = len(soup.find_all("a", href=True))
    app_root = soup.find(id="root") or soup.find(id="__next") or soup.find(id="app") \
        or soup.find(id="__nuxt") or soup.find(attrs={"ng-version": True})
    is_thin = len(text) < MIN_TEXT_LENGTH
    return is_thin or nb_links < MIN_LINKS_FOUND or bool(app_root and nb_links <= 2)


def _precheck_is_spa(target_url):
    try:
        resp = requests.get(target_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[pipeline] pre-check échoué ({exc}) -> Playwright")
        return True
    spa = _looks_like_js_rendered_spa(resp.text)
    print(f"[pipeline] pre-check {target_url}: {'SPA -> Playwright' if spa else 'HTML statique -> requests'}")
    return spa


def _resolve_scheme(target_url):
    """https:// ajouté par défaut : si le site ne répond qu'en http, on bascule tout de suite.
    Utilise HEAD (pas GET) pour ne pas télécharger le corps de la page."""
    if not target_url.startswith("https://"):
        return target_url
    try:
        requests.head(target_url, headers={"User-Agent": USER_AGENT},
                      timeout=10, allow_redirects=True)
        return target_url
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
        http_url = "http://" + target_url[len("https://"):]
        try:
            requests.head(http_url, headers={"User-Agent": USER_AGENT},
                          timeout=10, allow_redirects=True)
            print(f"[pipeline] le site ne répond pas en HTTPS -> {http_url}")
            return http_url
        except requests.RequestException:
            return target_url
    except requests.RequestException:
        return target_url


def _crawl(target_url, max_pages, max_depth, progress):
    if USE_PLAYWRIGHT_MODE == "true":
        return crawl_with_playwright(target_url, max_pages, max_depth, progress), "playwright"
    if USE_PLAYWRIGHT_MODE == "false":
        return crawl(target_url, max_pages, max_depth, progress), "requests"

    if _precheck_is_spa(target_url):
        try:
            return crawl_with_playwright(target_url, max_pages, max_depth, progress), "playwright"
        except Exception as exc:  # Chromium absent : on fait au mieux avec requests
            print(f"[pipeline] Playwright indisponible ({exc}) -> requests")
            return crawl(target_url, max_pages, max_depth, progress), "requests"

    result = crawl(target_url, max_pages, max_depth, progress)
    pages = result[0]
    # Dernier filet : si requests n'a trouvé que la page d'accueil, c'est
    # probablement une navigation JS -> on retente avec le navigateur.
    if len(pages) <= 1 and max_pages > 1:
        try:
            js_result = crawl_with_playwright(target_url, max_pages, max_depth, progress)
            if len(js_result[0]) > len(pages):
                return js_result, "playwright"
        except Exception as exc:
            print(f"[pipeline] repli Playwright impossible ({exc})")
    return result, "requests"


def _site_name(pages, titles):
    """Nom du site : og:site_name, sinon le segment de titre commun à plusieurs pages."""
    if not pages:
        return titles[0].split(" | ")[0].strip() if titles else ""
    soup = BeautifulSoup(pages[0]["html"], "html.parser")
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    counts = {}
    for t in titles:
        for seg in re.split(r"\s+[|–—\-:·]\s+", t or ""):
            seg = seg.strip()
            if seg:
                counts[seg] = counts.get(seg, 0) + 1
    common = [s for s, n in counts.items() if n > 1]
    if common:
        return max(common, key=lambda s: counts[s])
    first = titles[0] if titles else ""
    return re.split(r"\s+[|–—\-:·]\s+", first)[0].strip() if first else ""


def run_pipeline(target_url=None, max_pages=None, max_depth=None, progress=None):
    target_url = normalize_url(target_url or SCRAPER_TARGET_URL)
    max_pages = int(max_pages) if max_pages else DEFAULT_MAX_PAGES
    max_depth = int(max_depth) if max_depth is not None else DEFAULT_MAX_DEPTH

    started_at = time.time()
    target_url = _resolve_scheme(target_url)
    (pages, pages_failed, urls_found), engine = _crawl(target_url, max_pages, max_depth, progress)

    if not pages and target_url.startswith("https://"):
        # Le site ne répond pas en HTTPS (certificat invalide / pas de TLS) : essai en HTTP
        http_url = "http://" + target_url[len("https://"):]
        print(f"[pipeline] aucune page en HTTPS -> nouvel essai en {http_url}")
        (pages, pages_failed, urls_found), engine = _crawl(http_url, max_pages, max_depth, progress)

    if not pages:
        return {
            "status": "error",
            "error": "Aucune page n'a pu être récupérée (site inaccessible, bloqué ou vide).",
            "start_url": target_url,
            "pages_scraped": 0,
            "pages_failed": pages_failed,
            "chunks_created": 0,
            "urls_found": urls_found,
            "engine": engine,
            "duration_seconds": round(time.time() - started_at, 1),
        }

    source_domain = domain_key(pages[0]["url"])
    all_chunks, per_page, seen_texts = [], [], set()
    for page in pages:
        chunks = parse_page(page["url"], page["html"], depth=page["depth"])
        # Supprime les chunks identiques répétés sur plusieurs pages
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

    # Coordonnées / contact (footer) : à partir de la page d'accueil + page contact
    info_parts = []
    for page in pages:
        if page["depth"] == 0 or "contact" in page["url"].lower():
            info = extract_site_info(page["html"])
            if info and info not in info_parts:
                info_parts.append(info)
    site_title = _site_name(pages, [t for _, t, _ in per_page])
    all_chunks.extend(site_info_chunks(pages[0]["url"], "\n\n".join(info_parts), site_name=site_title))

    total_chunks = replace_domain_chunks(source_domain, all_chunks)
    for url, title, n in per_page:
        log_scraped_page(url, title, n)

    result = {
        "status": "success",
        "start_url": target_url,
        "site_url": pages[0]["url"],
        "source_domain": source_domain,
        "site_title": site_title,
        "pages_scraped": len(pages),
        "pages_failed": pages_failed,
        "chunks_created": total_chunks,
        "urls_found": urls_found,
        "engine": engine,
        "duration_seconds": round(time.time() - started_at, 1),
    }
    print(f"[pipeline] {result}")
    return result


if __name__ == "__main__":
    run_pipeline(sys.argv[1] if len(sys.argv) > 1 else None)
