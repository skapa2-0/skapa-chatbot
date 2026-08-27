"""
Crawler web générique : BFS depuis start_url, reste sur le même domaine,
respecte MAX_PAGES et MAX_DEPTH. Compatible avec n'importe quel site.
"""

import os
import time
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "GenericCrawlerBot/1.0")
MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
MAX_DEPTH = int(os.environ.get("SCRAPER_MAX_DEPTH", 5))
DELAY_SECONDS = float(os.environ.get("SCRAPER_DELAY_SECONDS", 0.5))


def normalize_url(url):
    """Retire le fragment (#...) et normalise les trailing slashes."""
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    result = urlunparse(clean)
    if result.endswith("/") and parsed.path not in ("", "/"):
        result = result.rstrip("/")
    return result


def same_domain(base_url, candidate_url):
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def extract_links(html, base_url):
    """Retourne l'ensemble des liens internes normalisés d'une page."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full_url = normalize_url(urljoin(base_url, href))
        if same_domain(base_url, full_url):
            links.add(full_url)
    return links


def crawl(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH):
    """
    BFS crawler (requests + BeautifulSoup).
    Retourne : (pages, pages_failed, urls_found_count)
    pages = [{"url": ..., "html": ..., "depth": ...}, ...]
    """
    start_url = normalize_url(start_url)
    queue = [(start_url, 0)]
    visited = set()
    pages = []
    failed = 0
    all_urls_found = set()

    headers = {"User-Agent": USER_AGENT}

    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if depth > max_depth:
            continue

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                continue
        except requests.RequestException as exc:
            print(f"[spider] echec {url}: {exc}")
            failed += 1
            continue

        html = response.text
        pages.append({"url": url, "html": html, "depth": depth})
        print(f"[spider] depth={depth} ok: {url}")

        if depth < max_depth:
            new_links = extract_links(html, url)
            all_urls_found.update(new_links)
            for link in new_links:
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(DELAY_SECONDS)

    print(f"[spider] {len(pages)} pages, {failed} echecs, {len(all_urls_found)} URLs trouvees")
    return pages, failed, len(all_urls_found)


def crawl_with_playwright(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH):
    """Variante Playwright pour les sites qui chargent leur contenu en JS."""
    from playwright.sync_api import sync_playwright

    start_url = normalize_url(start_url)
    queue = [(start_url, 0)]
    visited = set()
    pages = []
    failed = 0
    all_urls_found = set()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": USER_AGENT})

        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            if depth > max_depth:
                continue

            try:
                page.goto(url, timeout=25000, wait_until="networkidle")
            except Exception as exc:
                print(f"[spider-js] echec {url}: {exc}")
                failed += 1
                continue

            html = page.content()
            pages.append({"url": url, "html": html, "depth": depth})
            print(f"[spider-js] depth={depth} ok: {url}")

            if depth < max_depth:
                new_links = extract_links(html, url)
                all_urls_found.update(new_links)
                for link in new_links:
                    if link not in visited:
                        queue.append((link, depth + 1))

        browser.close()

    print(f"[spider-js] {len(pages)} pages, {failed} echecs, {len(all_urls_found)} URLs")
    return pages, failed, len(all_urls_found)


if __name__ == "__main__":
    target = os.environ.get("SCRAPER_TARGET_URL", "https://example.com")
    results, _, _ = crawl(target, max_pages=10, max_depth=2)
    print(f"{len(results)} pages recuperees")