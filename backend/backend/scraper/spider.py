"""Crawler web générique : BFS, même domaine, statique + JS."""

import os
import time
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "GenericCrawlerBot/1.0")
MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
MAX_DEPTH = int(os.environ.get("SCRAPER_MAX_DEPTH", 5))
DELAY_SECONDS = float(os.environ.get("SCRAPER_DELAY_SECONDS", 0.5))
REQUEST_TIMEOUT = float(os.environ.get("SCRAPER_REQUEST_TIMEOUT", 20))
PLAYWRIGHT_TIMEOUT = int(os.environ.get("SCRAPER_PLAYWRIGHT_TIMEOUT", 30000))


def normalize_url(url):
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    result = urlunparse(clean)
    if result.endswith("/") and parsed.path not in ("", "/"):
        result = result.rstrip("/")
    return result


def same_domain(base_url, candidate_url):
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full_url = normalize_url(urljoin(base_url, href))
        if same_domain(base_url, full_url):
            links.add(full_url)
    return links



def discover_sitemap_urls(start_url):
    """Récupère les URLs du sitemap/robots sans dépendre du framework du site."""
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    candidates = [f"{base}/sitemap.xml"]
    try:
        robots = requests.get(f"{base}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=10)
        if robots.ok:
            for line in robots.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    candidates.append(line.split(":", 1)[1].strip())
    except requests.RequestException:
        pass

    urls = set()
    for sitemap in dict.fromkeys(candidates):
        try:
            response = requests.get(sitemap, headers={"User-Agent": USER_AGENT}, timeout=10)
            if not response.ok or "xml" not in response.headers.get("Content-Type", "") and not response.text.lstrip().startswith("<"):
                continue
            root = ET.fromstring(response.content)
            for loc in root.iter():
                if loc.tag.lower().endswith("loc") and loc.text:
                    url = normalize_url(loc.text.strip())
                    if same_domain(start_url, url):
                        urls.add(url)
        except (requests.RequestException, ET.ParseError):
            continue
    return urls

def _looks_like_js_app(html, discovered_links):
    """Heuristique volontairement prudente : app shell + peu de liens = fallback JS."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="root") or soup.find(id="__next") or soup.find(id="app")
    scripts = soup.find_all("script")
    body_text = soup.body.get_text(" ", strip=True) if soup.body else ""
    return bool(root and scripts and (len(discovered_links) <= 2 or len(body_text) < 300))


def crawl(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH):
    """Crawler requests. Retourne pages, echecs, nombre d'URLs internes."""
    start_url = normalize_url(start_url)
    queue = deque([(start_url, 0)])
    sitemap_urls = discover_sitemap_urls(start_url)
    queue.extend((url, 1) for url in sorted(sitemap_urls) if url != start_url)
    visited, pages, all_urls_found = set(), [], set(sitemap_urls)
    failed = 0
    headers = {"User-Agent": USER_AGENT}

    while queue and len(visited) < max_pages:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
            continue
        visited.add(url)
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
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
            queue.extend((link, depth + 1) for link in sorted(new_links) if link not in visited)
        time.sleep(DELAY_SECONDS)

    return pages, failed, len(all_urls_found)


def crawl_with_playwright(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH):
    """Crawler navigateur : récupère le DOM après exécution du JavaScript."""
    from playwright.sync_api import sync_playwright

    start_url = normalize_url(start_url)
    queue = deque([(start_url, 0)])
    sitemap_urls = discover_sitemap_urls(start_url)
    queue.extend((url, 1) for url in sorted(sitemap_urls) if url != start_url)
    visited, pages, all_urls_found = set(), [], set(sitemap_urls)
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        while queue and len(visited) < max_pages:
            url, depth = queue.popleft()
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            try:
                page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(300)
                # Open all collapsed accordion/disclosure panels so their content
                # is injected into the DOM before we extract HTML.
                # Targets aria-expanded="false" buttons generically — works with
                # Radix UI, Headless UI, and any ARIA-compliant accordion library.
                try:
                    expanded = page.evaluate("""
                        () => {
                            const btns = document.querySelectorAll(
                                'button[aria-expanded="false"]'
                            );
                            btns.forEach(b => b.click());
                            return btns.length;
                        }
                    """)
                    if expanded:
                        page.wait_for_timeout(300)
                except Exception:
                    pass
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
                queue.extend((link, depth + 1) for link in sorted(new_links) if link not in visited)

        context.close()
        browser.close()

    return pages, failed, len(all_urls_found)


def crawl_auto(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH):
    """Essaie le HTML statique puis bascule automatiquement vers Playwright si nécessaire."""
    static_pages, static_failed, static_urls = crawl(start_url, max_pages, max_depth)
    start_page = next((p for p in static_pages if p["url"] == normalize_url(start_url)), None)
    if start_page:
        links = extract_links(start_page["html"], start_page["url"])
        if not _looks_like_js_app(start_page["html"], links):
            return static_pages, static_failed, static_urls

    print("[spider] site probablement dynamique : bascule vers Playwright")
    return crawl_with_playwright(start_url, max_pages, max_depth)
